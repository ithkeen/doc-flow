# doc-flow 部署配置

本目录包含 VPS 裸机部署所需的配置文件。

## 文件说明

- `doc-flow.service` — systemd service 配置模板
- `nginx-doc-flow.conf` — Nginx 反向代理配置模板

## 使用方法

完整的部署流程请参考：`docs/superpowers/specs/2026-03-13-vps-deployment-design.md`

## 部署前准备

在使用这些配置文件前，需要替换以下占位符：

**doc-flow.service**：
- `<deploy-user>` → 实际运行服务的用户名
- `/path/to/doc-flow` → doc-flow 项目的实际路径

**nginx-doc-flow.conf**：
- `your-domain.com` → 实际的域名或服务器 IP

## 快速部署

```bash
# 1. 复制 systemd service 文件
sudo cp doc-flow.service /etc/systemd/system/
# 编辑文件，替换占位符
sudo systemctl daemon-reload
sudo systemctl enable doc-flow
sudo systemctl start doc-flow

# 2. 复制 Nginx 配置
sudo cp nginx-doc-flow.conf /etc/nginx/sites-available/doc-flow
# 编辑文件，替换占位符
sudo ln -s /etc/nginx/sites-available/doc-flow /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```
