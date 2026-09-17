#!/usr/bin/env bash
# 下载源自动选择：对官方源与国内镜像实测响应时间，选择最快可用者。
# 用法：source scripts/lib/mirrors.sh && select_mirrors
#
# 环境变量：
#   MIRROR=auto（默认，测速选择）| cn（强制国内镜像）| global（强制官方源）
#   PYPI_INDEX / NPM_REGISTRY / NODE_DIST / PYTHON_MIRROR  手工指定时跳过测速
#
# 选择结果导出为：PYPI_INDEX、NPM_REGISTRY、NODE_DIST、PYTHON_MIRROR（官方时为空）

MIRROR="${MIRROR:-auto}"
PROBE_TIMEOUT=6

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

# 探测地址：取各源上体积很小的资源，避免大文件拖慢测速
_probe_url() {
  case "$1" in
    */pypi/simple | */simple) echo "$1/six/" ;;
    *registry.npm*) echo "$1/is-number" ;;
    */node | */dist) echo "$1/latest-v22.x/SHASUMS256.txt" ;;
    */releases/download) echo "${1%/download}/latest" ;;
    *python-build-standalone) echo "$1/" ;;
    *) echo "$1" ;;
  esac
}

# 输出毫秒耗时；失败输出空
_probe_ms() {
  local url seconds
  url="$(_probe_url "$1")"
  seconds="$(curl -fsSL -o /dev/null -w '%{time_total}' --max-time "$PROBE_TIMEOUT" "$url" 2>/dev/null)" || return 0
  awk -v s="$seconds" 'BEGIN { printf "%d", s * 1000 }'
}

# 从候选列表中选择：global 取第一个（官方），cn 取第二个（首选国内镜像），auto 取最快
_pick() {
  local label="$1"; shift
  local candidates=("$@") best="" best_ms="" url ms shown
  case "$MIRROR" in
    global) echo "${candidates[0]}"; return ;;
    cn) echo "${candidates[1]}"; return ;;
  esac
  for url in "${candidates[@]}"; do
    ms="$(_probe_ms "$url")"
    shown="不可用"
    [ -n "$ms" ] && shown="${ms}ms"
    printf '    %-8s %-72s %s\n' "$label" "$url" "$shown" >&2
    if [ -n "$ms" ] && { [ -z "$best_ms" ] || [ "$ms" -lt "$best_ms" ]; }; then
      best="$url"; best_ms="$ms"
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
    PYTHON_MIRROR="$(_pick Python "${PYTHON_CANDIDATES[@]}")"
    [ "$PYTHON_MIRROR" = "${PYTHON_CANDIDATES[0]}" ] && PYTHON_MIRROR=""
  fi
  export PYPI_INDEX NPM_REGISTRY NODE_DIST PYTHON_MIRROR
  {
    echo "    → PyPI:    $PYPI_INDEX"
    echo "    → npm:     $NPM_REGISTRY"
    echo "    → Node.js: $NODE_DIST"
    echo "    → Python:  ${PYTHON_MIRROR:-官方 GitHub}"
  } >&2
}
