#!/bin/sh
# 容器入口：启动前检查数据目录是否可写，给出明确的中文提示，然后执行真正的命令。
set -eu

DATA_DIR="${INVOICE_SORTING_DATA_DIR:-/data}"

if ! mkdir -p "$DATA_DIR" 2>/dev/null || [ ! -w "$DATA_DIR" ]; then
  cat >&2 <<MSG
[错误] 数据目录 ${DATA_DIR} 不可写。
容器以非 root 用户运行（UID $(id -u)，GID $(id -g)）。
若用宿主机目录挂载数据，请先在宿主机执行：
    sudo mkdir -p <宿主机目录>
    sudo chown -R $(id -u):$(id -g) <宿主机目录>
使用命名卷（docker-compose.yml 的默认方式）时不需要额外授权。
MSG
  exit 1
fi

exec "$@"
