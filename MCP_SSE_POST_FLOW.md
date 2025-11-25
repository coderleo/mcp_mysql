# MCP SSE POST 流程与日志分析

此文档基于你提供的日志片段，对 MCP SSE 服务端接收 POST 到 `/messages` 的调用链进行梳理，解释为什么会看到“三次 POST”，并给出排查与防护建议。

## 关键日志片段（节选）

```
2025-11-24 14:18:29,006 - mcp.server.sse - DEBUG - Starting SSE writer
2025-11-24 14:18:29,006 - mcp.server.sse - DEBUG - Sent endpoint event: /messages?session_id=ad57389a...
2025-11-24 14:18:29,015 - __main__ - INFO - 收到 POST 消息
2025-11-24 14:18:29,016 - mcp.server.sse - DEBUG - Received JSON: b'{"method": "initialize", ... "id": 0}'
2025-11-24 14:18:29,018 - mcp.server.sse - DEBUG - Sending message via SSE: SessionMessage(... JSONRPCResponse id=0 ...)
2025-11-24 14:18:29,024 - __main__ - INFO - 收到 POST 消息
2025-11-24 14:18:29,025 - mcp.server.sse - DEBUG - Received JSON: b'{"method": "notifications/initialized", ...}'
2025-11-24 14:18:29,028 - __main__ - INFO - 收到 POST 消息
2025-11-24 14:18:29,029 - mcp.server.sse - DEBUG - Received JSON: b'{"method": "tools/call", "params": {"name": "query", "arguments": {"sql": "select ..."}}, "id": 1}'
```

## 从日志看见的完整交互流程（逐步说明）

1. SSE 连接建立并返回 POST endpoint
   - 服务端在客户端建立 SSE（GET /sse）后，通过 SSE 发送一条 `endpoint` 事件，告诉客户端后续要把 JSON-RPC 消息 POST 到 ` /messages?session_id=...`。

2. 第一次 POST — `initialize` 请求
   - 客户端发送 JSON-RPC `initialize`（带 `id:0`）。
   - `SseServerTransport.handle_post_message` 解析 body，校验并将其封装为 `SessionMessage` 写入该 session 的 read stream（`writer.send(session_message)`），并立即返回 HTTP 202 Accepted 给 POST 发起方。
   - Server 端的 `run()` 循环从 read_stream 读取该消息并处理，随后通过 SSE 将 `id=0` 的响应（capabilities 等）发给客户端。

3. 第二次 POST — `notifications/initialized` 通知
   - 客户端通知服务器自己已初始化完毕（notification，没有 id）。
   - 同样被 `handle_post_message` 读取并注入到 read stream，由 Server 处理。

4. 第三次 POST — `tools/call`（实际执行 query）
   - 这是触发你在服务器上注册的 `@app.call_tool()` handler 的实际请求（带 `id:1` 和 SQL）。
   - `handle_post_message` 将其注入 read stream，Server 在处理该 `CallToolRequest` 时会调用你定义的 `call_tool` 函数，进而执行 SQL 并把结果通过 write_stream -> SSE 发回客户端。

## 为什么是“三次 POST”而不是重复同一请求

- 客户端为完成会话初始化需要分三步发送不同的 JSON-RPC 消息：`initialize`、`notifications/initialized`、`tools/call`；因此日志里出现三次 POST 是正常且预期的。每次 POST 的 body 内容不同（见日志）。

## 关于“同一个 SQL 被多次执行”的可能原因

尽管日志显示 `tools/call` 只在第三次 POST 出现一次，如果你在 MySQL 日志中看到同一 SQL 被执行多次，可能原因包括：

- 客户端重试（网络/超时/代理导致客户端重发请求）
- 客户端在内部逻辑上多次发出相同的 `tools/call`（例如 UI 重试或重复按钮触发）
- 服务器侧在处理时二次调用了数据库（检查 `call_tool` 实现内部是否存在重复调用）
- 存在多个客户端/会话发出了相同的请求（检查 `session_id` 与 client IP）

## 建议的排查步骤（优先级顺序）

1. 在服务端记录更多上下文日志
   - 在 `call_tool` 开头记录 `name`、`arguments`、`request_id`/`session_id`、以及 `request` 中的 `client` 与 `headers`（或至少打印 `session_id` 与 JSON body 的哈希）。
   - `SseServerTransport.handle_post_message` 已有 DEBUG 级 `Received JSON`，可以临时将其提升为 INFO（仅调试时），以确认 POST 是否被发送多次。

2. 对比时间戳与 request id
   - 检查服务端日志中是否存在多条包含相同 `id` 或相同 `tools/call` body 的记录。
   - 对比 MySQL 日志的时间戳，确认数据库执行的时间点是否对应服务端接收到 `tools/call` 的时间点。

3. 检查客户端重试/超时逻辑
   - 在客户端开启请求日志或抓包（或在代理层查看），确认是否有重发。

4. 临时在服务端实现短期幂等保护（可选）
   - 在 `call_tool` 或外层请求处理处，记录最近 N 秒内处理过的 `request_id` 或 `hash(arguments)`；在短时间内重复到达则抑制第二次执行并返回之前的结果或错误。

## 快速排查命令（在项目目录）

启动服务器（PowerShell）：

```powershell
python -m mcp_mysql.server
```

清除 Python 字节码缓存（如果你修改了依赖包或 site-packages 后遇到旧代码被执行）：

```powershell
# Windows PowerShell
Get-ChildItem -Path . -Include *.pyc -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Include __pycache__ -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
```

## 推荐下一步（我可以帮你完成）

- 我可以把 `call_tool` 的详细日志（记录 `arguments`、`session_id`、`request_id`）加回到你的 `mcp_mysql/server.py`，然后你跑一次并把日志贴上来，我来判断是否确实有重复到达 handler。
- 或者我可以示例性地在服务端实现一个短期去重（基于 `id` 或参数哈希）的方案，并说明它的利弊。

---

文件路径：`docs/MCP_SSE_POST_FLOW.md`

如需我现在把详细日志加回代码进行一次实测，请回复“加日志并运行”。
