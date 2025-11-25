"""
MCP MySQL 服务器（连接与查询）

本模块提供一个 Model Context Protocol (MCP) 服务器，允许通过 SSE
与 MySQL 数据库建立连接并执行 SQL 查询。
"""

import os
import json
import asyncio
import logging
from typing import Any, Optional
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
from mcp.server import Server

# 加载 .env 文件中的环境变量
load_dotenv()
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import Response

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MySQLPoolManager:
    """MySQL 连接池管理器（同步客户端）。

    管理基于 `mysql.connector.pooling.MySQLConnectionPool` 的连接池，提供
    同步的 `execute_query` 方法。由于 MCP 服务器是异步的，调用方应
    在协程中通过 `asyncio.to_thread` 将该同步方法移到线程池中执行。
    """

    def __init__(self, host: str, port: int, user: str, password: str, database: str,
                 query_timeout: int = 30, pool_size: int = 5):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.query_timeout = query_timeout
        self.pool_size = pool_size
        self.pool: Optional[pooling.MySQLConnectionPool] = None

    def connect(self):
        """创建连接池并初始化。成功返回 True，失败抛出异常。

        中文说明: 使用实例化时提供的配置信息创建 `MySQLConnectionPool`。
        """
        try:
            logger.info(f"创建 MySQL 连接池: {self.host}:{self.port}/{self.database} (size={self.pool_size})")
            self.pool = pooling.MySQLConnectionPool(
                pool_name="mcp_pool",
                pool_size=self.pool_size,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            logger.info("MySQL 连接池创建成功")
            return True
        except Error as e:
            logger.error(f"创建连接池失败: {e}")
            raise Exception(f"Error creating MySQL pool: {e}")

    def disconnect(self):
        """断开/清理连接池（尽力而为）。

        中文说明: mysql.connector 的池不提供显式关闭方法，这里只是
        将内部引用置空以便垃圾回收；对于大多数应用，让进程退出
        即可释放资源。
        """
        self.pool = None

    def execute_query(self, query: str, timeout: Optional[int] = None) -> dict[str, Any]:
        """使用池中的连接执行 SELECT 查询（同步方法）。

        中文说明:
        - 只允许执行以 SELECT 开头的查询；否则返回错误结构并拒绝执行。
        - 从连接池获取连接，设置会话级查询超时（`max_execution_time`），
          执行查询并返回结果（列表形式，字典字段）。
        - 如果出现数据库错误，返回带有 `error_code` 与 `message` 的结构。
        - 该方法是阻塞的；在异步环境中应通过 `asyncio.to_thread` 将其移到
          线程池执行以避免阻塞事件循环。
        """
        # 验证查询是以 SELECT 开头的语句
        query_upper = query.strip().upper()
        if not query_upper.startswith('SELECT'):
            logger.warning(f"拒绝执行非 SELECT 查询: {query[:50]}...")
            return {
                "success": False,
                "error_code": "INVALID_QUERY",
                "message": "仅允许执行 SELECT 查询"
            }

        try:
            if not self.pool:
                self.connect()
        except Exception as e:
            return {
                "success": False,
                "error_code": "CONNECTION_ERROR",
                "message": f"数据库连接失败: {str(e)}"
            }

        effective_timeout = timeout if timeout is not None else self.query_timeout

        conn = None
        cursor = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor(dictionary=True)
            # 将查询超时设置为毫秒
            cursor.execute(f"SET SESSION max_execution_time={effective_timeout * 1000}")

            logger.info(f"执行查询 (超时: {effective_timeout}秒): {query[:100]}...")
            cursor.execute(query)
            results = cursor.fetchall()
            logger.info(f"查询成功，返回 {len(results)} 行数据")
            return {"success": True, "data": results}
        except Error as e:
            error_msg = str(e)
            if "max_execution_time" in error_msg.lower() or "timeout" in error_msg.lower() \
                or "time exceeded" in error_msg.lower():
                logger.warning(f"查询超时 ({effective_timeout}秒): {query[:50]}...")
                return {
                    "success": False,
                    "error_code": "TIMEOUT",
                    "message": f"查询超时，已超过 {effective_timeout} 秒。请优化查询或增加超时时间。",
                    "timeout_seconds": effective_timeout
                }
            logger.error(f"数据库错误: {e}")
            return {"success": False, "error_code": "DATABASE_ERROR", "message": f"执行查询时出错: {str(e)}"}
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()  # 返回连接到连接池（或关闭连接）
                except Exception:
                    pass
    



# Global MySQL pool manager
db_connection: Optional[MySQLPoolManager] = None


def get_db_connection() -> MySQLPoolManager:
    """获取或创建全局的 MySQL 连接池管理器。

    中文说明:
    - 懒初始化 `MySQLPoolManager` 并创建连接池，使用环境变量配置连接参数。
    - 返回单例的 `MySQLPoolManager` 以便在进程内复用池资源。

    说明：
    - 懒初始化 `MySQLPoolManager` 并使用环境变量配置连接参数创建连接池。
    - 返回进程内可复用的单例 `MySQLPoolManager`。
    """
    global db_connection
    if db_connection is None:
        host = os.getenv("MYSQL_HOST", "localhost")
        port = int(os.getenv("MYSQL_PORT", "3306"))
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "")
        query_timeout = int(os.getenv("QUERY_TIMEOUT", "15"))
        pool_size = int(os.getenv("POOL_SIZE", "20"))

        logger.info(f"创建数据库连接池管理: {user}@{host}:{port}/{database}")
        db_connection = MySQLPoolManager(host, port, user, password, database, query_timeout, pool_size)
        db_connection.connect()

    return db_connection


# Create MCP server instance
app = Server("mcp-mysql")

# Create a single SSE transport instance
sse_transport = SseServerTransport("/messages")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用的工具。"""
    return [
        Tool(
            name="query",
            description="在 MySQL 数据库上执行 SELECT 查询。仅允许 SELECT 语句，确保只读访问。",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的 SELECT 查询语句（仅支持 SELECT 语句）"
                    }
                },
                "required": ["sql"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用。"""
    logger.info(f"收到工具调用请求: {name}")
    if name != "query":
        error_result = {
            "success": False,
            "error_code": "UNKNOWN_TOOL",
            "message": f"未知的工具: {name}"
        }
        return [TextContent(
            type="text",
            text=json.dumps(error_result, indent=2, ensure_ascii=False)
        )]
    
    sql = arguments.get("sql")
    if not sql:
        error_result = {
            "success": False,
            "error_code": "MISSING_PARAMETER",
            "message": "需要提供 SQL 查询语句"
        }
        return [TextContent(
            type="text",
            text=json.dumps(error_result, indent=2, ensure_ascii=False)
        )]
    
    try:
        db = get_db_connection()
        # execute_query is synchronous (uses mysql.connector); run in thread
        result = await asyncio.to_thread(db.execute_query, sql)
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False, default=str)
        )]
    except Exception as e:
        # 处理连接错误等意外异常
        error_result = {
            "success": False,
            "error_code": "UNEXPECTED_ERROR",
            "message": f"意外错误: {str(e)}"
        }
        return [TextContent(
            type="text",
            text=json.dumps(error_result, indent=2, ensure_ascii=False)
        )]


# ASGI application combining SSE and message handling
async def mcp_asgi_app(scope, receive, send):
    """ASGI 主应用，处理 SSE 与消息路由。

    中文说明:
    - 处理来自 HTTP 的请求，根据 `scope['path']` 与方法路由到 SSE
      端点或消息端点。
    - 对于 `/sse` 建立 SSE 连接并驱动 MCP `Server` 的读取/写入流。
    - 对于 `/messages` 处理 POST 消息交付给 SSE 传输层。
    """
    if scope["type"] == "http":
        path = scope["path"]
        method = scope["method"]

        if path == "/sse" and method == "GET":
            # Handle SSE connection
            client = scope.get('client')
            client_host = client[0] if client else "未知"
            logger.info(f"SSE 连接建立: 客户端 {client_host}")

            async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
                await app.run(
                    read_stream,
                    write_stream,
                    app.create_initialization_options()
                )

        elif path == "/messages" and method == "POST":
            # Handle POST messages
            logger.info("收到 POST 消息")

            await sse_transport.handle_post_message(scope, receive, send)

        else:
            # 404 Not Found
            await send({
                'type': 'http.response.start',
                'status': 404,
                'headers': [(b'content-type', b'text/plain')],
            })
            await send({
                'type': 'http.response.body',
                'body': b'Not Found',
            })


# Use raw ASGI app instead of Starlette routes
starlette_app = mcp_asgi_app


async def main():
    """应用启动入口：配置并运行 uvicorn 服务器。

    中文说明:
    - 读取环境变量 `MCP_HOST` 和 `MCP_PORT`，打印启动信息并启动
      uvicorn 以运行 ASGI 应用 `starlette_app`。
    """
    import uvicorn

    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))

    logger.info("=" * 50)
    logger.info("MCP MySQL 服务器启动中...")
    logger.info(f"服务器地址: http://{host}:{port}")
    logger.info(f"SSE 端点: http://{host}:{port}/sse")
    logger.info(f"消息端点: http://{host}:{port}/messages")
    logger.info("=" * 50)

    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


def run():
    """启动服务器的同步包装函数。

    中文说明: 在同步上下文中调用此函数会运行 asyncio 事件循环并启动
    MCP SSE 服务器（等价于 `python -m mcp_mysql.server` 的行为）。
    """
    asyncio.run(main())


if __name__ == "__main__":
    run()
