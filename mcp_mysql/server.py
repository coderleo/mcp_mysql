"""
MCP Server for MySQL Database Connections and Queries

This module provides a Model Context Protocol (MCP) server that enables
connections to MySQL databases and execution of SQL queries via SSE.
"""

import os
import json
import asyncio
import logging
from typing import Any, Optional
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
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


class MySQLConnection:
    """Manages MySQL database connections."""
    
    def __init__(self, host: str, port: int, user: str, password: str, database: str, query_timeout: int = 30):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.query_timeout = query_timeout
        self.connection = None
    
    def connect(self):
        """Establish connection to MySQL database."""
        try:
            logger.info(f"正在连接到 MySQL: {self.host}:{self.port}/{self.database}")
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            logger.info("MySQL 连接成功")
            return True
        except Error as e:
            logger.error(f"MySQL 连接失败: {e}")
            raise Exception(f"Error connecting to MySQL: {e}")
    
    def disconnect(self):
        """Close the database connection."""
        if self.connection and self.connection.is_connected():
            self.connection.close()
    
    def execute_query(self, query: str, timeout: Optional[int] = None) -> dict[str, Any]:
        """执行 SELECT 查询并返回结果，支持超时控制。
        
        Args:
            query: 要执行的 SELECT 查询语句
            timeout: 查询超时时间（秒），默认使用实例配置的超时时间
        
        Returns:
            成功时: {"success": True, "data": [...]}
            失败时: {"success": False, "error_code": "...", "message": "..."}
            超时时: {"success": False, "error_code": "TIMEOUT", "message": "...", "timeout_seconds": 30}
        """
        # Validate that query is a SELECT statement
        query_upper = query.strip().upper()
        if not query_upper.startswith('SELECT'):
            logger.warning(f"拒绝执行非 SELECT 查询: {query[:50]}...")
            return {
                "success": False,
                "error_code": "INVALID_QUERY",
                "message": "仅允许执行 SELECT 查询"
            }
        
        try:
            if not self.connection or not self.connection.is_connected():
                self.connect()
        except Exception as e:
            return {
                "success": False,
                "error_code": "CONNECTION_ERROR",
                "message": f"数据库连接失败: {str(e)}"
            }
        
        # Use provided timeout or fall back to instance timeout
        effective_timeout = timeout if timeout is not None else self.query_timeout
        
        cursor = self.connection.cursor(dictionary=True)
        try:
            # Set query timeout
            cursor.execute(f"SET SESSION max_execution_time={effective_timeout * 1000}")  # MySQL timeout in milliseconds
            
            # Execute the actual query
            logger.info(f"执行查询 (超时: {effective_timeout}秒): {query[:100]}...")
            cursor.execute(query)
            results = cursor.fetchall()
            logger.info(f"查询成功，返回 {len(results)} 行数据")
            return {
                "success": True,
                "data": results
            }
        except Error as e:
            error_msg = str(e)
            # Check if it's a timeout error
            if "max_execution_time" in error_msg.lower() or "timeout" in error_msg.lower():
                logger.warning(f"查询超时 ({effective_timeout}秒): {query[:50]}...")
                return {
                    "success": False,
                    "error_code": "TIMEOUT",
                    "message": f"查询超时，已超过 {effective_timeout} 秒。请优化查询或增加超时时间。",
                    "timeout_seconds": effective_timeout
                }
            logger.error(f"数据库错误: {e}")
            return {
                "success": False,
                "error_code": "DATABASE_ERROR",
                "message": f"执行查询时出错: {str(e)}"
            }
        finally:
            cursor.close()
    



# Global MySQL connection
db_connection: Optional[MySQLConnection] = None


def get_db_connection() -> MySQLConnection:
    """Get or create database connection."""
    global db_connection
    if db_connection is None:
        host = os.getenv("MYSQL_HOST", "localhost")
        port = int(os.getenv("MYSQL_PORT", "3306"))
        user = os.getenv("MYSQL_USER", "root")
        password = os.getenv("MYSQL_PASSWORD", "")
        database = os.getenv("MYSQL_DATABASE", "")
        query_timeout = int(os.getenv("QUERY_TIMEOUT", "30"))
        
        logger.info(f"创建数据库连接: {user}@{host}:{port}/{database}")
        db_connection = MySQLConnection(host, port, user, password, database, query_timeout)
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
        result = db.execute_query(sql)
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
    """Main ASGI application for MCP server."""
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
            logger.debug("收到 POST 消息")
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
    """Main entry point for the MCP SSE server."""
    import uvicorn
    
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    
    logger.info("="*50)
    logger.info("MCP MySQL 服务器启动中...")
    logger.info(f"服务器地址: http://{host}:{port}")
    logger.info(f"SSE 端点: http://{host}:{port}/sse")
    logger.info(f"消息端点: http://{host}:{port}/messages")
    logger.info("="*50)
    
    config = uvicorn.Config(
        starlette_app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


def run():
    """Run the SSE server."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
