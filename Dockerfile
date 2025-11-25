FROM harbor-devops.local.opentide.com.cn/tools/python:3.11-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 复制项目代码
COPY mcp_mysql/ ./mcp_mysql/
COPY pyproject.toml .
COPY README.md .
# 安装项目
RUN pip install -e .

# 暴露端口
EXPOSE 7056

# 设置环境变量（可在运行时覆盖）
ENV MYSQL_HOST=localhost \
    MYSQL_PORT=3306 \
    MYSQL_USER=root \
    MYSQL_PASSWORD= \
    MYSQL_DATABASE= \
    QUERY_TIMEOUT=30 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=7056
#
# 启动命令
CMD ["python", "-m", "mcp_mysql.server"]