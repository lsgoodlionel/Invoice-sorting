#!/usr/bin/env bash
# 下载源自动选择：对官方源与国内镜像实测真实文件的下载速度，选择最快者。
# 用法：source scripts/lib/mirrors.sh && select_mirrors
#
# 环境变量：
#   MIRROR=auto（默认，测速选择）| cn（强制国内镜像）| global（强制官方源）
#   PYPI_INDEX / NPM_REGISTRY / NODE_DIST / PYTHON_MIRROR  手工指定时跳过测速
#
# 选择结果导出为：PYPI_INDEX、NPM_REGISTRY、NODE_DIST、PYTHON_MIRROR（官方时为空）

MIRROR="${MIRROR:-auto}"
PROBE_TIMEOUT=5

PYPI_CANDIDATES=(
  "https://pypi.org/simple"
  "https://mirrors.aliyun.com/pypi/simple"
  "https://pypi.tuna.tsinghua.edu.cn/simple"
)
NPM_CANDIDATES=(
  "https://registry.npmjs.org"
  "https://registry.npmmirror.com"
)
NODE_CANDIDATES=(
  "https://nodejs.org/dist"
  "https://npmmirror.com/mirrors/node"
)
# Python 解释器（python-build-standalone）下载镜像；官方为 GitHub Releases
PYTHON_CANDIDATES=(
  "https://github.com/astral-sh/python-build-standalone/releases/download"
  "https://registry.npmmirror.com/-/binary/python-build-standalone"
)

# 测速样本：各源上同一个约 300–500KB 的真实文件（只下载前 500KB），按实际下载速度比较。
# 注意 PyPI 的包文件与索引页不在同一主机，必须测包文件本身。
PYPI_SAMPLE="packages/eb/47/c95ffc2009878c7aac0c5e08528022dcb885933252a88b5f170058014464/pydantic-2.13.5-py3-none-any.whl"
NPM_SAMPLE="lodash/-/lodash-4.17.21.tgz"
NODE_SAMPLE="index.json"
PYTHON_SAMPLE="20250317/cpython-3.12.9+20250317-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PROBE_BYTES=499999

_probe_url() {
  case "$1" in
    https://pypi.org/simple) echo "https://files.pythonhosted.org/${PYPI_SAMPLE}" ;;
    */simple) echo "${1%/simple}/${PYPI_SAMPLE}" ;;
    *registry.npm*) echo "$1/${NPM_SAMPLE}" ;;
    */node | */dist) echo "$1/${NODE_SAMPLE}" ;;
    *python-build-standalone*) echo "$1/${PYTHON_SAMPLE}" ;;
    *) echo "$1" ;;
  esac
}

# 输出下载速度（KB/s，整数）；超时也按已下载部分计算；完全失败输出 0
_probe_kbps() {
  local url result code bytes speed
  url="$(_probe_url "$1")"
  result="$(curl -sL -r "0-${PROBE_BYTES}" -o /dev/null --max-time "$PROBE_TIMEOUT" \
    -w '%{http_code} %{size_download} %{speed_download}' "$url" 2>/dev/null || true)"
  read -r code bytes speed <<<"${result:-000 0 0}"
  case "$code" in
    200 | 206) ;;
    *) echo 0; return ;;
  esac
  [ "${bytes%.*}" -gt 0 ] 2>/dev/null || { echo 0; return; }
  awk -v s="$speed" 'BEGIN { printf "%d", s / 1024 }'
}

# 从候选列表中选择：global 取第一个（官方），cn 取第二个（首选国内镜像），auto 取下载最快
_pick() {
  local label="$1"; shift
  local candidates=("$@") best="" best_kbps=0 url kbps shown
  case "$MIRROR" in
    global) echo "${candidates[0]}"; return ;;
    cn) echo "${candidates[1]}"; return ;;
  esac
  for url in "${candidates[@]}"; do
    kbps="$(_probe_kbps "$url")"
    shown="不可用"
    [ "$kbps" -gt 0 ] && shown="${kbps} KB/s"
    printf '    %-8s %-60s %s\n' "$label" "$url" "$shown" >&2
    if [ "$kbps" -gt "$best_kbps" ]; then
      best="$url"; best_kbps="$kbps"
    fi
  done
  echo "${best:-${candidates[0]}}"
}

select_mirrors() {
  echo "==> 选择下载源（MIRROR=${MIRROR}）" >&2
  PYPI_INDEX="${PYPI_INDEX:-$(_pick PyPI "${PYPI_CANDIDATES[@]}")}"
  NPM_REGISTRY="${NPM_REGISTRY:-$(_pick npm "${NPM_CANDIDATES[@]}")}"
  NODE_DIST="${NODE_DIST:-$(_pick Node.js "${NODE_CANDIDATES[@]}")}"
  if [ -z "${PYTHON_MIRROR+x}" ]; then
    PYTHON_MIRROR=""
    # 已有 Python 3.12（如 Ubuntu 24.04 系统自带）时无需下载解释器，跳过测速
    if ! uv python find 3.12 >/dev/null 2>&1; then
      PYTHON_MIRROR="$(PROBE_TIMEOUT=10 _pick Python "${PYTHON_CANDIDATES[@]}")"
      [ "$PYTHON_MIRROR" = "${PYTHON_CANDIDATES[0]}" ] && PYTHON_MIRROR=""
    fi
  fi
  export PYPI_INDEX NPM_REGISTRY NODE_DIST PYTHON_MIRROR
  {
    echo "    → PyPI:    $PYPI_INDEX"
    echo "    → npm:     $NPM_REGISTRY"
    echo "    → Node.js: $NODE_DIST"
    echo "    → Python:  ${PYTHON_MIRROR:-官方 GitHub（或使用已安装的 3.12）}"
  } >&2
}
