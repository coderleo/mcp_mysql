# MCP MySQL 服务器部署指南

## 方式一：使用 systemd（推荐 - Linux）

### 1. 上传代码到服务器
```bash
# 在本地打包
cd D:\Projects\chatgpts\mcp_mysql
tar -czf mcp_mysql.tar.gz mcp_mysql/ pyproject.toml requirements.txt .env

# 上传到服务器
scp mcp_mysql.tar.gz user@your-server:/tmp/
```

### 2. 在服务器上安装
```bash
# SSH 连接到服务器
ssh user@your-server

# 创建目录
sudo mkdir -p /opt/mcp_mysql
cd /opt/mcp_mysql

# 解压
sudo tar -xzf /tmp/mcp_mysql.tar.gz -C /opt/mcp_mysql

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
# 或使用可编辑安装
pip install -e .
```

### 3. 配置环境变量
```bash
# 编辑 .env 文件
sudo nano /opt/mcp_mysql/.env

# 确保包含：
MYSQL_HOST=your-mysql-host
MYSQL_PORT=3306
MYSQL_USER=your-user
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=your-database
QUERY_TIMEOUT=30
MCP_HOST=0.0.0.0
MCP_PORT=7056
```

### 4. 配置 systemd 服务
```bash
# 复制服务文件
sudo cp mcp-mysql.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start mcp-mysql

# 设置开机自启
sudo systemctl enable mcp-mysql

# 查看状态
sudo systemctl status mcp-mysql

# 查看日志
sudo journalctl -u mcp-mysql -f
```

### 5. 配置防火墙
```bash
# 开放端口
sudo ufw allow 7056/tcp
# 或使用 firewalld
sudo firewall-cmd --permanent --add-port=7056/tcp
sudo firewall-cmd --reload
```

---

## 方式二：使用 Docker（推荐 - 跨平台）

### 1. 创建 Dockerfile
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY mcp_mysql/ ./mcp_mysql/
COPY pyproject.toml .

# 安装项目
RUN pip install -e .

# 暴露端口
EXPOSE 7056

# 启动服务
CMD ["python", "-m", "mcp_mysql.server"]
```

### 2. 构建并运行
```bash
# 构建镜像
docker build -t mcp-mysql .

# 运行容器
docker run -d \
  --name mcp-mysql \
  --restart=always \
  -p 7056:7056 \
  -e MYSQL_HOST=your-host \
  -e MYSQL_PORT=3306 \
  -e MYSQL_USER=your-user \
  -e MYSQL_PASSWORD=your-password \
  -e MYSQL_DATABASE=your-database \
  -e QUERY_TIMEOUT=30 \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=7056 \
  mcp-mysql

# 查看日志
docker logs -f mcp-mysql
```

### 3. 使用 docker-compose
```yaml
version: '3.8'
services:
  mcp-mysql:
    build: .
    container_name: mcp-mysql
    restart: always
    ports:
      - "7056:7056"
    environment:
      - MYSQL_HOST=your-host
      - MYSQL_PORT=3306
      - MYSQL_USER=your-user
      - MYSQL_PASSWORD=your-password
      - MYSQL_DATABASE=your-database
      - QUERY_TIMEOUT=30
      - MCP_HOST=0.0.0.0
      - MCP_PORT=7056
```

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

---

## 方式三：直接运行（简单测试）

### 1. 上传代码
```bash
scp -r mcp_mysql/ user@server:/home/user/
scp pyproject.toml requirements.txt .env user@server:/home/user/
```

### 2. 安装并运行
```bash
ssh user@server

cd /home/user
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 后台运行
nohup python -m mcp_mysql.server > mcp.log 2>&1 &

# 查看日志
tail -f mcp.log
```

---

## 方式四：使用 Supervisor（进程管理）

### 1. 安装 Supervisor
```bash
sudo apt install supervisor
```

### 2. 配置文件
```ini
# /etc/supervisor/conf.d/mcp-mysql.conf
[program:mcp-mysql]
command=/opt/mcp_mysql/venv/bin/python -m mcp_mysql.server
directory=/opt/mcp_mysql
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/mcp-mysql.log
environment=MYSQL_HOST="your-host",MYSQL_PORT="3306",MYSQL_USER="user",MYSQL_PASSWORD="pass",MYSQL_DATABASE="db"
```

### 3. 启动
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start mcp-mysql
sudo supervisorctl status mcp-mysql
```

---

## 验证部署

### 1. 测试连接
```bash
# 测试服务器是否启动
curl http://your-server:7056/sse

# 应该保持连接打开
```

### 2. 配置客户端
在 CodeBuddy 或 Claude Desktop 配置：
```json
{
  "mcpServers": {
    "mysql": {
      "url": "http://your-server:7056/sse"
    }
  }
}
```

---

## 安全建议

1. **使用 HTTPS**（通过 Nginx 反向代理）
```nginx
server {
    listen 443 ssl;
    server_name mcp.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:7056;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

2. **添加认证**（修改代码添加 API Key 验证）

3. **限制 IP 访问**
```bash
# 防火墙只允许特定 IP
sudo ufw allow from YOUR_IP to any port 7056
```

---

## 监控和维护

### 查看日志
```bash
# systemd
sudo journalctl -u mcp-mysql -f

# Docker
docker logs -f mcp-mysql

# 直接运行
tail -f mcp.log
```

### 重启服务
```bash
# systemd
sudo systemctl restart mcp-mysql

# Docker
docker restart mcp-mysql

# Supervisor
sudo supervisorctl restart mcp-mysql
```

---

## 推荐方案

**生产环境**：Docker + Nginx（HTTPS）
**开发/测试**：systemd 或 Supervisor
**快速验证**：直接运行
