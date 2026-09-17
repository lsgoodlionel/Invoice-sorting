#!/usr/bin/env bash
# 安装依赖并构建前端（本机开发与服务器部署共用），自动选择最快的下载源。
#
#   scripts/setup.sh            安装后端依赖（含 OCR）+ 前端依赖并构建
#   NO_OCR=1 scripts/setup.sh   不安装 OCR（截图凭证只按文件名识别）
#   MIRROR=cn scripts/setup.sh  强制国内镜像；MIRROR=global 强制官方源
#   FRONTEND_BUILD=local        本地构建前端（默认，开发时反映未提交的前端改动）
#   FRONTEND_BUILD=prebuilt     只用 CI 预构建前端（无需 Node.js）；auto：优先预构建，失败再本地构建
#   SKIP_FRONTEND=1             跳过前端
#
# 需要：uv；本地构建前端时还需要 Node.js ≥ 20 与 pnpm。版本严格按 uv.lock / pnpm-lock.yaml 安装。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"  # 在仓库目录内运行，避免读取调用者目录中的 uv.toml / .npmrc
# 慢速网络下放宽下载超时（uv 默认 30 秒）
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-300}" UV_HTTP_RETRIES="${UV_HTTP_RETRIES:-5}"
# shellcheck source=lib/mirrors.sh
. "$ROOT/scripts/lib/mirrors.sh"

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }

install_backend() {
  local backend="$ROOT/backend" requirements extras=()
  [ "${NO_OCR:-0}" = "1" ] || extras=(--extra ocr)
  requirements="$(mktemp)"

  log "安装后端依赖（${PYPI_INDEX}）"
  if [ -n "$PYTHON_MIRROR" ]; then
    export UV_PYTHON_INSTALL_MIRROR="$PYTHON_MIRROR"
  fi
  if [ ! -x "$backend/.venv/bin/python" ]; then
    uv venv --quiet --python 3.12 "$backend/.venv"
  fi
  # 按锁文件导出精确版本（含哈希），再从选中的源安装，保证与锁文件一致
  uv export --quiet --project "$backend" --frozen --no-dev --no-emit-project \
    --format requirements-txt "${extras[@]}" -o "$requirements"
  uv pip install --quiet --python "$backend/.venv/bin/python" \
    --index-url "$PYPI_INDEX" -r "$requirements"
  rm -f "$requirements"
  uv pip install --quiet --python "$backend/.venv/bin/python" --no-deps -e "$backend"
}

build_frontend_locally() {
  local frontend="$ROOT/frontend"
  command -v pnpm >/dev/null 2>&1 || { echo "未找到 pnpm，请先执行 corepack enable" >&2; exit 1; }
  log "安装前端依赖（${NPM_REGISTRY}）"
  # 慢速网络：放宽超时并重试；corepack 按 package.json 固定的 pnpm 版本下载，不查询最新版
  export COREPACK_NPM_REGISTRY="$NPM_REGISTRY" COREPACK_ENABLE_DOWNLOAD_PROMPT=0
  export npm_config_fetch_retries=5 npm_config_fetch_timeout=300000
  pnpm --dir "$frontend" install --frozen-lockfile --silent --registry "$NPM_REGISTRY"
  log "构建前端"
  pnpm --dir "$frontend" build >/dev/null
}

install_frontend() {
  [ "${SKIP_FRONTEND:-0}" = "1" ] && return 0
  case "${FRONTEND_BUILD:-local}" in
    prebuilt) bash "$ROOT/scripts/fetch-frontend.sh" ;;
    auto) bash "$ROOT/scripts/fetch-frontend.sh" || build_frontend_locally ;;
    *) build_frontend_locally ;;
  esac
}

main() {
  command -v uv >/dev/null 2>&1 || { echo "未找到 uv，请先安装：https://docs.astral.sh/uv/" >&2; exit 1; }
  select_mirrors
  install_backend
  install_frontend
  log "完成。启动：$ROOT/backend/.venv/bin/invoice-sorting"
}

main "$@"
