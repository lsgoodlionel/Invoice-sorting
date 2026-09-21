#!/usr/bin/env bash
# install.sh 的回归测试：读取 /etc/os-release 不得污染脚本自身的变量。
#   用法：bash deploy/tests/install_env_test.sh
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SH="${SCRIPT_DIR}/../install.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Ubuntu 24.04 真实内容：VERSION 与脚本的版本参数同名
cat >"${TMP_DIR}/os-release" <<'OSREL'
PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
OSREL

failures=0
check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    printf '  ok   %s\n' "$name"
  else
    printf '  FAIL %s：期望 %s，实际 %s\n' "$name" "$expected" "$actual"
    failures=$((failures + 1))
  fi
}

# 只加载函数定义，不执行安装
export INSTALL_SH_SOURCE_ONLY=1
export OS_RELEASE_FILE="${TMP_DIR}/os-release"
export VERSION="v0.2.0"
# shellcheck disable=SC1090
. "$INSTALL_SH"

check "读取 ID" "ubuntu" "$(os_release_field ID)"
check "读取 PRETTY_NAME" "Ubuntu 24.04.5 LTS" "$(os_release_field PRETTY_NAME)"
check "缺失字段返回空" "" "$(os_release_field NOT_THERE)"

os_release_field ID >/dev/null
check "VERSION 未被 os-release 覆盖" "v0.2.0" "$VERSION"

# 版本校验必须仍然通过（这正是当初失败的地方）
# die 会直接 exit，所以放进子 shell 里判断
if ( check_source_settings ) >/dev/null 2>&1; then
  printf '  ok   check_source_settings 通过\n'
else
  printf '  FAIL check_source_settings 失败（VERSION=%s）\n' "$VERSION"
  failures=$((failures + 1))
fi

# 非法版本仍要被拦下
VERSION="24.04.5 LTS (Noble Numbat)"
if ( check_source_settings ) >/dev/null 2>&1; then
  printf '  FAIL 非法 VERSION 未被拦截\n'
  failures=$((failures + 1))
else
  printf '  ok   非法 VERSION 被拦截\n'
fi

[ "$failures" -eq 0 ] || { printf '%d 项失败\n' "$failures" >&2; exit 1; }
printf '全部通过\n'
