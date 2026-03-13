# VPS 部署实现计划

## 目标

根据 `docs/superpowers/specs/2026-03-13-vps-deployment-design.md` 创建部署配置文件，使 doc-flow 可以在 VPS 上通过 systemd + Nginx 运行。

## 范围

**包含**：
- 创建 `deploy/` 目录
- 编写 systemd service 配置文件
- 编写 Nginx 反向代理配置文件

**不包含**：
- 实际的服务器部署操作（由用户在 VPS 上执行）
- HTTPS 证书获取（由用户通过 certbot 完成）
- 服务器环境安装（uv、Nginx、git 等）

## 实现步骤

### 1. 创建 deploy 目录结构

创建 `deploy/` 目录用于存放部署配置文件。

**文件**：无（目录创建）

**验收**：`deploy/` 目录存在

---

### 2. 创建 systemd service 配置

编写 `deploy/doc-flow.service`，包含：
- Unit 描述和依赖
- Service 配置（用户、工作目录、启动命令、重启策略）
- Install 配置（开机自启）

**文件**：`deploy/doc-flow.service`

**关键点**：
- 不使用 `EnvironmentFile`（pydantic-settings 已加载 .env）
- `WorkingDirectory` 使用占位符 `/path/to/doc-flow`（用户部署时替换）
- `User` 使用占位符 `<deploy-user>`（用户部署时替换）
- `ExecStart` 指向 `.venv/bin/chainlit`
- 监听 `127.0.0.1:8000`（仅本地）

**验收**：文件存在，语法正确（可通过 `systemd-analyze verify` 验证）

---

### 3. 创建 Nginx 配置

编写 `deploy/nginx-doc-flow.conf`，包含：
- 监听 80 端口
- 反向代理到 `127.0.0.1:8000`
- WebSocket 支持（Upgrade 和 Connection 头）
- 代理超时设置（300s）
- 标准代理头（Host、X-Real-IP、X-Forwarded-For、X-Forwarded-Proto）

**文件**：`deploy/nginx-doc-flow.conf`

**关键点**：
- `server_name` 使用占位符 `your-domain.com`（用户部署时替换）
- 包含 WebSocket 必需的 `proxy_http_version 1.1` 和 Upgrade 头
- 超时设置 `proxy_read_timeout 300s` 和 `proxy_send_timeout 300s`
- 注释说明 certbot 会自动添加 SSL 配置

**验收**：文件存在，语法正确（可通过 `nginx -t` 验证）

---

### 4. 添加部署说明文档

在 `deploy/README.md` 中添加简要说明，指向完整的设计文档。

**文件**：`deploy/README.md`

**内容**：
- 说明这两个文件的用途
- 指向 `docs/superpowers/specs/2026-03-13-vps-deployment-design.md` 获取完整部署流程
- 提醒用户需要替换占位符（路径、用户名、域名）

**验收**：文件存在，内容清晰

---

## 验证方式

1. 文件结构检查：
   ```bash
   ls -la deploy/
   # 应包含：doc-flow.service, nginx-doc-flow.conf, README.md
   ```

2. systemd 配置语法检查（需要在 Linux 上）：
   ```bash
   systemd-analyze verify deploy/doc-flow.service
   ```

3. Nginx 配置语法检查（需要安装 Nginx）：
   ```bash
   nginx -t -c deploy/nginx-doc-flow.conf
   ```

## 依赖关系

- 步骤 1 → 步骤 2, 3, 4（目录必须先存在）
- 步骤 2, 3, 4 可并行执行

## 风险与注意事项

- 配置文件中的占位符必须在部署时被替换，否则服务无法启动
- systemd service 文件的路径必须是绝对路径
- Nginx 配置中的 `server_name` 如果不替换，可能导致虚拟主机路由错误

## 交付物

1. `deploy/doc-flow.service` — systemd service 配置模板
2. `deploy/nginx-doc-flow.conf` — Nginx 站点配置模板
3. `deploy/README.md` — 部署说明文档
