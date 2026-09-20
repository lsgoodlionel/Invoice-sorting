#!/usr/bin/env bash
# 启动前自检与失败提示（由 systemd 调用，以应用用户身份运行）。
#
#   startup-check.sh                 ExecStartPre：试导入后端，失败就清空字节码缓存再试一次
#   startup-check.sh --failure-hint  ExecStopPost：服务非正常退出时在日志里给出排查提示
#
# 设计要点：
# - **幂等**：可以反复执行，正常情况下什么都不做、不输出。
# - **不阻塞恢复**：任何情况下都以 0 退出，自检失败也让服务继续尝试启动。
# - 字节码缓存集中在 PYTHONPYCACHEPREFIX 指向的目录，损坏时整目录删掉即可（不碰代码与数据）。
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT}/backend/.venv"
PYTHON="${VENV_DIR}/bin/python"
CACHE_DIR="${PYTHONPYCACHEPREFIX:-/var/cache/invoice-sorting/pycache}"
SERVICE_NAME="invoice-sorting"
APP_BIN="${VENV_DIR}/bin/invoice-sorting"
DIAGNOSE_TIMEOUT=60
# 自检导入的模块：应用入口 + 历史上出现过 .pyc 损坏的第三方包
CHECK_SNIPPET='import invoice_sorting.main, openpyxl'

note() { printf '[启动自检] %s\n' "$*" >&2; }

print_failure_hint() {
  # SERVICE_RESULT 由 systemd 在 ExecStopPost 时注入；正常停止不打扰
  local result="${SERVICE_RESULT:-success}"
  [ "$result" != "success" ] || return 0
  cat >&2 <<EOF
[异常退出] ${SERVICE_NAME} 非正常退出（${result}）。排查顺序：
  1. 看日志：journalctl -u ${SERVICE_NAME} -n 50 --no-pager
  2. 日志里有 "bad marshal data" 或 "EOFError: marshal data too short" → Python 字节码缓存损坏：
       sudo rm -rf ${CACHE_DIR}/* && sudo systemctl restart ${SERVICE_NAME}
  3. 连续失败次数超过阈值后 systemd 会停止自动重启（日志显示 start request repeated too quickly），
     修复后执行：sudo systemctl reset-failed ${SERVICE_NAME} && sudo systemctl start ${SERVICE_NAME}
  4. 依赖损坏时重新执行一键安装命令即可修复（数据不受影响）。
EOF
  collect_crash_diagnostics
}

# 非正常退出后留一份**脱敏**诊断包（docs/日志与故障上报_设计.md）。
# - 只有同时配置了 INVOICE_SORTING_LOG_REPO 与 INVOICE_SORTING_LOG_TOKEN 才会上传，默认只存本机；
# - 幂等：反复执行只是多生成一个包，诊断包目录自动只保留最近 10 个；
# - 不阻塞恢复：超时即放弃，任何失败都只打印一行提示并返回 0。
collect_crash_diagnostics() {
  [ -x "$APP_BIN" ] || return 0
  local args=(diagnose --reason=crash)
  if [ -n "${INVOICE_SORTING_LOG_REPO:-}" ] && [ -n "${INVOICE_SORTING_LOG_TOKEN:-}" ]; then
    args+=(--upload)
  fi
  local output
  # 诊断包里不会出现令牌；这里也只回显命令自己的输出，不打印任何环境变量
  if output="$(run_limited "$APP_BIN" "${args[@]}" 2>&1)"; then
    printf '%s\n' "$output" | tail -n 3 >&2
  else
    note "生成崩溃诊断包失败（不影响服务恢复）："
    printf '%s\n' "$output" | tail -n 3 >&2
  fi
  return 0
}

# 有 timeout 就限时执行，没有就直接跑（诊断包生成通常在 1 秒内完成）
run_limited() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$DIAGNOSE_TIMEOUT" "$@"
  else
    "$@"
  fi
}

can_import() { "$PYTHON" -c "$CHECK_SNIPPET" 2>&1; }

clear_bytecode_cache() {
  # 集中缓存目录整体清空；再顺手清掉历史遗留的 __pycache__（老版本没有集中缓存）
  [ -n "$CACHE_DIR" ] && rm -rf -- "${CACHE_DIR:?}"/* 2>/dev/null
  find "$VENV_DIR" "${ROOT}/backend/src" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
  return 0
}

run_startup_check() {
  if [ ! -x "$PYTHON" ]; then
    note "未找到 ${PYTHON}，跳过自检"
    return 0
  fi
  local output
  output="$(can_import)" && return 0
  note "后端导入失败，清理字节码缓存后重试："
  printf '%s\n' "$output" | tail -n 3 >&2
  clear_bytecode_cache
  if output="$(can_import)"; then
    note "清理字节码缓存后已恢复正常"
    return 0
  fi
  note "清理缓存后仍无法导入后端，服务可能起不来；重新执行一键安装命令可修复依赖。错误如下："
  printf '%s\n' "$output" | tail -n 5 >&2
  return 0
}

main() {
  mkdir -p "$CACHE_DIR" 2>/dev/null || true
  case "${1:-}" in
    --failure-hint) print_failure_hint ;;
    *) run_startup_check ;;
  esac
  return 0
}

main "$@"
exit 0
