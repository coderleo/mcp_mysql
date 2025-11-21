# MCP SSE 服务器调试经验总结

## 问题概述

在部署基于 Starlette 的 MCP (Model Context Protocol) SSE 服务器时，遇到了一系列与 ASGI 协议和响应处理相关的问题。

## 关键问题及解决方案

### 1. SseServerTransport 的正确使用方式

**问题：**
- 最初尝试将 `SseServerTransport` 作为异步上下文管理器使用，导致 `TypeError: 'SseServerTransport' object does not support asynchronous context manager protocol`

**错误代码：**
```python
async with SseServerTransport("/messages") as transport:
    # 这是错误的用法
```

**解决方案：**
- 创建全局单例的 `SseServerTransport` 实例
- 使用 `connect_sse()` 方法建立 SSE 连接

**正确代码：**
```python
# 全局创建一个共享实例
sse_transport = SseServerTransport("/messages")

# 在处理函数中使用
async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
    await app.run(read_stream, write_stream, app.create_initialization_options())
```

### 2. Session 追踪问题

**问题：**
- 每次请求创建新的 `SseServerTransport` 实例导致会话无法追踪
- 日志显示：`Could not find session for ID: xxx`
- HTTP 状态：404 Not Found

**原因：**
- SSE 连接和 POST 消息使用不同的 transport 实例
- Session 信息保存在 transport 实例中，无法跨实例共享

**解决方案：**
- 在模块级别创建**单个共享**的 `SseServerTransport` 实例
- 所有请求处理函数使用同一个实例

**错误示例：**
```python
async def handle_sse(request):
    transport = SseServerTransport("/messages")  # ❌ 每次创建新实例
    ...

async def handle_messages(request):
    transport = SseServerTransport("/messages")  # ❌ 另一个新实例
    ...
```

**正确示例：**
```python
# 模块级别 - 只创建一次
sse_transport = SseServerTransport("/messages")

async def handle_sse(request):
    # ✅ 使用共享实例
    async with sse_transport.connect_sse(...) as streams:
        ...

async def handle_messages(request):
    # ✅ 使用同一个共享实例
    await sse_transport.handle_post_message(...)
```

### 3. Starlette Route 与 ASGI 响应冲突

**问题：**
- `handle_post_message()` 返回 `None`，导致 `TypeError: 'NoneType' object is not callable`
- 或者返回 `Response()` 后导致 `RuntimeError: Unexpected ASGI message 'http.response.start' sent, after response already completed`

**原因分析：**
- `handle_post_message()` 是一个 ASGI 应用，它通过 `send` 回调**直接发送响应**，不返回 Response 对象
- Starlette 的 `Route` 期望处理函数返回一个 `Response` 对象
- 这导致了双重响应：
  1. `handle_post_message` 通过 `send` 发送响应（202 Accepted）
  2. Starlette 尝试调用返回值作为 Response（None 或 Response()）

**错误尝试 1 - 不返回任何东西：**
```python
async def handle_messages(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    # ❌ 返回 None，Starlette 会报错
```

**错误尝试 2 - 返回 Response：**
```python
async def handle_messages(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    return Response()  # ❌ 导致重复发送响应
```

**最终解决方案 - 使用原生 ASGI 应用：**
```python
async def mcp_asgi_app(scope, receive, send):
    """原生 ASGI 应用，直接处理请求"""
    if scope["type"] == "http":
        path = scope["path"]
        method = scope["method"]
        
        if path == "/sse" and method == "GET":
            async with sse_transport.connect_sse(scope, receive, send) as (read_stream, write_stream):
                await app.run(read_stream, write_stream, app.create_initialization_options())
        
        elif path == "/messages" and method == "POST":
            await sse_transport.handle_post_message(scope, receive, send)
        
        else:
            # 手动发送 404 响应
            await send({
                'type': 'http.response.start',
                'status': 404,
                'headers': [(b'content-type', b'text/plain')],
            })
            await send({
                'type': 'http.response.body',
                'body': b'Not Found',
            })

# 直接使用原生 ASGI 应用，不经过 Starlette 路由
starlette_app = mcp_asgi_app
```

### 4. Python 字节码缓存问题

**问题：**
- 修改源码后，运行的还是旧代码
- 使用 `pip install -e .` 可编辑安装，但字节码缓存未清除

**解决方案：**
```bash
# 清除所有字节码缓存
find . -name '*.pyc' -delete
find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# 强制重新安装
pip uninstall mcp-mysql -y
pip install -e . --no-cache-dir
```

### 5. 跨平台部署问题

**问题：**
- 虚拟环境从 Windows 复制到 Linux 失败
- Python 虚拟环境包含平台特定的二进制文件

**解决方案：**
- 不要复制虚拟环境
- 在目标平台重新创建虚拟环境：
  ```bash
  # 在 Linux 服务器上
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  pip install -e .
  ```

## 调试技巧

### 1. 检查实际导入的模块
```python
# 查看 Python 实际导入的文件位置
python3 -c "import mcp_mysql.server; print(mcp_mysql.server.__file__)"

# 检查函数源码
python3 -c "import mcp_mysql.server; import inspect; print(inspect.getsource(mcp_mysql.server.handle_messages))"
```

### 2. 测试 ASGI 应用返回值
```python
import asyncio
from mcp_mysql.server import sse_transport

async def test():
    scope = {'type': 'http', 'method': 'POST', 'path': '/messages', 'query_string': b'session_id=test'}
    async def receive(): return {'type': 'http.request', 'body': b'{}'}
    responses = []
    async def send(message): responses.append(message)
    
    result = await sse_transport.handle_post_message(scope, receive, send)
    print(f"返回值: {result}")  # 应该是 None
    print(f"响应: {responses}")  # 应该包含 http.response.start 和 http.response.body

asyncio.run(test())
```

### 3. 查看日志诊断问题
```python
# 在代码中添加详细日志
logger.info(f"函数返回值: {result}")
logger.info(f"返回值类型: {type(result)}")
```

## 什么是原生 ASGI 应用？

### ASGI 协议简介

**ASGI (Asynchronous Server Gateway Interface)** 是 Python 异步 Web 服务器和应用之间的标准接口协议，类似于同步环境下的 WSGI。

### 原生 ASGI 应用的定义

**原生 ASGI 应用** 是一个符合 ASGI 规范的异步函数，它接受三个参数：

```python
async def app(scope, receive, send):
    """
    scope: dict - 包含请求信息（路径、方法、headers等）
    receive: callable - 异步函数，用于接收客户端消息
    send: callable - 异步函数，用于向客户端发送响应
    """
    # 直接处理 HTTP 请求
    if scope['type'] == 'http':
        # 通过 send 发送响应
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [(b'content-type', b'text/plain')],
        })
        await send({
            'type': 'http.response.body',
            'body': b'Hello World',
        })
```

### 原生 ASGI vs Starlette Route

| 特性 | 原生 ASGI 应用 | Starlette Route 处理函数 |
|------|---------------|------------------------|
| **函数签名** | `async def app(scope, receive, send)` | `async def handler(request: Request)` |
| **请求对象** | 直接访问 ASGI scope 字典 | 包装在 `Request` 对象中 |
| **响应方式** | 通过 `send()` 回调发送 | 返回 `Response` 对象 |
| **响应控制** | 完全手动控制 | Starlette 自动处理 |
| **适用场景** | 需要底层控制、流式响应、SSE | 常规 HTTP 请求/响应 |

### 示例对比

**Starlette Route 方式（高层抽象）：**
```python
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

async def homepage(request):
    # ✅ 返回 Response 对象
    return JSONResponse({'hello': 'world'})

app = Starlette(routes=[
    Route('/', endpoint=homepage),
])
```

**原生 ASGI 方式（底层控制）：**
```python
async def app(scope, receive, send):
    # ✅ 直接发送响应
    if scope['path'] == '/':
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [(b'content-type', b'application/json')],
        })
        await send({
            'type': 'http.response.body',
            'body': b'{"hello": "world"}',
        })
```

### 为什么 MCP SSE 需要原生 ASGI？

**问题根源：**

`SseServerTransport.handle_post_message()` 是一个原生 ASGI 应用：
- 它接受 `(scope, receive, send)` 参数
- 它通过 `send()` **直接发送** HTTP 响应（202 Accepted）
- 它**不返回** Response 对象（返回 `None`）

**冲突点：**

Starlette 的 `Route` 期望：
- 处理函数接受 `Request` 对象
- 处理函数**返回** `Response` 对象
- Starlette 负责调用 Response 对象发送响应

**结果：**

```python
# ❌ 使用 Route 会导致冲突
async def handle_messages(request: Request):
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    # handle_post_message 已经发送了响应（202 Accepted）
    # 但这个函数返回 None
    # Starlette 尝试调用 None() -> TypeError: 'NoneType' object is not callable
```

**解决方案：**

```python
# ✅ 使用原生 ASGI，完全绕过 Starlette 的 Route 机制
async def mcp_asgi_app(scope, receive, send):
    if scope['path'] == '/messages':
        # handle_post_message 完全控制响应，没有冲突
        await sse_transport.handle_post_message(scope, receive, send)

starlette_app = mcp_asgi_app  # 直接使用，不经过 Route
```

### ASGI 应用的响应流程

**原生 ASGI 发送响应的步骤：**

```python
async def app(scope, receive, send):
    # 步骤 1: 发送响应头
    await send({
        'type': 'http.response.start',
        'status': 200,
        'headers': [
            (b'content-type', b'text/html'),
            (b'content-length', b'13'),
        ],
    })
    
    # 步骤 2: 发送响应体
    await send({
        'type': 'http.response.body',
        'body': b'Hello, World!',
    })
```

**注意事项：**
- 每个响应只能调用一次 `http.response.start`
- 之后可以多次调用 `http.response.body`（用于流式传输）
- 如果在响应完成后再次调用 `send()`，会触发错误：
  ```
  RuntimeError: Unexpected ASGI message 'http.response.start' sent, after response already completed.
  ```

## 最佳实践

### 1. ASGI 应用的选择
- **使用 Starlette Route：** 适合返回 `Response` 对象的处理函数（常规 REST API）
- **使用原生 ASGI：** 适合直接通过 `send` 发送响应的应用（MCP SSE、WebSocket、流式传输）

### 2. 代码结构
```python
# 1. 创建全局单例
sse_transport = SseServerTransport("/messages")

# 2. 定义原生 ASGI 应用
async def mcp_asgi_app(scope, receive, send):
    # 直接处理请求，完全控制响应
    if scope["path"] == "/sse":
        await handle_sse_connection(scope, receive, send)
    elif scope["path"] == "/messages":
        await handle_messages(scope, receive, send)

# 3. 不使用 Starlette 路由，直接使用 ASGI 应用
starlette_app = mcp_asgi_app
```

### 3. 部署流程
1. **本地开发：** 使用 `pip install -e .` 可编辑安装
2. **代码修改后：** 清除缓存（`find . -name '*.pyc' -delete`）
3. **部署到服务器：**
   - 上传源码（不包括虚拟环境）
   - 在服务器上创建新虚拟环境
   - 安装依赖：`pip install -e .`
4. **更新代码：** 直接 `scp` 上传修改的文件，清除缓存后重启

### 4. 文件上传命令
```powershell
# Windows PowerShell
scp d:\Projects\chatgpts\mcp_mysql\mcp_mysql\server.py ubuntu@server-ip:~/Documents/projects/mcp_mysql/mcp_mysql/
```

```bash
# Linux 服务器
cd ~/Documents/projects/mcp_mysql
find . -name '*.pyc' -delete
python -m mcp_mysql.server
```

## 错误信息速查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `TypeError: 'NoneType' object is not callable` | Route 处理函数返回 None | 使用原生 ASGI 应用，不使用 Route |
| `RuntimeError: response already completed` | 重复发送响应 | 不要在 handle_post_message 后返回 Response |
| `Could not find session for ID` | 使用了不同的 transport 实例 | 创建全局单例 transport |
| `TypeError: does not support async context manager` | 错误使用 SseServerTransport | 使用 `transport.connect_sse()` 方法 |
| `ImportError: cannot import name 'sse_handler'` | MCP SDK API 变更或错误 | 使用正确的 API：`connect_sse()` 和 `handle_post_message()` |

## 成功标志

当服务器正常工作时，你应该看到：

```
INFO:     109.254.2.136:10244 - "POST /messages?session_id=xxx HTTP/1.1" 202 Accepted
2025-11-21 17:00:27,860 - mcp.server.lowlevel.server - INFO - Processing request of type ListToolsRequest
```

- HTTP 状态码：202 Accepted
- 日志显示：`Processing request of type ListToolsRequest`
- 无错误异常

## 总结

MCP SSE 服务器的关键点：

1. ✅ **使用全局单例** `SseServerTransport` 实例
2. ✅ **使用原生 ASGI 应用**，不经过 Starlette 路由
3. ✅ **不要返回 Response 对象**，让 `handle_post_message` 完全控制响应
4. ✅ **清除 Python 字节码缓存** 确保代码更新生效
5. ✅ **在目标平台重建虚拟环境**，不要跨平台复制

通过这些经验，可以避免在部署 MCP SSE 服务器时遇到常见的陷阱。
