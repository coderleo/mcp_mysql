#!/bin/bash
# MCP MySQL 服务器启动脚本

# 激活虚拟环境（如果使用）
# source venv/bin/activate

# 加载环境变量
export $(cat .env | xargs)

# 启动服务器
python -m mcp_mysql.server
