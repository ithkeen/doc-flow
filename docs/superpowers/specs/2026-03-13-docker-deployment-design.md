# Docker Compose 部署设计

## 概述

将 doc-flow 从本地运行迁移到 VPS 云主机部署，使用 Docker Compose 编排 Chainlit 应用容器和 Nginx 反代容器，面向个人/小团队使用场景。

## 目标

- 通过 Docker 容器化实现环境一致性和可移植性
- 通过 Nginx 反向代理支持 HTTPS 和 WebSocket
- Go 项目源码通过 volume 挂载，不打包进镜像
- 敏感配置（API Key）通过环境变量注入，不进镜像

## 容器架构

```
用户 → Nginx 容器 (80/443) → Chainlit 容器 (8000)
                                   ↓ volume mount
                              宿主机 Go 项目目录
```

| 服务 | 镜像 | 职责 | 端口 |
|------|------|------|------|
| `app` | 自定义（python:3.11-slim 多阶段构建） | 运行 `chainlit run app.py` | 8000（内部） |
| `nginx` | nginx:alpine | 反向代理、HTTPS 终止、WebSocket 转发 | 80, 443（对外） |

## 新增文件结构

```
doc-flow/
├── Dockerfile              # app 容器多阶段构建
├── docker-compose.yml      # 服务编排
├── .dockerignore           # 构建排除规则
└── nginx/
    └── default.conf        # Nginx 反代配置
```

## Dockerfile 设计

多阶段构建，最小化最终镜像体积：

**Stage 1 — builder**：
- 基础镜像：`python:3.11-slim`
- 安装 `uv`
- 复制 `pyproject.toml` + `uv.lock`
- 执行 `uv sync --frozen --no-dev`（只装生产依赖）

**Stage 2 — runtime**：
- 基础镜像：`python:3.11-slim`
- `WORKDIR /app`
- 从 builder 复制 `.venv/`
- 复制项目源码：`src/`、`app.py`、`.chainlit/`、`chainlit.md`
- 设置 `PATH` 包含 `.venv/bin`
- `EXPOSE 8000`
- `CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]`

**必须打包进镜像的文件**（Chainlit 运行时依赖）：
- `app.py` — 入口文件
- `src/` — 所有源码，**包括 `src/prompts/` 下的 `.md` 模板文件**
- `.chainlit/` — Chainlit 配置和翻译文件
- `chainlit.md` — Chainlit 欢迎页内容

**不打包进镜像的内容**：
- `.env` 文件（通过 env_file 注入）
- Go 项目源码（通过 volume 挂载）
- dev 依赖（pytest 等）
- `.git/`、`__pycache__/`、`tests/`、`logs/`、`docs/`

**`.dockerignore` 注意事项**：
- 不要使用 `*.md` 全局排除模式，否则会误删 `src/prompts/` 下的 prompt 模板和 `chainlit.md`
- 只排除项目根目录的文档：`docs/`、`README.md`

## Docker Compose 配置

```yaml
services:
  app:
    build: .
    env_file: .env
    environment:
      - AGENT_WORK_DIR=/workspace
      - DOCS_OUTPUT_DIR=docs
      - LOG_DIR=/app/logs/
    volumes:
      - /path/to/go-project:/workspace:ro    # Go 源码只读
      - ./docs:/workspace/docs               # 文档输出（覆盖只读挂载的 docs 子路径）
      - ./logs:/app/logs                      # 日志输出
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - /path/to/ssl/certs:/etc/nginx/ssl:ro
    depends_on:
      app:
        condition: service_healthy
    restart: unless-stopped
```

**路径解析说明**：`doc_storage` 工具使用 `Path(settings.agent_work_dir) / settings.docs_output_dir` 拼接文档路径。因此 `DOCS_OUTPUT_DIR` 必须是**相对路径**（如 `docs`），这样实际路径为 `/workspace/docs`。通过将 `./docs` 挂载到 `/workspace/docs`，文档输出覆盖了 Go 项目只读挂载中的 `docs` 子路径，实现读写。

**网络**：使用 Docker Compose 默认 bridge 网络，容器间通过服务名互访（如 `http://app:8000`），无需自定义网络配置。

## Nginx 配置要点

`nginx/default.conf` 关键配置：

- HTTP (80) → HTTPS (443) 301 重定向
- 反向代理：`proxy_pass http://app:8000`
- WebSocket 支持（Chainlit 必需）：
  ```
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  ```
- 超时放宽：`proxy_read_timeout 300s`（LLM 响应可能较慢）
- 标准代理头：`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`

## 部署流程

### 首次部署

1. VPS 上安装 Docker 和 Docker Compose
2. `git clone` doc-flow 仓库到服务器
3. 创建 `.env` 文件（参考 `.env.example`），填入 `LLM_API_KEY` 等
4. 修改 `docker-compose.yml` 中 Go 项目挂载路径
5. （可选）配置域名 DNS，获取 SSL 证书
6. `docker compose up -d --build`
7. 访问验证

### 日常运维

| 操作 | 命令 |
|------|------|
| 查看日志 | `docker compose logs -f app` |
| 重启服务 | `docker compose restart` |
| 更新代码 | `git pull && docker compose up -d --build` |
| 停止服务 | `docker compose down` |

## 注意事项

- **会话持久化**：当前 MemorySaver 是内存级别，容器重启后会话丢失。小团队场景可接受，未来可接入 SQLite/PostgreSQL checkpointer。
- **安全性**：`.env` 不提交 Git（确认 `.gitignore` 已排除）；Go 项目目录只读挂载；API Key 仅通过环境变量注入。部署后应将 `.chainlit/config.toml` 中的 `allow_origins` 从 `["*"]` 改为实际域名。
- **HTTPS**：可用 Let's Encrypt + certbot 获取免费证书（需要 `fullchain.pem` 和 `privkey.pem`，放入 SSL 证书目录并在 Nginx 配置中引用）。内网使用时可暂时只开 HTTP，去掉 443 端口和 SSL 相关配置。

## 交付物

1. `Dockerfile` — 多阶段构建的应用容器
2. `docker-compose.yml` — 服务编排配置
3. `.dockerignore` — 构建排除规则
4. `nginx/default.conf` — Nginx 反代配置
