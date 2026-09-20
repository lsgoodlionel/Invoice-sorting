# Docker 交付

用容器跑「发票账本」。完整运维说明见 [部署与运维](../../docs/部署与运维.md)。

## 快速开始

```bash
cd deploy/docker
cp .env.example .env     # 不改也能跑：默认单账套、不校验授权
docker compose up -d --build
```

打开 `http://服务器IP:8765`，首次访问为管理员 `admin` 设置初始密码。

需要在前面再挡一层 Nginx（统一端口、上传上限、以后接 HTTPS）：

```bash
docker compose --profile nginx up -d --build
```

启用 nginx 时建议在 `.env` 里把应用端口收回本机：`APP_PUBLISH=127.0.0.1:18765`。

## 目录内容

| 文件 | 作用 |
| --- | --- |
| `Dockerfile` | 多阶段镜像：前端构建（或用预构建 dist）+ uv 按锁文件装后端 + 精简运行时 |
| `Dockerfile.dockerignore` | 构建上下文过滤；已排除 `.env`、虚拟环境、数据库等 |
| `docker-compose.yml` | 应用服务 + 可选 Nginx（`--profile nginx`），数据挂 `/data` |
| `docker-entrypoint.sh` | 启动前检查数据目录可写，给出明确的中文提示 |
| `.env.example` | 配置模板（部署形态、授权、端口、构建参数），值全是占位符 |
| `nginx.conf` | 可选 Nginx 的反向代理配置 |

## 部署形态

在 `.env` 里选：

```bash
DEPLOY_MODE=single        # 单账套（默认）
# DEPLOY_MODE=saas        # 多账套；可再配 TENANT_HOST_SUFFIX=example.com
```

私有化授权（两项都留空则完全不校验、不联网）：

```bash
LICENSE_KEY=供应商提供的密钥
LICENSE_SERVER=https://saas.example.com
```

运行日志与诊断包（**默认不上传**，两项都配置了才会把脱敏诊断包发到私有仓库）：

```bash
LOG_REPO=lsgoodlionel/paper     # 私有仓库 owner/repo；留空即关闭上传
LOG_TOKEN=细粒度 PAT            # 只给该仓库 Contents 读写权限
```

日志在 `/data/日志/app.log`，诊断包在 `/data/日志/诊断包/`。手工生成一个交给开发：

```bash
docker compose exec app invoice-sorting diagnose --reason=manual
```

脱敏范围、令牌创建步骤与关闭方法见 [部署与运维 · 运行日志与诊断包](../../docs/部署与运维.md#117-运行日志与诊断包把现场交给开发)。

## 注意事项

- **镜像里不含任何密钥**：授权密钥与日志仓库令牌都只在运行时通过环境变量传入；`.env` 已被 `.gitignore` 忽略，也不会进入构建上下文。
- **非 root 运行**：容器内用户 UID/GID 均为 `10001`。改用宿主机目录存数据时，先 `sudo chown -R 10001:10001 <目录>`，否则容器会启动失败并打印提示。
- **数据在 `/data`**：默认挂命名卷 `invoice-data`；`docker compose down` 不会删除它。
- **构建慢或失败**：国内网络在 `.env` 里换镜像源（`PYPI_INDEX`、`NPM_REGISTRY`）；已在宿主机构建好前端时设 `FRONTEND_SOURCE=prebuilt` 可跳过容器内的前端构建。

## 常用命令

```bash
docker compose logs -f app                      # 实时日志
docker compose ps                               # 状态与健康检查
docker compose exec app invoice-sorting reset-password
docker compose exec app invoice-sorting export-tenant --out /data/备份/账套.zip
```
