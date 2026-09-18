#!/usr/bin/env bash
# 发票账本 · Ubuntu 一键安装 / 升级脚本
#
# 首次安装与升级使用同一条命令（重复执行即升级，数据与登录密码保留）。
# 安装完成后打开网页为管理员 admin 设置初始密码，再在「设置 → 用户管理」添加其他用户：
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Invoice-sorting/main/deploy/install.sh | sudo bash
#
# 可选环境变量（写在 sudo 之后，例如 `| sudo DOMAIN=invoice.example.com bash`）：
#   DOMAIN          访问域名，默认 _（任意域名/IP）
#   ENABLE_HTTPS    true 时用 Let's Encrypt 申请证书（需 DOMAIN 与 EMAIL，且域名已解析到本机）
#   EMAIL           证书通知邮箱
#   HTTP_PORT       对外访问端口（Nginx），默认 8765；启用 HTTPS 时默认 80（证书验证需要）
#   APP_PORT        应用内部端口（仅本机），默认 18765
#   BRANCH          Git 分支，默认 main
#   REPO_URL        仓库地址
#   MIRROR          下载源：auto（默认，测速选择官方源或国内镜像）| cn | global
#   NO_OCR          设为 1 时不安装截图文字识别（OCR）
#   FRONTEND_BUILD  prebuilt（默认：下载 CI 预构建前端，失败再本地构建）| local（服务器上构建）
#   INSTALL_DIR     程序目录，默认 /opt/invoice-sorting
#   DATA_DIR        数据目录，默认 /var/lib/invoice-sorting
set -Eeuo pipefail
# 任何命令意外失败都打印位置，避免静默退出
trap 'printf "\033[1;31m[错误]\033[0m 安装中断：第 %s 行命令失败：%s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

APP_NAME="invoice-sorting"
REPO_URL="${REPO_URL:-https://github.com/lsgoodlionel/Invoice-sorting.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/invoice-sorting}"
APP_DIR="${INSTALL_DIR}/app"
DATA_DIR="${DATA_DIR:-/var/lib/invoice-sorting}"
APP_USER="${APP_USER:-invoice}"
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
MAX_UPLOAD_MB=100
LEGACY_HTPASSWD_FILE="/etc/nginx/${APP_NAME}.htpasswd"  # 旧版 Nginx 登录弹窗，升级时删除
NGINX_SITE="/etc/nginx/sites-available/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
BACKUP_KEEP=10

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[错误]\033[0m %s\n' "$*" >&2; exit 1; }

as_app() { runuser -u "$APP_USER" -- env HOME="$INSTALL_DIR" PATH="/usr/local/bin:/usr/bin:/bin" "$@"; }
has_systemd() { [ -d /run/systemd/system ]; }

check_environment() {
  [ "$(id -u)" -eq 0 ] || die "请使用 root 运行（在命令前加 sudo）"
  [ -r /etc/os-release ] || die "无法识别操作系统"
  # shellcheck disable=SC1091
  . /etc/os-release
  [ "${ID:-}" = "ubuntu" ] || warn "本脚本针对 Ubuntu 22.04/24.04 编写，当前系统：${PRETTY_NAME:-未知}"
  if [ "$ENABLE_HTTPS" = "true" ] && { [ "$DOMAIN" = "_" ] || [ -z "$EMAIL" ]; }; then
    die "启用 HTTPS 需要同时设置 DOMAIN 与 EMAIL"
  fi
  [ "$HTTP_PORT" != "$APP_PORT" ] || die "HTTP_PORT 与 APP_PORT 不能相同（当前均为 ${APP_PORT}）"
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
  mkdir -p "$INSTALL_DIR" "$DATA_DIR"
  chown "$APP_USER:$APP_USER" "$INSTALL_DIR"
  chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
  chmod 750 "$DATA_DIR"
}

backup_database() {
  local db="${DATA_DIR}/invoice.db"
  [ -f "$db" ] || return 0
  local dir="${DATA_DIR}/备份"
  local target
  target="${dir}/upgrade_$(date +%Y%m%d_%H%M%S).db"
  mkdir -p "$dir"
  log "升级前备份数据库 → ${target}"
  sqlite3 "$db" ".backup '${target}'"
  chown "$APP_USER:$APP_USER" "$dir" "$target"
  # 仅保留最近若干份升级备份
  find "$dir" -maxdepth 1 -name 'upgrade_*.db' -printf '%T@ %p\n' | sort -rn |
    tail -n +"$((BACKUP_KEEP + 1))" | cut -d' ' -f2- | xargs -r rm -f
}

fetch_source() {
  if [ -d "${APP_DIR}/.git" ]; then
    log "更新代码（${BRANCH}）"
    as_app git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
    as_app git -C "$APP_DIR" reset --quiet --hard "origin/${BRANCH}"
  else
    log "下载代码 ${REPO_URL}"
    as_app git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  fi
  log "当前版本：$(as_app git -C "$APP_DIR" log -1 --format='%h %s')"
}

prepare_frontend() {
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

verify_backend() {
  # 清除 .pyc 缓存后重新编译并试导入；缓存损坏（bad marshal data）或依赖不完整时重建虚拟环境一次
  local venv="${APP_DIR}/backend/.venv"
  local attempt
  for attempt in 1 2; do
    find "$venv" "${APP_DIR}/backend/src" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
    as_app "$venv/bin/python" -m compileall -q "$venv/lib" "${APP_DIR}/backend/src" >/dev/null 2>&1 || true
    if as_app "$venv/bin/python" -c "import invoice_sorting.main" 2>/tmp/invoice-sorting-import.log; then
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
  # UV_NO_CONFIG：不读取任何 uv.toml，避免受调用者目录或用户配置影响
  as_app env MIRROR="$MIRROR" NO_OCR="${NO_OCR:-0}" UV_NO_CONFIG=1 \
    SKIP_FRONTEND="${FRONTEND_READY:-0}" FRONTEND_BUILD=local \
    PYPI_INDEX="$PYPI_INDEX" NPM_REGISTRY="$NPM_REGISTRY" NODE_DIST="$NODE_DIST" \
    PYTHON_MIRROR="$PYTHON_MIRROR" \
    UV_PYTHON_INSTALL_DIR="${INSTALL_DIR}/python" UV_CACHE_DIR="${INSTALL_DIR}/.cache/uv" \
    bash "${APP_DIR}/scripts/setup.sh"
}

write_service() {
  log "配置 systemd 服务"
  cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=发票账本（个人发票报销管理）
After=network.target

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
ExecStart=${APP_DIR}/backend/.venv/bin/invoice-sorting
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
ReadWritePaths=${DATA_DIR}

[Install]
WantedBy=multi-user.target
EOF
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
    server_name ${DOMAIN};

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
 访问地址：${scheme}://${host}${port_suffix}
EOF
  if password_is_set; then
    echo " 管理员：admin（沿用网页中已设置的密码；其他用户由管理员在网页中添加）"
  else
    echo " 管理员：admin，尚未设置密码 ← 请立即打开上面的访问地址，为 admin 设置初始密码"
    echo "          （设置前任何能访问该地址的人都可以设置，请尽快完成）"
  fi
  cat <<EOF
 重置 admin 密码：sudo -u ${APP_USER} env INVOICE_SORTING_DATA_DIR=${DATA_DIR} ${APP_DIR}/backend/.venv/bin/invoice-sorting reset-password
 数据目录：${DATA_DIR}（收件箱：${DATA_DIR}/收件箱）
 升级命令：重新执行安装命令即可
 查看日志：journalctl -u ${APP_NAME} -f
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
  enable_https
  print_summary
}

main "$@"
