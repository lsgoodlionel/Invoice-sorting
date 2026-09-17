#!/usr/bin/env bash
# 下载 CI 预构建的前端（Release「frontend-dist」），校验与本地前端代码版本一致后放到 frontend/dist。
# 成功返回 0；网络失败或版本不一致返回非 0（调用方可退回本地构建）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
URL="${FRONTEND_DIST_URL:-https://github.com/lsgoodlionel/Invoice-sorting/releases/download/frontend-dist/frontend-dist.tar.gz}"

key="$(git log -1 --format=%H -- frontend 2>/dev/null || true)"
if [ -z "$key" ]; then
  echo "无法确定前端代码版本（需要 git 仓库）" >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "==> 下载预构建前端（${URL}）" >&2
if ! curl -fL -# --retry 5 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 900 \
  -o "$work/frontend-dist.tar.gz" "$URL"; then
  echo "预构建前端下载失败" >&2
  exit 1
fi
tar -xzf "$work/frontend-dist.tar.gz" -C "$work"
built="$(cat "$work/BUILD_COMMIT" 2>/dev/null || true)"
if [ "$built" != "$key" ]; then
  echo "预构建前端版本（${built:-未知}）与代码（${key}）不一致" >&2
  exit 1
fi
[ -f "$work/dist/index.html" ] || { echo "预构建前端内容不完整" >&2; exit 1; }
rm -rf frontend/dist
mv "$work/dist" frontend/dist
echo "==> 已使用预构建前端（${key:0:7}）" >&2
