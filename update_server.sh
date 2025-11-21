#!/bin/bash
# 快速更新服务器代码脚本

echo "正在更新服务器上的代码..."

# 上传最新的 server.py
scp mcp_mysql/server.py ubuntu@your-server-ip:~/Documents/projects/mcp_mysql/mcp_mysql/

echo "代码已上传"
echo ""
echo "现在请在服务器上运行以下命令："
echo "cd ~/Documents/projects/mcp_mysql"
echo "find . -name '*.pyc' -delete  # 清除字节码缓存"
echo "find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true"
echo "python -m mcp_mysql.server"
