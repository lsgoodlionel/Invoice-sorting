#!/usr/bin/env bash
# 发票账本 · Ubuntu 一键安装 / 升级脚本
#
# 首次安装与升级使用同一条命令（重复执行即升级，数据与登录密码保留）。
# **安装命令里不含任何账号、密码信息**，首个管理员一律在首次打开网页时设置：
#   - 单账套（默认）：为管理员 admin 设置初始密码，再在「设置 → 用户管理」添加其他用户
#   - SaaS 多账套：用主域名打开网页，设置首个平台管理员的用户名（默认 admin）与密码，随后从「平台」入口开通账套
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Invoice-sorting/main/deploy/install.sh | sudo bash
#
# 安装来源（默认按 GitHub Release 安装，保证同一条命令在任何时刻装到的都是同一份已通过 CI 的产物）：
#   CHANNEL         release（默认，装固定版本的发布包）| main（跟随 main 分支源码，尝鲜与调试用）
#   VERSION         指定版本，例如 v0.2.0；留空即最新正式版。**回滚就是把它改成旧版本号重跑本命令**
#   ALLOW_MAIN_FALLBACK  true（默认）：没有可用 Release 时回退到 main 分支并在日志中显著告警；
#                        false：直接报错退出（对生产环境更保险）
#   RELEASE_BASE_URL     发布包下载前缀，默认 https://github.com/<仓库>/releases/download（可指向内网镜像）
#   RECREATE_VENV        设为 1 时删除旧的 Python 虚拟环境重建（跨大版本回滚后依赖异常时使用）
#
# 可选环境变量（写在 sudo 之后，例如 `| sudo DOMAIN=invoice.example.com bash`）：
#   DOMAIN          访问域名，默认 _（任意域名/IP）
#   ENABLE_HTTPS    true 时用 Let's Encrypt 申请证书（需 DOMAIN 与 EMAIL，且域名已解析到本机）
#   EMAIL           证书通知邮箱
#   HTTP_PORT       对外访问端口（Nginx），默认 8765；启用 HTTPS 时默认 80（证书验证需要）
#   APP_PORT        应用内部端口（仅本机），默认 18765
#   BRANCH          Git 分支，默认 main（仅 CHANNEL=main 生效）
#   REPO_URL        仓库地址
#   MIRROR          下载源：auto（默认，测速选择官方源或国内镜像）| cn | global
#   NO_OCR          设为 1 时不安装截图文字识别（OCR）
#   FRONTEND_BUILD  仅 CHANNEL=main 生效：prebuilt（默认：下载 CI 预构建前端，失败再本地构建）| local
#   INSTALL_DIR     程序目录，默认 /opt/invoice-sorting
#   DATA_DIR        数据目录，默认 /var/lib/invoice-sorting
#
# 部署形态与授权（均可留空，留空即与现在完全一致；升级时不传则沿用上次已配置的值）：
#   DEPLOY_MODE           single（默认，单账套）| saas（多账套）
#   TENANT_HOST_SUFFIX    仅 saas：配置后 t1.example.com 直接定位账套 t1，需泛域名与通配符证书
#   LICENSE_KEY           私有化授权密钥（供应商提供）
#   LICENSE_SERVER        授权校验服务地址，例如 https://saas.example.com
#   CHECK_INTERVAL_HOURS  授权校验间隔小时数，默认 24
#   GRACE_DAYS            授权过期后的宽限天数，默认 14
#
# 详细说明见 docs/部署与运维.md。
set -Eeuo pipefail
# 任何命令意外失败都打印位置，避免静默退出
trap 'printf "\033[1;31m[错误]\033[0m 安装中断：第 %s 行命令失败：%s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

APP_NAME="invoice-sorting"
REPO_URL="${REPO_URL:-https://github.com/lsgoodlionel/Invoice-sorting.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/invoice-sorting}"
APP_DIR="${INSTALL_DIR}/app"
# 安装来源：release（按版本装发布包）/ main（跟随分支源码）
CHANNEL_RELEASE="release"
CHANNEL_MAIN="main"
CHANNEL="${CHANNEL:-$CHANNEL_RELEASE}"
VERSION="${VERSION:-}"
OS_RELEASE_FILE="${OS_RELEASE_FILE:-/etc/os-release}"  # 可在测试中指向假文件
ALLOW_MAIN_FALLBACK="${ALLOW_MAIN_FALLBACK:-true}"
# owner/repo，用于拼接 Release 下载地址
REPO_SLUG="$(printf '%s' "${REPO_URL%.git}" | sed -E 's#^.*github\.com[:/]##')"
RELEASE_BASE_URL="${RELEASE_BASE_URL:-https://github.com/${REPO_SLUG}/releases/download}"
RELEASE_LATEST_URL="${RELEASE_LATEST_URL:-https://github.com/${REPO_SLUG}/releases/latest}"
RELEASE_API_URL="${RELEASE_API_URL:-https://api.github.com/repos/${REPO_SLUG}/releases/latest}"
# 发布包里的资产名（由 .github/workflows/release.yml 生成）
RELEASE_ASSETS=(SHA256SUMS manifest.json backend.tar.gz frontend.tar.gz deploy.tar.gz)
RELEASE_ARCHIVES=(backend.tar.gz frontend.tar.gz deploy.tar.gz manifest.json)
# 已安装版本记录：cat /opt/invoice-sorting/VERSION 即可查看
VERSION_FILE="${INSTALL_DIR}/VERSION"
# 本次安装的来源与版本，由 fetch_source 填充
SOURCE_CHANNEL="$CHANNEL"
TARGET_VERSION=""
TARGET_COMMIT=""
DATA_DIR="${DATA_DIR:-/var/lib/invoice-sorting}"
APP_USER="${APP_USER:-invoice}"
# Python 字节码缓存集中到这里（systemd 里设 PYTHONPYCACHEPREFIX）：
# 缓存损坏时整目录删掉即可恢复，不会牵连代码目录，也不会再出现散落的 __pycache__
PYCACHE_DIR="${PYCACHE_DIR:-/var/cache/${APP_NAME}/pycache}"
APP_PORT="${APP_PORT:-18765}"
if [ "${ENABLE_HTTPS:-false}" = "true" ]; then
  HTTP_PORT="${HTTP_PORT:-80}"
else
  HTTP_PORT="${HTTP_PORT:-8765}"
fi
DOMAIN="${DOMAIN:-_}"
ENABLE_HTTPS="${ENABLE_HTTPS:-false}"
EMAIL="${EMAIL:-}"
NODE_MAJOR=22
# 略高于应用自身的单文件上限（config.py MAX_UPLOAD_BYTES = 30 MB），
# 让超限文件由应用返回中文提示，同时挡住明显过大的请求
MAX_UPLOAD_MB=40
LEGACY_HTPASSWD_FILE="/etc/nginx/${APP_NAME}.htpasswd"  # 旧版 Nginx 登录弹窗，升级时删除
NGINX_SITE="/etc/nginx/sites-available/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
BACKUP_KEEP=10
MODE_SINGLE="single"
MODE_SAAS="saas"
DEFAULT_CHECK_INTERVAL_HOURS=24
DEFAULT_GRACE_DAYS=14
DEFAULT_LOG_LEVEL=INFO
DEFAULT_LOG_APP=invoice-sorting
DEFAULT_LOG_BRANCH=main
# 注意：DEPLOY_MODE / TENANT_HOST_SUFFIX / LICENSE_* / LOG_* / CHECK_INTERVAL_HOURS / GRACE_DAYS
# 这几项**不在此处赋默认值**：resolve_deployment_settings 要靠「变量是否被设置过」
# 区分“用户本次显式传入空值（清空）”和“没传（沿用旧配置）”。

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

as_app() { runuser -u "$APP_USER" -- env HOME="$INSTALL_DIR" PATH="/usr/local/bin:/usr/bin:/bin" "$@"; }
has_systemd() { [ -d /run/systemd/system ]; }

# 读取 systemd 单元中已写入的环境变量值；单元不存在或没配过时输出空
unit_env() {
  [ -f "$SERVICE_FILE" ] || return 0
  sed -n "s/^Environment=$1=//p" "$SERVICE_FILE" | tail -n1
}

# 解析一项配置：本次显式传入（哪怕是空串）优先，其次沿用单元文件中的旧值，最后用默认值。
# 这样升级时不带 LICENSE_KEY 重跑安装命令不会把已配置的密钥清空；确实要清空时传 LICENSE_KEY= 即可。
resolve_setting() {
  local name="$1" unit_key="$2" fallback="${3:-}" previous
  if [ -n "${!name+set}" ]; then
    printf '%s' "${!name}"
    return 0
  fi
  previous="$(unit_env "$unit_key")"
  printf '%s' "${previous:-$fallback}"
}

is_positive_int() { [ -n "$1" ] && [ -z "${1//[0-9]/}" ] && [ "$1" -gt 0 ] 2>/dev/null; }

# 运行日志与故障上报（docs/日志与故障上报_设计.md）。
# **默认不上传**：LOG_REPO 与 LOG_TOKEN 两项都配置了才会把诊断包发到私有仓库。
# 令牌只写进 systemd 单元（随后 chmod 600），脚本任何输出里都不回显它。
resolve_log_settings() {
  LOG_LEVEL="$(resolve_setting LOG_LEVEL INVOICE_SORTING_LOG_LEVEL "$DEFAULT_LOG_LEVEL")"
  LOG_REPO="$(resolve_setting LOG_REPO INVOICE_SORTING_LOG_REPO)"
  LOG_TOKEN="$(resolve_setting LOG_TOKEN INVOICE_SORTING_LOG_TOKEN)"
  LOG_APP="$(resolve_setting LOG_APP INVOICE_SORTING_LOG_APP "$DEFAULT_LOG_APP")"
  LOG_INSTANCE="$(resolve_setting LOG_INSTANCE INVOICE_SORTING_LOG_INSTANCE)"
  LOG_BRANCH="$(resolve_setting LOG_BRANCH INVOICE_SORTING_LOG_BRANCH "$DEFAULT_LOG_BRANCH")"

  if [ -n "$LOG_REPO" ] && [[ ! "$LOG_REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    die "LOG_REPO 需要写成 owner/repo（当前：${LOG_REPO}）"
  fi
  if [ -n "$LOG_REPO" ] && [ -z "$LOG_TOKEN" ]; then
    warn "只配置了 LOG_REPO、没有 LOG_TOKEN，诊断包不会上传（仍会保存在本机）"
  fi
  if [ -z "$LOG_REPO" ] && [ -n "$LOG_TOKEN" ]; then
    warn "只配置了 LOG_TOKEN、没有 LOG_REPO，诊断包不会上传（仍会保存在本机）"
  fi
  if [ -n "$LOG_REPO" ] && [ -n "$LOG_TOKEN" ]; then
    warn "已启用诊断包上传：出故障时会把**脱敏后**的诊断包发到私有仓库 ${LOG_REPO}"
    warn "关闭方式：重新执行安装命令并传 LOG_REPO= （留空）"
  fi
}

# 解析部署形态与授权配置，并做基本校验（必须在 check_environment 中、写单元文件之前调用）
resolve_deployment_settings() {
  DEPLOY_MODE="$(resolve_setting DEPLOY_MODE INVOICE_SORTING_DEPLOYMENT_MODE "$MODE_SINGLE")"
  TENANT_HOST_SUFFIX="$(resolve_setting TENANT_HOST_SUFFIX INVOICE_SORTING_TENANT_HOST_SUFFIX)"
  LICENSE_KEY="$(resolve_setting LICENSE_KEY INVOICE_SORTING_LICENSE_KEY)"
  LICENSE_SERVER="$(resolve_setting LICENSE_SERVER INVOICE_SORTING_LICENSE_SERVER)"
  CHECK_INTERVAL_HOURS="$(resolve_setting CHECK_INTERVAL_HOURS \
    INVOICE_SORTING_LICENSE_CHECK_INTERVAL_HOURS "$DEFAULT_CHECK_INTERVAL_HOURS")"
  GRACE_DAYS="$(resolve_setting GRACE_DAYS INVOICE_SORTING_LICENSE_GRACE_DAYS "$DEFAULT_GRACE_DAYS")"
  resolve_log_settings

  case "$DEPLOY_MODE" in
    "$MODE_SINGLE" | "$MODE_SAAS") ;;
    *) die "DEPLOY_MODE 只能是 ${MODE_SINGLE} 或 ${MODE_SAAS}（当前：${DEPLOY_MODE}）" ;;
  esac
  if [ "$DEPLOY_MODE" = "$MODE_SINGLE" ] && [ -n "$TENANT_HOST_SUFFIX" ]; then
    warn "TENANT_HOST_SUFFIX 只在 DEPLOY_MODE=saas 下生效，本次已忽略"
    TENANT_HOST_SUFFIX=""
  fi
  TENANT_HOST_SUFFIX="${TENANT_HOST_SUFFIX#.}"
  if [ "$DEPLOY_MODE" = "$MODE_SAAS" ] && [ -n "$LICENSE_KEY" ]; then
    warn "多账套（saas）模式不校验私有化授权，LICENSE_KEY 仅记录在配置中，不会生效"
  fi
  if [ -n "$LICENSE_KEY" ] && [ -z "$LICENSE_SERVER" ]; then
    warn "只配置了 LICENSE_KEY、没有 LICENSE_SERVER，授权校验不会启用（按本机自用方式运行）"
  fi
  is_positive_int "$CHECK_INTERVAL_HOURS" || die "CHECK_INTERVAL_HOURS 需为正整数（当前：${CHECK_INTERVAL_HOURS}）"
  is_positive_int "$GRACE_DAYS" || die "GRACE_DAYS 需为正整数（当前：${GRACE_DAYS}）"
}

# 校验安装来源相关的参数（CHANNEL / VERSION / ALLOW_MAIN_FALLBACK）
check_source_settings() {
  case "$CHANNEL" in
    "$CHANNEL_RELEASE" | "$CHANNEL_MAIN") ;;
    *) die "CHANNEL 只能是 ${CHANNEL_RELEASE} 或 ${CHANNEL_MAIN}（当前：${CHANNEL}）" ;;
  esac
  case "$ALLOW_MAIN_FALLBACK" in
    true | false) ;;
    *) die "ALLOW_MAIN_FALLBACK 只能是 true 或 false（当前：${ALLOW_MAIN_FALLBACK}）" ;;
  esac
  if [ -n "$VERSION" ]; then
    case "$VERSION" in
      v[0-9]*) ;;
      *) die "VERSION 需形如 v0.2.0（当前：${VERSION}）" ;;
    esac
    [ "$CHANNEL" = "$CHANNEL_RELEASE" ] ||
      warn "CHANNEL=${CHANNEL_MAIN} 时不按版本安装，VERSION=${VERSION} 本次忽略"
  fi
  [ -n "$REPO_SLUG" ] || die "无法从 REPO_URL 解析出 owner/repo（当前：${REPO_URL}）"
}

# 在子 shell 中读取 /etc/os-release 的某个字段。
# 不能直接 source：它带有 NAME/VERSION/ID 等变量，其中 VERSION 会覆盖脚本自己的
# 版本参数（Ubuntu 上是 "24.04.5 LTS (Noble Numbat)"），导致后续版本校验必然失败。
os_release_field() {
  (
    # shellcheck disable=SC1090,SC1091
    . "$OS_RELEASE_FILE" >/dev/null 2>&1 || exit 0
    printf '%s' "${!1:-}"
  )
}

check_environment() {
  [ "$(id -u)" -eq 0 ] || die "请使用 root 运行（在命令前加 sudo）"
  [ -r "$OS_RELEASE_FILE" ] || die "无法识别操作系统"
  local os_id os_pretty
  os_id="$(os_release_field ID)"
  os_pretty="$(os_release_field PRETTY_NAME)"
  [ "$os_id" = "ubuntu" ] || warn "本脚本针对 Ubuntu 22.04/24.04 编写，当前系统：${os_pretty:-未知}"
  if [ "$ENABLE_HTTPS" = "true" ] && { [ "$DOMAIN" = "_" ] || [ -z "$EMAIL" ]; }; then
    die "启用 HTTPS 需要同时设置 DOMAIN 与 EMAIL"
  fi
  [ "$HTTP_PORT" != "$APP_PORT" ] || die "HTTP_PORT 与 APP_PORT 不能相同（当前均为 ${APP_PORT}）"
  check_source_settings
  resolve_deployment_settings
  if [ -n "$TENANT_HOST_SUFFIX" ]; then
    log "多账套子域名已启用：*.${TENANT_HOST_SUFFIX} 将解析为对应账套"
    [ "$DOMAIN" != "_" ] || warn "未设置 DOMAIN，Nginx 仍按任意域名接收请求；建议同时设置 DOMAIN=${TENANT_HOST_SUFFIX}"
    if [ "$ENABLE_HTTPS" = "true" ]; then
      warn "子域名接入需要 *.${TENANT_HOST_SUFFIX} 的通配符证书，Let's Encrypt 的通配符证书只能用 DNS 验证申请；"
      warn "本脚本只会为 ${DOMAIN} 申请单域名证书，子域名访问需自行配置通配符证书。"
    fi
  fi
}

install_packages() {
  log "安装系统依赖"
  export DEBIAN_FRONTEND=noninteractive
  # 过滤 apt 的重复源等警告（W:），保留错误输出
  apt-get update -qq 2>&1 | grep -v '^W: ' || true
  # libgl1、libglib2.0-0 为 OCR（opencv）运行所需；python3-venv 用于从 PyPI 镜像安装 uv
  apt-get install -y -qq git curl ca-certificates xz-utils nginx sqlite3 \
    libgl1 libglib2.0-0 python3-venv >/dev/null
}

load_mirrors() {
  # release 通道不会用到 Node.js / npm（前端是发布包里现成的），跳过这两项测速省下十几秒
  if [ "$SOURCE_CHANNEL" = "$CHANNEL_RELEASE" ]; then
    export NPM_REGISTRY="${NPM_REGISTRY:-https://registry.npmjs.org}"
    export NODE_DIST="${NODE_DIST:-https://nodejs.org/dist}"
  fi
  # shellcheck source=/dev/null
  . "${APP_DIR}/scripts/lib/mirrors.sh"
  select_mirrors
}

install_node() {
  local current=0
  if command -v node >/dev/null 2>&1; then
    current="$(node -p 'process.versions.node.split(".")[0]')"
  fi
  if [ "$current" -lt 20 ]; then
    install_node_binary
  fi
  corepack enable >/dev/null 2>&1 || npm install -g pnpm --registry "$NPM_REGISTRY" >/dev/null
}

install_node_binary() {
  local arch tarball
  case "$(uname -m)" in
    x86_64) arch="x64" ;;
    aarch64 | arm64) arch="arm64" ;;
    *) die "不支持的 CPU 架构：$(uname -m)" ;;
  esac
  tarball="$(curl -fsSL --retry 5 --retry-all-errors "${NODE_DIST}/latest-v${NODE_MAJOR}.x/SHASUMS256.txt" |
    grep -o "node-v[0-9.]*-linux-${arch}.tar.xz" | head -n1)"
  [ -n "$tarball" ] || die "无法获取 Node.js ${NODE_MAJOR} 版本信息（${NODE_DIST}）"
  log "安装 Node.js（${tarball}，来源 ${NODE_DIST}）"
  local archive="${INSTALL_DIR}/.cache/${tarball}"
  mkdir -p "${INSTALL_DIR}/.cache"
  # 断点续传 + 重试，避免慢速网络下只下载到半个文件
  curl -fL -C - --retry 8 --retry-all-errors --retry-delay 3 --connect-timeout 20 \
    -o "$archive" "${NODE_DIST}/latest-v${NODE_MAJOR}.x/${tarball}"
  tar -xJf "$archive" -C /usr/local --strip-components=1 --exclude='*.md' --exclude=LICENSE
}

install_uv() {
  command -v uv >/dev/null 2>&1 && return 0
  log "安装 uv（来源 ${PYPI_INDEX}）"
  # 从选中的 PyPI 源安装 uv，避免国内访问 GitHub Releases 过慢
  python3 -m venv "${INSTALL_DIR}/tools"
  "${INSTALL_DIR}/tools/bin/pip" install --quiet --timeout 120 --retries 10 \
    --index-url "$PYPI_INDEX" uv
  ln -sf "${INSTALL_DIR}/tools/bin/uv" /usr/local/bin/uv
}

prepare_user_and_dirs() {
  if ! id "$APP_USER" >/dev/null 2>&1; then
    log "创建系统用户 ${APP_USER}"
    useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin "$APP_USER"
  fi
  mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$PYCACHE_DIR"
  chown "$APP_USER:$APP_USER" "$INSTALL_DIR"
  chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
  chmod 750 "$DATA_DIR"
  chown -R "$APP_USER:$APP_USER" "$PYCACHE_DIR"
  chmod 750 "$PYCACHE_DIR"
}

# 备份一个 SQLite 库到 数据目录/备份/<前缀><时间>.db，并按前缀清理旧备份
backup_sqlite_db() {
  local db="$1" prefix="$2"
  [ -f "$db" ] || return 0
  local dir="${DATA_DIR}/备份"
  local target
  target="${dir}/${prefix}$(date +%Y%m%d_%H%M%S).db"
  mkdir -p "$dir"
  log "升级前备份 $(basename "$db") → ${target}"
  sqlite3 "$db" ".backup '${target}'"
  chown "$APP_USER:$APP_USER" "$dir" "$target"
  # 仅保留最近若干份升级备份
  find "$dir" -maxdepth 1 -name "${prefix}*.db" -printf '%T@ %p\n' | sort -rn |
    tail -n +"$((BACKUP_KEEP + 1))" | cut -d' ' -f2- | xargs -r rm -f
}

backup_database() {
  # 业务库（沿用原有 upgrade_ 前缀，旧备份文件名不变）与控制库（账套、账号、套餐、授权）
  backup_sqlite_db "${DATA_DIR}/invoice.db" "upgrade_"
  backup_sqlite_db "${DATA_DIR}/control.db" "control_upgrade_"
}

# ---------------------------------------------------------------------------
# 代码来源：release 通道下载固定版本的发布包并校验 SHA-256；main 通道走 git。
# ---------------------------------------------------------------------------

# 读取已安装版本（<程序目录>/VERSION 里的 VERSION= 行）；没装过时输出空
installed_version() {
  [ -f "$VERSION_FILE" ] || return 0
  sed -n 's/^VERSION=//p' "$VERSION_FILE" | tail -n1
}

# 记录本次安装的版本，供下次升级对比与人工查看。
# 放在服务起来、健康检查通过之后写：这样文件里始终是"当前真正在跑的版本"，
# 装到一半失败时保留旧记录，重跑安装命令仍能正确打印「旧版本 → 新版本」。
record_version() {
  cat >"$VERSION_FILE" <<EOF
# 由 deploy/install.sh 写入，记录当前已安装的版本；回滚见 docs/部署与运维.md
VERSION=${TARGET_VERSION}
CHANNEL=${SOURCE_CHANNEL}
COMMIT=${TARGET_COMMIT}
INSTALLED_AT=$(date -Iseconds)
EOF
  chmod 644 "$VERSION_FILE"
}

# 下载单个文件：重试 + 超时，失败返回非 0（由调用方决定是否回退）
download_file() {
  curl -fL -# --retry 5 --retry-all-errors --retry-delay 3 \
    --connect-timeout 20 --max-time 1800 -o "$2" "$1"
}

# 按 SHA256SUMS 校验一个文件；不匹配直接终止（下载被截断或文件被篡改）
verify_sha256() {
  local file="$1" sums="$2" name expected actual
  name="$(basename "$file")"
  expected="$(awk -v n="$name" '$2 == n { print $1 }' "$sums" | head -n1)"
  [ -n "$expected" ] || die "校验和文件 SHA256SUMS 里没有 ${name} 的记录，发布包不完整，请换一个 VERSION 重试"
  actual="$(sha256sum "$file" | awk '{ print $1 }')"
  [ "$actual" = "$expected" ] ||
    die "${name} 的 SHA-256 校验失败（期望 ${expected}，实际 ${actual}）；下载被截断或文件被篡改，请重新执行安装命令"
}

# 解析最新正式版的标签：先跟随 /releases/latest 的跳转（不消耗 API 配额），再退回 API
resolve_latest_version() {
  local final tag=""
  final="$(curl -fsSL --retry 3 --retry-all-errors --connect-timeout 15 --max-time 60 \
    -o /dev/null -w '%{url_effective}' "$RELEASE_LATEST_URL" 2>/dev/null || true)"
  case "$final" in
    */releases/tag/*) tag="${final##*/tag/}" ;;
  esac
  if [ -z "$tag" ]; then
    # 退回 GitHub API（跳转被中间层改写时）；查不到只当作"没有 Release"，不算错误
    tag="$( { curl -fsSL --retry 3 --retry-all-errors --connect-timeout 15 --max-time 60 \
      "$RELEASE_API_URL" 2>/dev/null || true; } |
      sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
  fi
  printf '%s' "$tag"
}

# 用暂存目录整体替换程序目录：先换再删，尽量缩短不可用窗口；
# 保留已有的 Python 虚拟环境，升级时不必重装全部依赖（RECREATE_VENV=1 时由 build_app 重建）。
swap_app_dir() {
  local stage="$1" old="${APP_DIR}.old"
  rm -rf "$old"
  if [ -d "$APP_DIR" ]; then
    mv "$APP_DIR" "$old"
    if [ -d "${old}/backend/.venv" ]; then
      mv "${old}/backend/.venv" "${stage}/backend/.venv"
    fi
  fi
  mv "$stage" "$APP_DIR"
  rm -rf "$old"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
}

# 发布包解包后必须具备的文件，缺任何一个都说明这个 Release 不可用
assert_release_complete() {
  local stage="$1" path
  for path in backend/pyproject.toml backend/uv.lock scripts/setup.sh \
    deploy/startup-check.sh frontend/dist/index.html; do
    [ -e "${stage}/${path}" ] || die "发布包 ${TARGET_VERSION} 内容不完整（缺少 ${path}），请换一个 VERSION 重试"
  done
}

# 下载并安装指定版本的发布包；下载不到（没有 Release / 网络不通）时返回非 0 交给调用方决定回退
fetch_release() {
  local work="${INSTALL_DIR}/.download" stage="${INSTALL_DIR}/.stage" base name
  TARGET_VERSION="$VERSION"
  if [ -z "$TARGET_VERSION" ]; then
    log "查询最新正式版本（${RELEASE_LATEST_URL}）"
    TARGET_VERSION="$(resolve_latest_version)"
  fi
  if [ -z "$TARGET_VERSION" ]; then
    warn "未找到可用的 Release：仓库 ${REPO_SLUG} 可能还没有发布过版本，或当前网络无法访问 GitHub"
    return 1
  fi

  base="${RELEASE_BASE_URL}/${TARGET_VERSION}"
  rm -rf "$work" "$stage"
  mkdir -p "$work" "${stage}/frontend"
  log "下载发布包 ${TARGET_VERSION}（${base}）"
  for name in "${RELEASE_ASSETS[@]}"; do
    if ! download_file "${base}/${name}" "${work}/${name}"; then
      warn "下载失败：${base}/${name}"
      warn "请确认版本 ${TARGET_VERSION} 存在（见 https://github.com/${REPO_SLUG}/releases），以及服务器能访问 GitHub"
      rm -rf "$work" "$stage"
      return 1
    fi
  done

  log "校验 SHA-256"
  for name in "${RELEASE_ARCHIVES[@]}"; do
    verify_sha256 "${work}/${name}" "${work}/SHA256SUMS"
  done

  tar -xzf "${work}/backend.tar.gz" -C "$stage"
  tar -xzf "${work}/deploy.tar.gz" -C "$stage"
  tar -xzf "${work}/frontend.tar.gz" -C "${stage}/frontend"
  assert_release_complete "$stage"
  TARGET_COMMIT="$(sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "${work}/manifest.json" | head -n1)"
  cp "${work}/manifest.json" "${stage}/RELEASE.json"
  swap_app_dir "$stage"
  rm -rf "$work"
  SOURCE_CHANNEL="$CHANNEL_RELEASE"
  return 0
}

# main 通道：仍然用 git 拉取分支最新代码（内容随分支变动，适合尝鲜与调试）
fetch_from_git() {
  if [ -d "${APP_DIR}/.git" ]; then
    log "更新代码（${BRANCH}）"
    as_app git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
    as_app git -C "$APP_DIR" reset --quiet --hard "origin/${BRANCH}"
  else
    # 目录存在但不是 git 仓库（上次是 release 通道装的）：先腾空再克隆，
    # 虚拟环境先挪到一边，克隆完再放回去，避免重装全部依赖。
    local kept="${INSTALL_DIR}/.venv-keep"
    rm -rf "$kept"
    if [ -d "${APP_DIR}/backend/.venv" ]; then
      mv "${APP_DIR}/backend/.venv" "$kept"
    fi
    rm -rf "$APP_DIR"
    log "下载代码 ${REPO_URL}"
    as_app git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
    if [ -d "$kept" ]; then
      mv "$kept" "${APP_DIR}/backend/.venv"
      chown -R "$APP_USER:$APP_USER" "${APP_DIR}/backend/.venv"
    fi
  fi
  TARGET_COMMIT="$(as_app git -C "$APP_DIR" rev-parse HEAD)"
  TARGET_VERSION="${BRANCH}@${TARGET_COMMIT:0:7}"
  SOURCE_CHANNEL="$CHANNEL_MAIN"
  log "当前代码：$(as_app git -C "$APP_DIR" log -1 --format='%h %s')"
}

fetch_source() {
  local previous
  previous="$(installed_version)"
  if [ -n "$previous" ]; then
    log "已安装版本：${previous}"
  else
    log "未检测到已安装版本（按全新安装处理）"
  fi

  if [ "$CHANNEL" = "$CHANNEL_RELEASE" ] && fetch_release; then
    log "版本变更：${previous:-无} → ${TARGET_VERSION}（来源：Release，已校验 SHA-256）"
    return 0
  fi
  if [ "$CHANNEL" = "$CHANNEL_RELEASE" ]; then
    [ "$ALLOW_MAIN_FALLBACK" = "true" ] ||
      die "无法从 Release 安装（原因见上方），且 ALLOW_MAIN_FALLBACK=false。请指定一个存在的 VERSION 重试，或临时改用 CHANNEL=main"
    warn "──────────────────────────────────────────────"
    warn "注意：本次**没有**按固定版本安装，已回退到 ${BRANCH} 分支的最新源码。"
    warn "分支内容随时会变，不同时间安装结果可能不同；正式环境请改用 VERSION=vX.Y.Z 指定版本，"
    warn "或加 ALLOW_MAIN_FALLBACK=false 让脚本在没有 Release 时直接报错而不是回退。"
    warn "──────────────────────────────────────────────"
  fi
  fetch_from_git
  log "版本变更：${previous:-无} → ${TARGET_VERSION}（来源：${BRANCH} 分支源码，非固定版本）"
}

prepare_frontend() {
  # release 通道：前端 dist 已随发布包解包到位，无需再下载或构建
  if [ "$SOURCE_CHANNEL" = "$CHANNEL_RELEASE" ]; then
    [ "${FRONTEND_BUILD:-}" != "local" ] ||
      warn "release 通道直接使用发布包内已构建好的前端，FRONTEND_BUILD=local 本次忽略"
    FRONTEND_READY=1
    return 0
  fi
  # 优先下载 CI 预构建前端：服务器无需 Node.js/pnpm，也不依赖 npm 源
  if [ "${FRONTEND_BUILD:-prebuilt}" != "local" ] && as_app bash "${APP_DIR}/scripts/fetch-frontend.sh"; then
    FRONTEND_READY=1
    return 0
  fi
  log "改为在服务器上构建前端（需要 Node.js）"
  install_node
  FRONTEND_READY=0
}

stop_service() {
  # 升级期间停止旧服务：避免它在依赖替换过程中反复重启、写入损坏的 .pyc 缓存，也让数据库备份一致
  if has_systemd && systemctl is-active --quiet "$APP_NAME" 2>/dev/null; then
    log "停止旧服务"
    systemctl stop "$APP_NAME" || true
  fi
}

# 清空集中缓存目录，并清掉旧版本遗留在 venv / src 下的 __pycache__
clear_bytecode_cache() {
  mkdir -p "$PYCACHE_DIR"
  rm -rf -- "${PYCACHE_DIR:?}"/* 2>/dev/null || true
  find "${APP_DIR}/backend/.venv" "${APP_DIR}/backend/src" \
    -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  chown -R "$APP_USER:$APP_USER" "$PYCACHE_DIR"
}

verify_backend() {
  # 清除 .pyc 缓存后重新编译并试导入；缓存损坏（bad marshal data）或依赖不完整时重建虚拟环境一次。
  # 编译与导入都带上 PYTHONPYCACHEPREFIX，保证生成的缓存与服务运行时用的是同一个目录。
  local venv="${APP_DIR}/backend/.venv"
  local attempt
  for attempt in 1 2; do
    clear_bytecode_cache
    as_app env PYTHONPYCACHEPREFIX="$PYCACHE_DIR" "$venv/bin/python" \
      -m compileall -q "$venv/lib" "${APP_DIR}/backend/src" >/dev/null 2>&1 || true
    if as_app env PYTHONPYCACHEPREFIX="$PYCACHE_DIR" "$venv/bin/python" \
      -c "import invoice_sorting.main, openpyxl" 2>/tmp/invoice-sorting-import.log; then
      return 0
    fi
    if [ "$attempt" = 2 ]; then
      break
    fi
    warn "后端导入失败，重建 Python 虚拟环境后重试："
    tail -n 3 /tmp/invoice-sorting-import.log >&2 || true
    rm -rf "$venv"
    build_app
  done
  cat /tmp/invoice-sorting-import.log >&2 || true
  die "后端依赖安装不完整，原因见上方日志；可删除 ${venv} 后重新执行安装命令"
}

build_app() {
  if [ "${RECREATE_VENV:-0}" = "1" ] && [ -d "${APP_DIR}/backend/.venv" ]; then
    log "按 RECREATE_VENV=1 重建 Python 虚拟环境"
    rm -rf "${APP_DIR}/backend/.venv"
  fi
  # UV_NO_CONFIG：不读取任何 uv.toml，避免受调用者目录或用户配置影响
  as_app env MIRROR="$MIRROR" NO_OCR="${NO_OCR:-0}" UV_NO_CONFIG=1 \
    SKIP_FRONTEND="${FRONTEND_READY:-0}" FRONTEND_BUILD=local \
    PYPI_INDEX="$PYPI_INDEX" NPM_REGISTRY="$NPM_REGISTRY" NODE_DIST="$NODE_DIST" \
    PYTHON_MIRROR="$PYTHON_MIRROR" \
    UV_PYTHON_INSTALL_DIR="${INSTALL_DIR}/python" UV_CACHE_DIR="${INSTALL_DIR}/.cache/uv" \
    bash "${APP_DIR}/scripts/setup.sh"
}

# 部署形态与授权对应的 Environment= 行；留空的项不写入，保持单元文件干净
deployment_env_lines() {
  printf 'Environment=INVOICE_SORTING_DEPLOYMENT_MODE=%s\n' "$DEPLOY_MODE"
  if [ -n "$TENANT_HOST_SUFFIX" ]; then
    printf 'Environment=INVOICE_SORTING_TENANT_HOST_SUFFIX=%s\n' "$TENANT_HOST_SUFFIX"
  fi
  if [ -n "$LICENSE_KEY" ]; then
    printf 'Environment=INVOICE_SORTING_LICENSE_KEY=%s\n' "$LICENSE_KEY"
  fi
  if [ -n "$LICENSE_SERVER" ]; then
    printf 'Environment=INVOICE_SORTING_LICENSE_SERVER=%s\n' "$LICENSE_SERVER"
    printf 'Environment=INVOICE_SORTING_LICENSE_CHECK_INTERVAL_HOURS=%s\n' "$CHECK_INTERVAL_HOURS"
    printf 'Environment=INVOICE_SORTING_LICENSE_GRACE_DAYS=%s\n' "$GRACE_DAYS"
  fi
  log_env_lines
  return 0
}

# 运行日志与故障上报的 Environment= 行；未配置的项不写入，保持单元文件干净
log_env_lines() {
  printf 'Environment=INVOICE_SORTING_LOG_LEVEL=%s\n' "$LOG_LEVEL"
  if [ -n "$LOG_REPO" ]; then
    printf 'Environment=INVOICE_SORTING_LOG_REPO=%s\n' "$LOG_REPO"
    printf 'Environment=INVOICE_SORTING_LOG_APP=%s\n' "$LOG_APP"
    printf 'Environment=INVOICE_SORTING_LOG_BRANCH=%s\n' "$LOG_BRANCH"
  fi
  if [ -n "$LOG_TOKEN" ]; then
    printf 'Environment=INVOICE_SORTING_LOG_TOKEN=%s\n' "$LOG_TOKEN"
  fi
  if [ -n "$LOG_INSTANCE" ]; then
    printf 'Environment=INVOICE_SORTING_LOG_INSTANCE=%s\n' "$LOG_INSTANCE"
  fi
  return 0
}

write_service() {
  log "配置 systemd 服务（形态：${DEPLOY_MODE}）"
  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=发票账本（个人发票报销管理）
After=network.target
# 崩溃重启限速：5 分钟内失败超过 5 次就停下，避免无限重启刷爆日志、掩盖真正的错误。
# 修好之后执行：systemctl reset-failed ${APP_NAME} && systemctl start ${APP_NAME}
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment=INVOICE_SORTING_DATA_DIR=${DATA_DIR}
Environment=INVOICE_SORTING_HOST=127.0.0.1
Environment=INVOICE_SORTING_PORT=${APP_PORT}
Environment=INVOICE_SORTING_OPEN_BROWSER=false
Environment=INVOICE_SORTING_FRONTEND_DIST=${APP_DIR}/frontend/dist
Environment=TZ=Asia/Shanghai
Environment=PYTHONPYCACHEPREFIX=${PYCACHE_DIR}
$(deployment_env_lines)
# 启动前自检一次导入；失败会清空字节码缓存后重试，"-" 表示自检本身不阻塞启动
ExecStartPre=-/usr/bin/env bash ${APP_DIR}/deploy/startup-check.sh
ExecStart=${APP_DIR}/backend/.venv/bin/invoice-sorting
# 非正常退出时在日志里留一段排查提示（正常停止不输出）
ExecStopPost=-/usr/bin/env bash ${APP_DIR}/deploy/startup-check.sh --failure-hint
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
ReadWritePaths=${DATA_DIR} ${PYCACHE_DIR}

[Install]
WantedBy=multi-user.target
EOF
  # 单元文件里含授权密钥或日志仓库令牌时收紧权限（systemd 以 root 读取，不影响启动）
  if [ -n "$LICENSE_KEY" ] || [ -n "$LOG_TOKEN" ]; then
    chmod 600 "$SERVICE_FILE"
  else
    chmod 644 "$SERVICE_FILE"
  fi
}

# 输出监听指定 TCP 端口的进程名（无人监听时为空）
port_owner() {
  # 无人监听时 grep 无匹配返回 1，在 pipefail 下不能当作错误
  ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'users:(("[^"]*"' | head -n1 | cut -d'"' -f2 || true
}

check_ports() {
  local owner
  owner="$(port_owner "$HTTP_PORT")"
  if [ -n "$owner" ] && [ "$owner" != "nginx" ]; then
    die "访问端口 ${HTTP_PORT} 已被程序「${owner}」占用。请停止该程序，或换一个端口重新执行，例如：| sudo HTTP_PORT=18080 bash"
  fi
  owner="$(port_owner "$APP_PORT")"
  if [ -n "$owner" ] && ! systemctl is-active --quiet "$APP_NAME" 2>/dev/null; then
    die "应用内部端口 ${APP_PORT} 已被程序「${owner}」占用。请换一个端口重新执行，例如：| sudo APP_PORT=18766 bash"
  fi
}

# Nginx 自带的默认站点监听 80 端口；80 端口已被其他程序占用时会导致 Nginx 无法启动
disable_conflicting_default_site() {
  local default_site=/etc/nginx/sites-enabled/default owner
  [ -e "$default_site" ] || return 0
  owner="$(port_owner 80)"
  if [ "$HTTP_PORT" = "80" ] && [ "$DOMAIN" = "_" ]; then
    rm -f "$default_site"
  elif [ -n "$owner" ] && [ "$owner" != "nginx" ]; then
    warn "80 端口已被「${owner}」占用，停用 Nginx 自带的默认站点以避免冲突"
    rm -f "$default_site"
  fi
}

# server_name：配置了多账套子域名后同时接收泛域名（.example.com 含 example.com 与其所有子域名）
server_name_value() {
  if [ -n "$TENANT_HOST_SUFFIX" ] && [ "$DOMAIN" != "_" ]; then
    printf '%s .%s' "$DOMAIN" "$TENANT_HOST_SUFFIX"
    return 0
  fi
  printf '%s' "$DOMAIN"
}

ipv6_listen_line() {
  # 系统未启用 IPv6 时监听 [::] 会导致 Nginx 启动失败
  [ -s /proc/net/if_inet6 ] && echo "    listen [::]:${HTTP_PORT};"
  return 0
}

write_nginx() {
  log "配置 Nginx 反向代理"
  rm -f "$LEGACY_HTPASSWD_FILE"
  check_ports
  cat >"$NGINX_SITE" <<EOF
server {
    listen ${HTTP_PORT};
$(ipv6_listen_line)
    server_name $(server_name_value);

    client_max_body_size ${MAX_UPLOAD_MB}m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
}
EOF
  ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/${APP_NAME}"
  disable_conflicting_default_site
  nginx -t >/dev/null 2>&1 || { nginx -t; die "Nginx 配置检查失败"; }
}

enable_https() {
  [ "$ENABLE_HTTPS" = "true" ] || return 0
  log "申请 HTTPS 证书（${DOMAIN}）"
  apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect --keep-until-expiring
}

open_firewall() {
  if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    log "放行防火墙端口"
    ufw allow "${HTTP_PORT}/tcp" >/dev/null
    [ "$ENABLE_HTTPS" = "true" ] && ufw allow 443/tcp >/dev/null
  fi
  return 0
}

start_services() {
  if ! has_systemd; then
    warn "未检测到 systemd，跳过服务启动。可手动运行：sudo -u ${APP_USER} ${APP_DIR}/backend/.venv/bin/invoice-sorting"
    return 0
  fi
  log "启动服务"
  systemctl daemon-reload
  systemctl enable --quiet "$APP_NAME"
  # 上次崩溃重启触发了启动次数限制时，单元会停在 failed 状态，直接 restart 会被拒绝
  systemctl reset-failed "$APP_NAME" 2>/dev/null || true
  systemctl restart "$APP_NAME"
  systemctl enable --quiet nginx
  if ! { systemctl reload nginx 2>/dev/null || systemctl restart nginx; }; then
    journalctl -u nginx -n 20 --no-pager || true
    ss -ltnp 2>/dev/null | grep -E ":(80|${HTTP_PORT}) " || true
    die "Nginx 启动失败，原因见上方日志；修正后重新执行安装命令即可"
  fi
  wait_until_healthy
}

wait_until_healthy() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1; then
      log "健康检查通过"
      return 0
    fi
    sleep 1
  done
  journalctl -u "$APP_NAME" -n 30 --no-pager || true
  die "服务未能在 30 秒内启动（尝试 ${attempt} 次），请查看上方日志"
}

password_is_set() {
  curl -fsS "http://127.0.0.1:${APP_PORT}/api/auth/status" 2>/dev/null | grep -q '"password_set":true'
}

# 首个管理员的提示。安装命令里从不包含账号密码，首个管理员一律在首次打开网页时设置：
#   单账套 → 为管理员 admin 设置初始密码；SaaS → 在主域名上设置首个平台管理员的用户名与密码。
print_admin_hint() {
  local role="管理员 admin"
  if [ "$DEPLOY_MODE" = "$MODE_SAAS" ]; then
    role="平台管理员（用户名默认 admin）"
  fi
  if password_is_set; then
    echo " ${role}：沿用网页中已设置的密码；其他用户由管理员在网页中添加"
  else
    echo " ${role}：尚未设置密码 ← 请立即打开上面的访问地址完成设置"
    if [ "$DEPLOY_MODE" = "$MODE_SAAS" ]; then
      echo "          （用**主域名**打开，不要带账套子域名；设置完即登录，可从「平台」入口开通账套）"
    fi
    echo "          （设置前任何能访问该地址的人都可以设置，请尽快完成）"
  fi
  return 0
}

# 部署形态与授权状态摘要（单账套且未配授权时只有一行，与现状观感一致）
print_deployment_summary() {
  if [ "$DEPLOY_MODE" = "$MODE_SAAS" ]; then
    echo " 部署形态：多账套（saas）；账套与套餐在平台运营后台管理"
    if [ -n "$TENANT_HOST_SUFFIX" ]; then
      echo " 账套子域名：*.${TENANT_HOST_SUFFIX}（需把泛域名解析到本机，HTTPS 需通配符证书）"
    fi
  else
    echo " 部署形态：单账套（single）；界面不出现账套概念，与升级前一致"
  fi
  if [ -n "$LICENSE_KEY" ] && [ -n "$LICENSE_SERVER" ]; then
    echo " 私有化授权：已配置（校验服务 ${LICENSE_SERVER}，每 ${CHECK_INTERVAL_HOURS} 小时校验，宽限 ${GRACE_DAYS} 天）"
    echo "             授权状态见网页「设置」页；密钥保存在 ${SERVICE_FILE}"
  fi
  return 0
}

print_summary() {
  local scheme="http" host="$DOMAIN" port_suffix=""
  [ "$ENABLE_HTTPS" = "true" ] && scheme="https"
  if [ "$host" = "_" ]; then
    host="$(hostname -I 2>/dev/null | awk '{print $1}')"
    host="${host:-服务器IP}"
  fi
  [ "$scheme" = "http" ] && [ "$HTTP_PORT" != "80" ] && port_suffix=":${HTTP_PORT}"
  cat <<EOF

────────────────────────────────────────────────
 发票账本已就绪
 版本：${TARGET_VERSION}（来源：${SOURCE_CHANNEL}）
 访问地址：${scheme}://${host}${port_suffix}
EOF
  print_admin_hint
  print_deployment_summary
  cat <<EOF
 重置 admin 密码：sudo -u ${APP_USER} env INVOICE_SORTING_DATA_DIR=${DATA_DIR} ${APP_DIR}/backend/.venv/bin/invoice-sorting reset-password
 数据目录：${DATA_DIR}（收件箱：${DATA_DIR}/收件箱）
 当前版本：cat ${VERSION_FILE}
 升级命令：重新执行安装命令即可（默认装最新正式版）
 回滚版本：重新执行安装命令并指定旧版本，例如 | sudo VERSION=v0.1.0 bash
 查看日志：journalctl -u ${APP_NAME} -f
 日志出现 bad marshal data（字节码缓存损坏）时：sudo rm -rf ${PYCACHE_DIR}/* && sudo systemctl restart ${APP_NAME}
────────────────────────────────────────────────
EOF
}

main() {
  check_environment
  install_packages
  prepare_user_and_dirs
  # 切到程序目录：调用者的当前目录（如 /home/xxx）对系统用户 invoice 不可读，
  # uv/pnpm 会在当前目录查找配置文件而报 Permission denied
  cd "$INSTALL_DIR"
  stop_service
  backup_database
  fetch_source
  load_mirrors
  install_uv
  prepare_frontend
  build_app
  verify_backend
  write_service
  write_nginx
  open_firewall
  start_services
  record_version
  enable_https
  print_summary
}

# 供测试使用：置 1 时只定义函数，不执行安装流程
if [ "${INSTALL_SH_SOURCE_ONLY:-0}" != "1" ]; then
  main "$@"
fi
