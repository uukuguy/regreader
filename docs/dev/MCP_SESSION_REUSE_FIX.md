# MCP 会话复用优化

## 问题描述

用户在使用主智能体模式时发现严重的性能问题：

### 问题 1：重复加载嵌入模型
每次调用 MCP 工具时都会重新加载嵌入模型（耗时 1.7 秒），导致：
- 4 次工具调用 = 6.8 秒（仅模型加载）
- 资源浪费
- 性能极差

### 问题 2：传输模式错误
用户指定了 `--mcp-transport sse`（连接远程 MCP Server），但系统仍使用 `stdio` 模式（启动本地子进程）。

### 日志证据
```bash
[MCP] Starting stdio mode...  # 每次调用都启动新子进程
2026-01-16 21:30:01.237 | INFO | 预加载嵌入模型...
2026-01-16 21:30:02.942 | INFO | 模型加载完成
```

## 根本原因分析

### 原因 1：每次调用创建新会话

`RegReaderMCPToolsAdapter` 的 `_call_tool_async()` 方法：

```python
async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
    async with self._create_session() as session:  # ❌ 每次都创建新会话
        result = await session.call_tool(name, arguments)
```

使用 `async with` 会导致：
- 每次调用创建新的 `AsyncExitStack`
- 每次调用启动新的子进程（stdio）或建立新连接（sse）
- 每次调用都重新加载嵌入模型

### 原因 2：MCP 配置未传递

- 用户在 CLI 指定 `--mcp-transport sse`
- CLI 创建 MainAgent 时没有传递 MCP 配置
- MainAgent 创建子智能体时也没有传递 MCP 配置
- 子智能体回退到默认配置（`settings.mcp_transport="stdio"`）

## 解决方案

### 方案 1：实现会话复用

修改 `RegReaderMCPToolsAdapter` 来支持会话复用：

```python
class RegReaderMCPToolsAdapter:
    def __init__(self, transport, server_url):
        self.transport = transport
        self.server_url = server_url
        self._session: ClientSession | None = None  # 会话缓存
        self._session_lock = asyncio.Lock()

    async def _get_or_create_session(self) -> ClientSession:
        """获取或创建会话（支持复用）"""
        async with self._session_lock:
            if self._session is None:
                logger.info(f"[MCP] 创建新会话: {self.transport} 模式")

                # 创建会话（手动管理生命周期）
                async_exit_stack = AsyncExitStack()

                if self.transport == "stdio":
                    transport = await async_exit_stack.enter_async_context(
                        stdio_client(server_params)
                    )
                else:
                    transport = await async_exit_stack.enter_async_context(
                        sse_client(self.server_url)
                    )

                session = await async_exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()

                # 保存会话和清理栈
                self._session = session
                self._exit_stack = async_exit_stack

            return self._session

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        """异步调用 MCP 工具（会话复用）"""
        session = await self._get_or_create_session()  # ✅ 复用会话
        result = await session.call_tool(name, arguments)
        return result

    async def close(self):
        """关闭会话并清理资源"""
        async with self._session_lock:
            if self._session is not None:
                await self._exit_stack.aclose()
                self._session = None
```

**关键改进**：
1. 首次调用时创建会话并缓存
2. 后续调用复用已缓存的会话
3. 只加载一次嵌入模型
4. 手动管理会话生命周期

### 方案 2：传递 MCP 配置

修改 MainAgent 和子智能体来接收并传递 MCP 配置：

#### BaseSubagentFS
```python
def __init__(
    self,
    workspace: Path,
    reg_id: str,
    framework: str = "claude",
    mcp_transport: str | None = None,  # 新增
    mcp_host: str | None = None,        # 新增
    mcp_port: int | None = None,        # 新增
):
    # MCP 配置（优先使用传递的参数，否则从配置读取）
    from regreader.core.config import get_settings
    settings = get_settings()

    self.mcp_transport = mcp_transport or settings.mcp_transport
    self.mcp_host = mcp_host or settings.mcp_host
    self.mcp_port = mcp_port or settings.mcp_port
```

#### MainAgent
```python
def __init__(
    self,
    reg_id: str,
    mcp_transport: str | None = None,  # 新增
    mcp_host: str | None = None,        # 新增
    mcp_port: int | None = None,        # 新增
):
    # MCP 配置
    self.mcp_transport = mcp_transport or settings.mcp_transport
    self.mcp_host = mcp_host or settings.mcp_host
    self.mcp_port = mcp_port or settings.mcp_port
```

#### SearchAgent
```python
search_agent = SearchAgent(
    workspace=...,
    reg_id=...,
    mcp_transport=self.mcp_transport,  # 传递配置
    mcp_host=self.mcp_host,
    mcp_port=self.mcp_port,
)
```

#### CLI
```python
agent = MainAgent(
    reg_id=reg_id or "angui_2024",
    mcp_transport=mcp_transport,  # 从 CLI 参数传递
    mcp_host=mcp_host,
    mcp_port=mcp_port,
)
```

## 验证结果

### 性能对比

**修复前**（每次调用创建新会话）：
```bash
[MCP] Starting stdio mode...
预加载嵌入模型... 1.7s
✅ Tool Done: get_toc (2.1ms)

[MCP] Starting stdio mode...  # ❌ 重复加载
预加载嵌入模型... 1.7s
✅ Tool Done: smart_search (156.7ms)
```

**修复后**（会话复用）：
```bash
[MCP] 创建新会话: sse 模式  # 只创建一次
预加载嵌入模型... 1.7s
✅ Tool Done: get_toc (2.1ms)

✅ Tool Done: smart_search (156.7ms)  # ✅ 复用会话，无需重新加载
```

### 测试验证

```python
# 测试脚本：tests/agents/test_mcp_session_reuse.py
adapter = RegReaderMCPToolsAdapter(
    transport="sse",
    server_url="http://127.0.0.1:8080/sse"
)

# 首次调用：创建会话（1.7s）
result1 = adapter.list_regulations()

# 第二次调用：复用会话（<0.1s）
result2 = adapter.list_regulations()

# 第三次调用：复用会话（<0.1s）
toc = adapter.get_toc("angui_2024")
```

**预期输出**：
```
[1] 首次调用：list_regulations()
[MCP] 创建新会话: sse 模式
预加载嵌入模型...
✓ 返回 X 个规程

[2] 第二次调用：list_regulations()（应该复用会话）
✓ 返回 X 个规程  # 无日志，因为复用会话

[3] 第三次调用：get_toc()
✓ 返回目录结构...
```

## 使用方式

### 启动 MCP Server（SSE 模式）

```bash
# 启动 MCP Server
regreader serve --transport sse --port 8080
```

### 使用主智能体模式

```bash
# 使用 SSE 模式连接远程 MCP Server
regreader ask "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？" \
  -r angui_2024 \
  --agent claude \
  -m \
  --mcp-transport sse \
  --mcp-url http://127.0.0.1:8080/sse
```

**性能优势**：
- ✅ 只加载一次嵌入模型
- ✅ 复用 MCP 会话
- ✅ 避免重复启动子进程
- ✅ 显著提升响应速度

## 技术要点

### 1. 会话生命周期管理

- **创建**：首次调用时创建
- **复用**：后续调用直接返回已创建的会话
- **清理**：调用 `close()` 或 `__del__` 时清理资源
- **线程安全**：使用 `asyncio.Lock()` 保证并发安全

### 2. 资源清理

```python
async def close(self):
    """关闭 MCP 会话并清理资源"""
    async with self._session_lock:
        if self._session is not None:
            await self._exit_stack.aclose()
            self._session = None
            self._exit_stack = None
```

### 3. 事件循环处理

已在之前修复：`_run_async()` 方法支持在已有事件循环中运行。

## 后续优化

1. **连接池**：支持多个 SSE 连接的负载均衡
2. **自动重连**：网络中断时自动重连
3. **心跳检测**：定期检测会话健康状态
4. **监控指标**：记录会话创建、复用、清理的次数

## 相关文件

- `src/regreader/mcp/adapter.py` - MCP 适配器（会话复用）
- `src/regreader/subagents/bash_fs_base.py` - 子智能体基类（MCP 配置）
- `src/regreader/subagents/search/agent.py` - SearchAgent（MCP 配置）
- `src/regreader/agents/main/agent.py` - MainAgent（MCP 配置传递）
- `src/regreader/cli.py` - CLI（MCP 配置传递）
- `tests/agents/test_mcp_session_reuse.py` - 会话复用测试
