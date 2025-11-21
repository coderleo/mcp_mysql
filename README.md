# MCP MySQL Server

一个用于连接和查询MySQL数据库的MCP (Model Context Protocol) 服务器。

## 功能特性

- 通过 SSE (Server-Sent Events) 提供 HTTP 接口
- 连接MySQL数据库
- 执行 SELECT 查询（只读访问）
- 安全的只读模式，不支持 INSERT/UPDATE/DELETE 操作

## 安装

### 使用 uv（推荐）

```bash
# 安装 uv（如果尚未安装）
pip install uv

# 创建虚拟环境
uv venv

# 激活虚拟环境
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # MacOS/Linux

# 安装项目
pip install -e .
```

### 使用 pip

```bash
# 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate  # Windows
# source venv/bin/activate  # MacOS/Linux

# 安装项目
pip install -e .
```

## 使用方法

### 启动服务器

```bash
# 设置环境变量
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=your_username
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=your_database
export QUERY_TIMEOUT=30  # 查询超时时间（秒）

# Windows PowerShell
$env:MYSQL_HOST="localhost"
$env:MYSQL_PORT="3306"
$env:MYSQL_USER="your_username"
$env:MYSQL_PASSWORD="your_password"
$env:MYSQL_DATABASE="your_database"
$env:QUERY_TIMEOUT="30"  # 查询超时时间（秒）

# 启动 SSE 服务器
python -m mcp_mysql.server
# 或
mcp-mysql

# 服务器将运行在 http://localhost:8000
```

### 配置参数

**环境变量：**
- `MYSQL_HOST` - MySQL 服务器地址（默认: localhost）
- `MYSQL_PORT` - MySQL 端口（默认: 3306）
- `MYSQL_USER` - 数据库用户名（默认: root）
- `MYSQL_PASSWORD` - 数据库密码（默认: 空）
- `MYSQL_DATABASE` - 数据库名称（默认: 空）
- `QUERY_TIMEOUT` - 查询超时时间，单位秒（默认: 30）
- `MCP_HOST` - MCP 服务器地址（默认: 0.0.0.0）
- `MCP_PORT` - MCP 服务器端口（默认: 8000）

### 在 Claude Desktop 中配置

在 Claude Desktop 配置文件中添加以下配置：

**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mysql": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### 可用工具

1. **query** - 执行 SELECT 查询
   - `sql`: 要执行的 SELECT 语句（仅支持 SELECT 查询，保证只读访问）

## 示例

连接后，你可以：
- "查询 users 表的所有数据：SELECT * FROM users"
- "查询特定条件：SELECT name, email FROM users WHERE id > 10"
- "统计数据：SELECT COUNT(*) FROM orders WHERE status='completed'"

**注意：** 为了数据安全，本服务器只支持 SELECT 查询，不支持 INSERT、UPDATE、DELETE 等写操作。

## 安全注意事项

- 请妥善保管数据库凭据
- 建议使用只读账户
- 不要在公共仓库中提交包含密码的配置文件
