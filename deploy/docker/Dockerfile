# syntax=docker/dockerfile:1.7
# 发票账本 · 容器镜像（多阶段构建）
#
# 构建上下文是**仓库根目录**，例如：
#   docker build -f deploy/docker/Dockerfile -t invoice-sorting:local .
#   docker compose -f deploy/docker/docker-compose.yml build
#
# 可选构建参数（--build-arg）：
#   FRONTEND_SOURCE=build     前端在容器内构建（默认）；prebuilt 则直接用仓库里已有的 frontend/dist
#   INSTALL_OCR=true          安装截图文字识别依赖（约增加 300MB）；false 则不装
#   PYPI_INDEX / NPM_REGISTRY 下载源，国内网络可换成镜像地址
#
# 镜像内不包含任何密钥：授权密钥、域名等一律在运行时通过环境变量传入。

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG NODE_IMAGE=node:22-bookworm-slim
ARG FRONTEND_SOURCE=build

# ---------- 前端：容器内构建 ----------
FROM ${NODE_IMAGE} AS frontend-build
ARG NPM_REGISTRY=https://registry.npmjs.org
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    COREPACK_NPM_REGISTRY=${NPM_REGISTRY} \
    npm_config_fetch_retries=5 \
    npm_config_fetch_timeout=300000
WORKDIR /src
# 先装依赖再拷源码：源码改动时依赖层仍可复用
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile --registry "${NPM_REGISTRY}"
COPY frontend/ ./
RUN pnpm build && mkdir -p /out && cp -r dist /out/dist

# ---------- 前端：使用仓库中已构建好的 dist ----------
FROM ${PYTHON_IMAGE} AS frontend-prebuilt
WORKDIR /out
# 需要先在宿主机执行 pnpm --dir frontend build（或 scripts/fetch-frontend.sh）生成 frontend/dist
COPY frontend/dist /out/dist

# 按 FRONTEND_SOURCE 选择上面两种来源之一
FROM frontend-${FRONTEND_SOURCE} AS frontend

# ---------- 后端依赖：uv 按锁文件精确安装到 /opt/venv ----------
FROM ${PYTHON_IMAGE} AS backend
ARG PYPI_INDEX=https://pypi.org/simple
ARG INSTALL_OCR=true
ENV UV_NO_CONFIG=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_HTTP_RETRIES=5 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# 慢速网络下放宽超时并重试，避免半途 ReadTimeout 让整个构建失败
RUN pip install --no-cache-dir --timeout 120 --retries 10 --index-url "${PYPI_INDEX}" uv
WORKDIR /src/backend
# 只拷元数据即可导出锁定版本，源码改动不会让依赖层失效
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN set -eu; \
    if [ "${INSTALL_OCR}" = "true" ]; then set -- --extra ocr; else set -- ; fi; \
    uv export --frozen --no-dev --no-emit-project --format requirements-txt "$@" \
      -o /tmp/requirements.txt; \
    uv venv /opt/venv; \
    uv pip install --python /opt/venv/bin/python --index-url "${PYPI_INDEX}" \
      -r /tmp/requirements.txt; \
    rm -f /tmp/requirements.txt
COPY backend/src ./src
RUN uv pip install --python /opt/venv/bin/python --no-deps .

# ---------- 运行时 ----------
FROM ${PYTHON_IMAGE} AS runtime
ARG INSTALL_OCR=true
ARG APP_UID=10001
ARG APP_GID=10001
LABEL org.opencontainers.image.title="invoice-sorting" \
      org.opencontainers.image.description="发票账本 · 个人发票报销管理工具" \
      org.opencontainers.image.source="https://github.com/lsgoodlionel/Invoice-sorting"

# sqlite3 用于备份与排查；libgl1/libglib2.0-0 是 OCR（opencv）运行所需
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates tzdata sqlite3; \
    if [ "${INSTALL_OCR}" = "true" ]; then \
      apt-get install -y --no-install-recommends libgl1 libglib2.0-0; \
    fi; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    groupadd --gid "${APP_GID}" invoice; \
    useradd --uid "${APP_UID}" --gid "${APP_GID}" --home-dir /app --shell /usr/sbin/nologin invoice; \
    mkdir -p /app /data; \
    chown invoice:invoice /app /data; \
    chmod 750 /data

COPY --from=backend /opt/venv /opt/venv
COPY --from=frontend --chown=invoice:invoice /out/dist /app/frontend/dist
COPY deploy/docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

ENV PATH=/opt/venv/bin:$PATH \
    TZ=Asia/Shanghai \
    INVOICE_SORTING_DATA_DIR=/data \
    INVOICE_SORTING_HOST=0.0.0.0 \
    INVOICE_SORTING_PORT=8765 \
    INVOICE_SORTING_OPEN_BROWSER=false \
    INVOICE_SORTING_FRONTEND_DIST=/app/frontend/dist

WORKDIR /app
# 未显式挂载时也不会丢数据（会落到匿名卷）；正式部署请按 docker-compose.yml 挂命名卷或宿主目录
VOLUME ["/data"]
USER invoice
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('INVOICE_SORTING_PORT','8765'), timeout=3).status == 200 else 1)"
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["invoice-sorting"]
