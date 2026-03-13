# VPS 裸机部署设计

## 概述

将 doc-flow 从本地运行迁移到 VPS 云主机部署，使用 systemd 管理 Chainlit 进程，Nginx 做反向代理，面向个人/小团队使用场景。裸机部署方式让 doc-flow、Go 项目代码、git 操作都在同一环境中，便于后续扩展代码变动自动更新文档等功能。

## 目标

- 在 VPS 上稳定运行 Chainlit 聊天 UI
- 通过 Nginx 反向代理支持 HTTPS 和 WebSocket
- 使用 systemd 实现进程管理（开机自启、崩溃重启）
- Go 项目和 doc-flow 在同一环境，便于 git 操作和未来扩展

## 系统架构

```
用户 → Nginx (80/443) → Chainlit (127.0.0.1:8000, systemd service)
                              ↓
                         Go 项目目录（本地路径，通过 AGENT_WORK_DIR 配置）
```

## 服务器要求

- Linux VPS（Ubuntu 22.04+ 或类似发行版）
- Python 3.11（通过 uv 管理）
- Nginx
- Git
- 至少 1GB 内存（Chainlit + LLM 调用的开销主要在外部 API）

## 新增文件结构

```
doc-flow/
└── deploy/
    ├── doc-flow.service        # systemd service 文件
    └── nginx-doc-flow.conf     # Nginx 站点配置
```

将部署相关文件放在 `deploy/` 目录下，不污染项目根目录。

## systemd Service 设计

`deploy/doc-flow.service`：

```ini
[Unit]
Description=doc-flow Chainlit 聊天服务
After=network.target

[Service]
Type=simple
User=<deploy-user>
WorkingDirectory=/path/to/doc-flow
ExecStart=/path/to/doc-flow/.venv/bin/chainlit run app.py --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**关键设计决策**：
- `--host 127.0.0.1`：只监听本地，由 Nginx 对外暴露
- **不使用 `EnvironmentFile`**：pydantic-settings 已通过 `env_file=_ENV_FILE` 自动加载项目根目录的 `.env` 文件，无需 systemd 重复加载。避免 systemd 的 `EnvironmentFile` 解析器与 python-dotenv 的格式差异（如多行值、行内注释）导致问题
- `WorkingDirectory`：设为 doc-flow 项目根目录，确保 `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` 正确指向项目根，`.env` 文件自动被 pydantic-settings 加载
- `ExecStart` 使用 `.venv/bin/chainlit`：`uv sync` 默认在项目根目录创建 `.venv/`
- `Restart=on-failure`：进程异常退出时自动重启
- `User`：使用非 root 用户运行（安全性）

## Nginx 配置设计

`deploy/nginx-doc-flow.conf`：

```nginx
server {
    listen 80;
    server_name your-domain.com;    # 替换为实际域名或 IP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # WebSocket 支持（Chainlit 必需）
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # 标准代理头
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时放宽（LLM 响应可能较慢）
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # 配置 HTTPS 后，certbot 会自动添加 SSL 相关配置
}
```

## 环境配置

`.env` 文件与本地开发格式完全一致，只需调整路径相关配置：

```bash
# LLM API 配置（与本地一致）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your-key
LLM_MODEL=gpt-4

# 路径配置（指向服务器上的 Go 项目）
AGENT_WORK_DIR=/home/user/go-project
DOCS_OUTPUT_DIR=./docs

# 日志
LOG_LEVEL=INFO
LOG_DIR=logs/
```

**路径解析**：`doc_storage` 工具使用 `Path(settings.agent_work_dir) / settings.docs_output_dir` 拼接文档路径，因此 `DOCS_OUTPUT_DIR` 应保持为相对路径。最终文档写入 `{AGENT_WORK_DIR}/docs/`。

## 部署流程

### 首次部署

1. **安装基础依赖**：
   ```bash
   # 安装 uv
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # 安装 Nginx
   sudo apt install -y nginx

   # 安装 git（通常已预装）
   sudo apt install -y git

   # 配置防火墙（只开放必要端口）
   sudo ufw allow 22/tcp     # SSH
   sudo ufw allow 80/tcp     # HTTP
   sudo ufw allow 443/tcp    # HTTPS
   sudo ufw enable
   ```

2. **部署 doc-flow**：
   ```bash
   cd /opt  # 或你选择的部署目录
   git clone <your-repo-url> doc-flow
   cd doc-flow
   uv sync --frozen --no-dev    # 安装生产依赖（自动在项目根目录创建 .venv/）
   cp .env.example .env          # 创建配置文件
   # 编辑 .env，填入 LLM_API_KEY 和 AGENT_WORK_DIR
   ```

   **注意**：`.chainlit/` 和 `chainlit.md` 在 `.gitignore` 中，`git clone` 后不会存在。首次启动 Chainlit 时会自动生成默认的 `.chainlit/config.toml`。如果需要自定义配置（如 `allow_origins`），在首次启动后编辑该文件。

3. **配置 systemd**：
   ```bash
   sudo cp deploy/doc-flow.service /etc/systemd/system/
   # 编辑 service 文件，填入实际路径和用户名
   sudo systemctl daemon-reload
   sudo systemctl enable doc-flow    # 开机自启
   sudo systemctl start doc-flow     # 启动服务
   ```

4. **配置 Nginx**：
   ```bash
   sudo cp deploy/nginx-doc-flow.conf /etc/nginx/sites-available/doc-flow
   sudo ln -s /etc/nginx/sites-available/doc-flow /etc/nginx/sites-enabled/
   sudo nginx -t                     # 测试配置
   sudo systemctl reload nginx       # 生效
   ```

5. **（可选）配置 HTTPS**：
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

6. **验证**：
   ```bash
   sudo systemctl status doc-flow                  # 确认服务运行中
   curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000  # 应返回 200
   ```
   然后访问 `http(s)://your-domain` 或 `http://server-ip`

### 日常运维

| 操作 | 命令 |
|------|------|
| 查看服务状态 | `sudo systemctl status doc-flow` |
| 查看实时日志 | `sudo journalctl -u doc-flow -f` |
| 查看应用日志 | `tail -f /path/to/doc-flow/logs/app.log` |
| 重启服务 | `sudo systemctl restart doc-flow` |
| 停止服务 | `sudo systemctl stop doc-flow` |
| 更新 doc-flow 代码 | `cd /path/to/doc-flow && git pull && uv sync --frozen --no-dev && sudo systemctl restart doc-flow` |
| 更新 Go 项目代码 | `cd /path/to/go-project && git pull`（无需重启 doc-flow） |

## 注意事项

- **会话持久化**：当前 MemorySaver 是内存级别，进程重启后会话丢失。小团队场景可接受，未来可接入 SQLite/PostgreSQL checkpointer。
- **安全性**：`.env` 不提交 Git（确认 `.gitignore` 已排除）；使用非 root 用户运行服务；Chainlit 只监听 127.0.0.1；防火墙仅开放 22/80/443 端口。Chainlit 首次启动后会生成 `.chainlit/config.toml`，建议将 `allow_origins` 从默认的 `["*"]` 改为实际域名。
- **HTTPS**：推荐使用 certbot 自动获取和续期 Let's Encrypt 证书。内网使用时可暂时只开 HTTP。
- **Go 项目更新**：Go 项目直接在服务器本地 `git pull`，doc-flow 通过 `AGENT_WORK_DIR` 路径读取，无需重启。未来可扩展 `git_diff` 工具实现代码变动自动触发文档更新。
- **Go 运行时**：不需要安装 Go，doc-flow 只读取 Go 源码文件，不编译或执行。
- **回滚**：如果更新后服务异常，可通过 `git checkout <上一个版本>` 回退代码，再 `sudo systemctl restart doc-flow`。

## 交付物

1. `deploy/doc-flow.service` — systemd service 配置
2. `deploy/nginx-doc-flow.conf` — Nginx 站点配置
