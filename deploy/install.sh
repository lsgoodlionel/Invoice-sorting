#!/usr/bin/env bash
# 发票账本 · Ubuntu 一键安装 / 升级脚本
#
# 首次安装与升级使用同一条命令（重复执行即升级，数据与登录密码保留）：
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/Invoice-sorting/main/deploy/install.sh | sudo bash
#
# 可选环境变量（写在 sudo 之后，例如 `| sudo DOMAIN=invoice.example.com bash`）：
#   DOMAIN          访问域名，默认 _（任意域名/IP）
#   ENABLE_HTTPS    true 时用 Let's Encrypt 申请证书（需 DOMAIN 与 EMAIL，且域名已解析到本机）
#   EMAIL           证书通知邮箱
#   AUTH_USER       网页登录用户名，默认 admin
#   AUTH_PASSWORD   网页登录密码；首次安装未提供时自动生成并打印；再次提供则重置
#   HTTP_PORT       Nginx 监听端口，默认 80
#   APP_PORT        应用内部端口（仅本机），默认 8765
#   BRANCH          Git 分支，默认 main
#   REPO_URL        仓库地址
#   INSTALL_DIR     程序目录，默认 /opt/invoice-sorting
#   DATA_DIR        数据目录，默认 /var/lib/invoice-sorting
set -euo pipefail

APP_NAME="invoice-sorting"
REPO_URL="${REPO_URL:-https://github.com/lsgoodlionel/Invoice-sorting.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/invoice-sorting}"
APP_DIR="${INSTALL_DIR}/app"
DATA_DIR="${DATA_DIR:-/var/lib/invoice-sorting}"
APP_USER="${APP_USER:-invoice}"
APP_PORT="${APP_PORT:-8765}"
HTTP_PORT="${HTTP_PORT:-80}"
DOMAIN="${DOMAIN:-_}"
ENABLE_HTTPS="${ENABLE_HTTPS:-false}"
EMAIL="${EMAIL:-}"
AUTH_USER="${AUTH_USER:-admin}"
AUTH_PASSWORD="${AUTH_PASSWORD:-}"
NODE_MAJOR=22
MAX_UPLOAD_MB=100
HTPASSWD_FILE="/etc/nginx/${APP_NAME}.htpasswd"
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
}

install_packages() {
  log "安装系统依赖"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq git curl ca-certificates gnupg nginx apache2-utils sqlite3 >/dev/null
  install_node
  install_uv
}

install_node() {
  local current=0
  if command -v node >/dev/null 2>&1; then
    current="$(node -p 'process.versions.node.split(".")[0]')"
  fi
  if [ "$current" -lt 20 ]; then
    log "安装 Node.js ${NODE_MAJOR}"
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - >/dev/null
    apt-get install -y -qq nodejs >/dev/null
  fi
  corepack enable >/dev/null 2>&1 || npm install -g pnpm >/dev/null
}

install_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    log "安装 uv"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
  fi
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

build_app() {
  log "安装后端依赖（Python 3.12）"
  as_app env UV_PYTHON_INSTALL_DIR="${INSTALL_DIR}/python" UV_CACHE_DIR="${INSTALL_DIR}/.cache/uv" \
    uv sync --project "${APP_DIR}/backend" --frozen --no-dev --quiet
  log "构建前端"
  as_app env COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm --dir "${APP_DIR}/frontend" install --frozen-lockfile --silent
  as_app env COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm --dir "${APP_DIR}/frontend" build >/dev/null
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

write_htpasswd() {
  if [ -n "$AUTH_PASSWORD" ]; then
    htpasswd -bcB "$HTPASSWD_FILE" "$AUTH_USER" "$AUTH_PASSWORD" >/dev/null 2>&1
    GENERATED_PASSWORD="$AUTH_PASSWORD"
  elif [ ! -s "$HTPASSWD_FILE" ]; then
    GENERATED_PASSWORD="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)"
    htpasswd -bcB "$HTPASSWD_FILE" "$AUTH_USER" "$GENERATED_PASSWORD" >/dev/null 2>&1
  fi
  chown root:www-data "$HTPASSWD_FILE"
  chmod 640 "$HTPASSWD_FILE"
}

write_nginx() {
  log "配置 Nginx（带登录密码保护）"
  write_htpasswd
  cat >"$NGINX_SITE" <<EOF
server {
    listen ${HTTP_PORT};
    listen [::]:${HTTP_PORT};
    server_name ${DOMAIN};

    client_max_body_size ${MAX_UPLOAD_MB}m;

    auth_basic "发票账本";
    auth_basic_user_file ${HTPASSWD_FILE};

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
  if [ "$DOMAIN" = "_" ] && [ "$HTTP_PORT" = "80" ]; then
    rm -f /etc/nginx/sites-enabled/default
  fi
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
  systemctl reload nginx 2>/dev/null || systemctl restart nginx
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
 登录用户：${AUTH_USER}
EOF
  if [ -n "${GENERATED_PASSWORD:-}" ]; then
    echo " 登录密码：${GENERATED_PASSWORD}   ← 请妥善保存，仅显示这一次"
  else
    echo " 登录密码：沿用之前设置（重置：AUTH_PASSWORD=新密码 重新执行本脚本）"
  fi
  cat <<EOF
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
  backup_database
  fetch_source
  build_app
  write_service
  write_nginx
  open_firewall
  start_services
  enable_https
  print_summary
}

main "$@"
