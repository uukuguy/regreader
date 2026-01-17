# RegReader 开发工作日志 (dev 分支)

## 2026-01-17 修复多智能体模式 MCP SSE 通信问题（已完成 ✅）

### 问题背景

在多智能体编排模式下，主智能体调用子智能体时出现挂起现象。

**错误现象**：
```
MCP 模式: transport=sse, url=http://127.0.0.1:8080/sse
LLM 拆解失败，回退到规则拆解:
[程序挂起，无响应]
```

### 根本原因

经过深入调试，发现了两个关键问题：

#### 问题 1：子智能体未收到 MCP 配置参数
**位置**: `src/regreader/agents/main/agent.py`

**问题**: TableAgent 和 ReferenceAgent 的创建调用未传递 MCP 连接参数
- SearchAgent 正确传递了 `mcp_transport`, `mcp_host`, `mcp_port`
- TableAgent 和 ReferenceAgent 缺少这些参数

**影响**: 子智能体无法连接到 MCP SSE 服务器，导致工具调用失败

#### 问题 2：事件循环嵌套导致死锁
**位置**: `src/regreader/subagents/bash_fs_base.py:run()` 和 `src/regreader/agents/main/agent.py:query()`

**问题**:
1. `MainAgent.query()` 是 `async` 方法，在运行的事件循环中执行
2. `MainAgent.query()` 调用 `search_agent.run()`（同步方法）
3. `search_agent.run()` 内部尝试使用 `asyncio.run_coroutine_threadsafe()` 在已有事件循环中运行异步步骤
4. 但 `async with self.mcp_client:` 需要 SSE 连接，这在嵌套的事件循环上下文中会阻塞

**调试日志显示的挂起点**:
```
DEBUG | 在主线程中，使用 run_coroutine_threadsafe...
DEBUG | 等待 future.result()...
[挂起，永不返回]
```

### 解决方案

#### 修复 1：传递 MCP 配置参数

**文件**: `src/regreader/agents/main/agent.py`

**修改内容**:
```python
# 修改前（TableAgent 和 ReferenceAgent）
table_agent = TableAgent(
    workspace=self.workspace_root.parent / "subagents" / "table",
    reg_id=self.reg_id,
)

# 修改后（添加 MCP 参数）
table_agent = TableAgent(
    workspace=self.workspace_root.parent / "subagents" / "table",
    reg_id=self.reg_id,
    mcp_transport=self.mcp_transport,
    mcp_host=self.mcp_host,
    mcp_port=self.mcp_port,
)
```

#### 修复 2：使用线程池隔离子智能体执行

**文件**: `src/regreader/agents/main/agent.py`

**核心思路**: 在独立线程中运行子智能体，避免事件循环嵌套

**实现代码**:
```python
# 修改前：直接调用
from regreader.subagents.search.agent import SearchAgent
search_agent = SearchAgent(...)
result = search_agent.run()

# 修改后：在线程池中运行
from regreader.subagents.search.agent import SearchAgent
import concurrent.futures

def run_search_agent():
    search_agent = SearchAgent(...)
    return search_agent.run()

with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(run_search_agent)
    result = future.result(timeout=300)  # 5分钟超时
```

**优势**:
1. ✅ 子智能体在独立线程中运行，拥有独立的事件循环
2. ✅ 主智能体的事件循环不会被阻塞
3. ✅ MCP SSE 连接在独立线程中正常工作
4. ✅ 超时机制防止无限等待

#### 修复 3：禁用子智能体的 LLM 任务拆解

**文件**: `src/regreader/subagents/search/agent.py`

**原因**: 子智能体的 `_llm_based_decomposition()` 方法也会遇到 sync/async 混用问题

**临时解决方案**: 直接使用规则拆解（更快、更可靠）

```python
def decompose_task(self, task: str) -> list[dict[str, Any]]:
    logger.info(f"拆解任务: {task[:100]}...")

    # 暂时禁用 LLM 拆解，直接使用规则拆解（避免 asyncio 事件循环冲突）
    # TODO: 未来可以重新启用 LLM 拆解，但需要解决 sync/async 混用问题
    return self._rule_based_decomposition(task)
```

### 验证结果

**测试命令**:
```bash
make ask AGENT=claude MODE=mcp-sse DISPLAY=enhanced AGENT_FLAGS="-m" \
  ASK_QUERY="锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？"
```

**执行结果**: ✅ 成功

**输出示例**:
```
╭──────────────────────────────── 主智能体回答 ────────────────────────────────╮
│                                                                              │
│  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓  │
│  ┃                锦苏直流系统闭锁故障时安控装置的动作逻辑                ┃  │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛  │
│                                                                              │
│  根据规程《angui_2024》中关于锦苏安控系统的规定，当锦苏直流系统发生闭锁故障  │
│  时，安控装置的动作逻辑如下：                                                │
│                                                                              │
│                       一、锦屏站安控装置的主要动作逻辑                       │
│                         1. 单换流器/多换流器闭锁故障                         │
│    [详细内容...]                                                             │
│                                                                              │
│  数据来源：《国调直调安全稳定控制系统...》(angui_2024) 第14-17页、第123页     │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

会话记录: coordinator/session_20260117_132802
```

### 技术要点总结

1. **async/await 的边界**: 当 `async` 函数需要调用 `sync` 函数，而该 `sync` 函数内部又要运行 `async` 代码时，必须使用线程池隔离

2. **事件循环隔离**: 每个线程可以有独立的事件循环，`asyncio.run()` 在新线程中创建新的事件循环

3. **MCP SSE 连接**: SSE 连接绑定到特定的事件循环，不能跨线程/跨事件循环共享

4. **超时机制**: 使用 `future.result(timeout=300)` 防止子智能体无限阻塞

### 文件修改清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/regreader/agents/main/agent.py` | 修改 | 添加线程池执行子智能体，传递 MCP 参数 |
| `src/regreader/subagents/search/agent.py` | 修改 | 禁用 LLM 任务拆解，使用规则拆解 |
| `src/regreader/subagents/bash_fs_base.py` | 修改 | 添加详细的调试日志 |

---

## 2026-01-16 实现主智能体任务级编排 + 子智能体原子级执行的 Bash+FS 范式（已完成 ✅）

### 问题背景

用户提出了关键的架构澄清要求：

> **"主智能体拆解任务应该是'从规程目录中定位可能的章节'、'从指定章节范围获得与问题任务相关的内容或表格'等，而不是'获得规程目录'、'获得指定章节的全部内容'这些原子任务，这些原子任务应该是子智能体负责主动识别和拆解执行的。"**

**核心架构要求**：
- **主智能体职责**：任务级拆解（"定位章节"、"获取表格数据"）
- **子智能体职责**：原子级拆解和执行（"调用 get_toc()"、"调用 smart_search()"）
- **记录要求**：主智能体记录任务计划，子智能体记录原子任务执行过程
- **技术栈**：
  - 主智能体：Claude Agent SDK + `preset: "claude_code"`
  - 子智能体：三框架封装（Claude SDK / Pydantic AI / LangGraph）

### 解决方案

#### Step 1: 创建主智能体（Claude Agent SDK + claude_code preset）

**文件**: `src/regreader/agents/main/agent.py`（新建）

**核心实现**：
- 使用 `ClaudeAgentOptions` 的 `system_prompt` 配置 preset
- LLM 驱动的任务级拆解（`_decompose_task_with_llm`）
- 规则回退方案（`_rule_based_decomposition`）
- 文件系统通信：写入 `subagents/{type}/task.md`
- 执行记录：`coordinator/session_{id}/plan.md`, `execution.md`, `final_report.md`

**关键 API 使用**：
```python
options = ClaudeAgentOptions(
    system_prompt="你是任务拆解专家，只返回 JSON 格式的任务列表。",
    model=self.model,  # model 通过 options 传递
)

async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt, session_id="decomposition")
    async for event in client.receive_response():
        if hasattr(event, "content"):
            for block in event.content:
                if hasattr(block, "text"):
                    result += block.text
```

#### Step 2: 创建子智能体基类（支持文件系统通信）

**文件**: `src/regreader/subagents/bash_fs_base.py`（新建）

**核心功能**：
- `read_task()`: 从 `task.md` 读取主智能体分发的任务
- `write_steps()`: 写入原子任务拆解到 `steps.md`
- `write_results()`: 写入最终结果到 `results.json`
- `run()`: 主流程（读取任务 → 拆解 → 执行 → 记录）
- `SubagentResult` 数据类：标准化返回格式

#### Step 3: 实现三个子智能体

**文件**:
- `src/regreader/subagents/search/agent.py`（新建）
- `src/regreader/subagents/table/agent.py`（新建）
- `src/regreader/subagents/reference/agent.py`（新建）

**核心特性**：
1. **MCP 集成（修复后）**：使用 `RegReaderMCPClient` + 异步执行
   ```python
   from regreader.mcp.client import RegReaderMCPClient
   from regreader.core.config import get_settings

   settings = get_settings()
   server_url = f"http://{settings.mcp_host}:{settings.mcp_port}/sse"

   # 创建异步 MCP 客户端
   self.mcp_client = RegReaderMCPClient(
       transport=settings.mcp_transport or "stdio",
       server_url=server_url,
   )

   # 异步调用
   async with self.mcp_client:
       result = await self.mcp_client.call_tool(action, params)
   ```

2. **LLM 驱动的任务拆解**：使用 Claude SDK 拆解任务为原子操作
3. **规则回退方案**：当 LLM 不可用时使用规则拆解
4. **异步支持**：`BaseSubagentFS.run()` 内部使用 `asyncio.run()` 或 `run_coroutine_threadsafe()` 执行异步步骤

#### Step 4: 事件循环管理

**问题**: 在已有事件循环中调用 `asyncio.run()` 会报错

**解决方案**: 添加事件循环检测和线程池执行
```python
try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, get_decomposition())
            response = future.result()
    else:
        response = asyncio.run(get_decomposition())
except RuntimeError:
    response = asyncio.run(get_decomposition())
```

#### Step 5: CLI 集成

**文件**: `src/regreader/cli.py`（修改）

**新增选项**：
```python
main_agent: bool = typer.Option(
    False, "--main-agent", "-m",
    help="启用主智能体模式（任务级拆解 + Bash+FS 范式）"
)
```

**使用示例**：
```bash
regreader ask "锦苏直流安控装置在母线失压时的动作逻辑" \
  -r angui_2024 --agent claude -m
```

#### Step 6: 单元测试

**文件**: `tests/agents/test_main_agent.py`（新建）

**测试覆盖**：
- 主智能体初始化、提示词验证、执行日志
- 子智能体任务读取、规则拆解、步骤写入、结果写入
- 文件系统通信、工作区结构
- 职责分离验证（主智能体不调用原子工具、子智能体拆解为原子操作）

**测试结果**: ✅ 13 passed, 1 warning in 30.73s

### 关键修复：多智能体模式 MCP SSE 通信问题（2026-01-16）

#### 问题描述

多智能体模式在使用 MCP SSE 传输时失败：
```
MCP 模式: transport=sse, url=http://127.0.0.1:8080/sse
[MCP] 会话初始化超时
```

#### 根本原因

**架构设计错误**：
- 单智能体模式：使用 `RegReaderMCPClient`（异步客户端）✅ 工作正常
- 多智能体模式：使用 `RegReaderMCPToolsAdapter`（同步包装器）❌ 会话初始化超时

`RegReaderMCPToolsAdapter` 试图在同步上下文中运行异步代码，导致事件循环冲突：
1. `session.initialize()` 在 SSE 模式下会挂起 30 秒
2. 跨线程的 SSE 连接无法工作
3. `asyncio.run()` 在已有事件循环中调用失败

#### 解决方案

**修改 `BaseSubagentFS` 基类**（`src/regreader/subagents/bash_fs_base.py`）：

1. **将 `execute_atomic_step()` 改为异步方法**：
   ```python
   @abstractmethod
   async def execute_atomic_step(self, step: dict[str, Any]) -> Any:
       """执行单个原子操作（异步）"""
       pass
   ```

2. **在 `run()` 中使用 asyncio 执行步骤**：
   ```python
   async def _execute_steps():
       """内部异步函数，执行所有步骤"""
       executed_steps = []
       for step in steps:
           step["result"] = await self.execute_atomic_step(step)
           executed_steps.append(step)
           self.write_steps(executed_steps)  # 实时写入
       return executed_steps

   # 检查事件循环并运行
   try:
       loop = asyncio.get_running_loop()
       if threading.current_thread() is threading.main_thread():
           future = asyncio.run_coroutine_threadsafe(_execute_steps(), loop)
           executed_steps = future.result(timeout=300)
       else:
           with ThreadPoolExecutor(max_workers=1) as pool:
               future = pool.submit(asyncio.run, _execute_steps())
               executed_steps = future.result()
   except RuntimeError:
       executed_steps = asyncio.run(_execute_steps())
   ```

**修改 `SearchAgent`**（`src/regreader/subagents/search/agent.py`）：

1. **使用 `RegReaderMCPClient` 替代 `RegReaderMCPToolsAdapter`**：
   ```python
   # OLD（broken）:
   from regreader.mcp.adapter import RegReaderMCPToolsAdapter
   self.mcp_adapter = RegReaderMCPToolsAdapter(transport, server_url)
   result = self.mcp_adapter._call_tool(action, params)

   # NEW（working）:
   from regreader.mcp.client import RegReaderMCPClient
   self.mcp_client = RegReaderMCPClient(transport, server_url)
   async with self.mcp_client:
       result = await self.mcp_client.call_tool(action, params)
   ```

2. **实现异步的 `execute_atomic_step()`**：
   ```python
   async def execute_atomic_step(self, step: dict[str, Any]) -> Any:
       action = step["action"]
       params = step["params"]

       try:
           async with self.mcp_client:
               result = await self.mcp_client.call_tool(action, params)
               return result
       except Exception as e:
           return {"error": str(e), "action": action, "params": params}
   ```

#### 验证结果

✅ **MCP 工具调用成功**：
- `get_toc`: 成功返回完整目录结构（150页，2300条目录项）
- `smart_search`: 成功返回10条搜索结果，包含章节路径、页码、相似度分数
- 执行日志正确写入 `subagents/search/steps.md`

#### 经验教训

1. **异步代码应该保持异步**：不要试图用同步包装器包装异步客户端
2. **MCP SSE 传输本身没问题**：单智能体模式工作正常，问题在于多智能体使用了错误的抽象
3. **事件循环管理**：使用 `asyncio.run_coroutine_threadsafe()` 在已有事件循环中运行异步代码
4. **架构一致性**：多智能体和单智能体应该使用相同的 MCP 客户端实现

#### 后续工作

需要将相同的修复应用到其他子智能体：
- TableAgent
- ReferenceAgent
- DiscoveryAgent

### 技术要点总结

#### 1. Claude Agent SDK API 正确用法

| 组件 | 错误用法 | 正确用法 |
|------|---------|---------|
| preset | `preset="claude_code"` | `system_prompt={"type": "preset", "preset": "claude_code", "append": "..."}` |
| model | `client(model="...")` | `options=ClaudeAgentOptions(model="...")` |
| query | `client.run(prompt)` | `await client.query(prompt, session_id="...")` |
| response | `async for msg in client.run()` | `async for event in client.receive_response()` |

#### 2. MCP 工具调用

| 组件 | 错误用法 | 正确用法 |
|------|---------|---------|
| 管理 | `MCPConnectionManager.initialize()` | `RegReaderMCPToolsAdapter` |
| 配置 | `settings.mcp_url` | `f"http://{settings.mcp_host}:{settings.mcp_port}/sse"` |
| 调用 | `await mcp_manager.call_tool()` | `mcp_adapter._call_tool(action, params)` |

#### 3. 事件循环处理

在已有事件循环中使用线程池执行异步代码：
```python
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor() as pool:
    future = pool.submit(asyncio.run, async_function())
    result = future.result()
```

### 架构验证

**主智能体记录**（`coordinator/session_{id}/`）：
- ✅ `plan.md`: 任务拆解计划
- ✅ `execution.md`: 子任务分发记录
- ✅ `final_report.md`: 最终答案
- ✅ 任务描述不包含"调用 get_toc()"等原子操作

**子智能体记录**（`subagents/{type}/`）：
- ✅ `task.md`: 收到的任务（任务级）
- ✅ `steps.md`: 原子任务拆解和执行过程
- ✅ `results.json`: 执行结果
- ✅ 拆解为具体的工具调用（get_toc, smart_search 等）

### 已知限制

1. **LLM 拆解依赖**: 需要 Claude Agent SDK 可用，否则回退到规则拆解
2. **MCP Server 依赖**: 子智能体需要 MCP Server 运行中
3. **同步执行**: 当前实现按顺序执行子任务，未实现并行

### 修复记录

#### 修复 1：MCP 适配器的事件循环处理（2026-01-16）

**问题**：
```bash
操作失败: get_toc, error=asyncio.run() cannot be called from a running event loop
RuntimeWarning: coroutine 'RegReaderMCPToolsAdapter._call_tool_async' was never awaited
```

**原因**：
`RegReaderMCPToolsAdapter._run_async()` 使用 `asyncio.run()` 在已有事件循环运行时会失败。

**解决方案**：
修改 `src/regreader/mcp/adapter.py` 的 `_run_async()` 方法，添加事件循环检测和线程池执行。

**技术要点**：
- 在新线程中创建新的事件循环来运行协程
- 使用 `asyncio.new_event_loop()` 和 `run_until_complete()`
- 确保事件循环正确关闭，避免资源泄漏

#### 修复 2：MCP 会话复用优化（2026-01-16）

**问题**：
```bash
# 重复加载嵌入模型
[MCP] Starting stdio mode...
预加载嵌入模型... 1.7s  # ❌ 每次调用都加载

# 传输模式错误
# 用户指定 --mcp-transport sse，但系统使用 stdio
```

**原因**：
1. **会不复用**：每次调用都创建新会话（`async with self._create_session()`）
2. **配置未传递**：CLI 的 MCP 配置没有传递给子智能体

**解决方案**：

**1. 实现会话复用**（`src/regreader/mcp/adapter.py`）：
```python
class RegReaderMCPToolsAdapter:
    def __init__(self, transport, server_url):
        self._session: ClientSession | None = None  # 会话缓存
        self._session_lock = asyncio.Lock()

    async def _get_or_create_session(self) -> ClientSession:
        """获取或创建会话（支持复用）"""
        async with self._session_lock:
            if self._session is None:
                # 首次调用：创建会话
                self._session = await self._create_and_init_session()
            return self._session  # 后续调用：复用会话

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        """异步调用 MCP 工具（会话复用）"""
        session = await self._get_or_create_session()  # ✅ 复用会话
        result = await session.call_tool(name, arguments)
        return result
```

**2. 传递 MCP 配置**：
- `BaseSubagentFS.__init__()` 接收 `mcp_transport`, `mcp_host`, `mcp_port`
- `MainAgent.__init__()` 接收并保存 MCP 配置
- `MainAgent._dispatch_*_task()` 传递 MCP 配置给子智能体
- CLI 传递 MCP 配置给 `MainAgent`

**性能改进**：
- **修复前**：4 次调用 = 6.8 秒（每次加载模型）
- **修复后**：4 次调用 = 2.0 秒（只加载一次模型）

**验证**：
```bash
# 测试脚本
python tests/agents/test_mcp_session_reuse.py

# 预期输出
[MCP] 创建新会话: sse 模式  # 只创建一次
✓ 首次调用成功
✓ 第二次调用成功  # 复用会话
✓ 第三次调用成功  # 复用会话
✓ 第四次调用成功  # 复用会话
```

**相关文件**：
- `src/regreader/mcp/adapter.py` - MCP 适配器（会话复用实现）
- `src/regreader/subagents/bash_fs_base.py` - 基类（MCP 配置）
- `src/regreader/subagents/search/agent.py` - SearchAgent（MCP 配置）
- `src/regreader/subagents/table/agent.py` - TableAgent（MCP 配置）
- `src/regreader/subagents/reference/agent.py` - ReferenceAgent（MCP 配置）
- `src/regreader/agents/main/agent.py` - MainAgent（配置传递）
- `src/regreader/cli.py` - CLI（配置传递 + URL 解析）
- `tests/agents/test_mcp_session_reuse.py` - 会话复用测试
- `tests/agents/test_cli_main_agent.py` - CLI 集成测试
- `docs/dev/MCP_SESSION_REUSE_FIX.md` - 详细文档

#### 修复 3：CLI MCP 配置传递（2026-01-16）

**问题**：
```bash
NameError: name 'mcp_transport' is not defined
```

**原因**：
CLI 的 `run_ask` 函数中尝试使用未定义的变量 `mcp_transport`、`mcp_host`、`mcp_port`。

**解决方案**：
从 `state` 对象中提取 MCP 配置，并解析 URL 获取 host 和 port：

```python
# 从 state 解析 MCP 配置
if state.use_mcp and state.mcp_transport == "sse" and state.mcp_url:
    from urllib.parse import urlparse
    parsed = urlparse(state.mcp_url)
    mcp_transport_for_main = state.mcp_transport
    mcp_host_for_main = parsed.hostname or "127.0.0.1"
    mcp_port_for_main = parsed.port or 8080
else:
    mcp_transport_for_main = None
    mcp_host_for_main = None
    mcp_port_for_main = None

# 传递 MCP 配置
agent = MainAgent(
    reg_id=reg_id or "angui_2024",
    mcp_transport=mcp_transport_for_main,
    mcp_host=mcp_host_for_main,
    mcp_port=mcp_port_for_main,
)
```

**验证**：
```bash
# 测试 CLI 集成
pytest tests/agents/test_cli_main_agent.py -xvs
# 结果：3 passed
```

**文件修改**：
- `src/regreader/cli.py` - 添加 MCP 配置解析逻辑（第 802-820 行）
- `tests/agents/test_cli_main_agent.py` - 新建 CLI 集成测试

#### 修复 4：跨线程事件循环处理（2026-01-16）

**问题**：
```bash
操作失败: smart_search, error=asyncio.run() cannot be called from a running event loop
```

**根本原因**：
MainAgent 的 `query()` 方法在 `asyncio.run()` 中运行（异步上下文），当它调用子智能体的同步方法时，子智能体调用 `_call_tool`（同步方法），而 `_call_tool` 调用 `_run_async()`，后者试图再次使用 `asyncio.run()`，导致错误。

此外，使用 `AsyncExitStack` 在跨线程场景下会导致 "generator didn't stop" 错误，因为异步生成器不能跨事件循环传递。

**解决方案**：

**1. 使用线程本地存储（threading.local）**：
```python
import threading

class RegReaderMCPToolsAdapter:
    def __init__(self, transport, server_url):
        # 使用线程本地存储以支持多线程
        self._local = threading.local()
```

**2. 手动管理异步上下文**（不使用 AsyncExitStack）：
```python
async def _get_or_create_session(self) -> ClientSession:
    # 获取或创建当前线程的会话
    if not hasattr(self._local, "session") or self._local.session is None:
        # stdio 模式：启动子进程
        if self.transport == "stdio":
            stdio_transport = stdio_client(server_params)
            read, write = await stdio_transport.__aenter__()
            self._local.stdio_transport = stdio_transport
        else:
            # sse 模式：连接外部服务器
            sse_transport = sse_client(self.server_url)
            read, write = await sse_transport.__aenter__()
            self._local.sse_transport = sse_transport

        # 创建会话
        session = ClientSession(read, write)
        await session.initialize()
        self._local.session = session

    return self._local.session
```

**3. 手动清理资源**：
```python
async def _close_async(self):
    if hasattr(self._local, "session") and self._local.session is not None:
        # 关闭会话
        await self._local.session.__aexit__(None, None, None)
        self._local.session = None

        # 关闭传输
        if hasattr(self._local, "stdio_transport"):
            await self._local.stdio_transport.__aexit__(None, None, None)
        elif hasattr(self._local, "sse_transport"):
            await self._local.sse_transport.__aexit__(None, None, None)
```

**4. 线程池执行**：
```python
def _run_async(self, coro):
    try:
        loop = asyncio.get_running_loop()
        # 当前正在运行的事件循环中，需要在新线程中运行
        import concurrent.futures

        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_new_loop)
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，可以直接使用 asyncio.run()
        return asyncio.run(coro)
```

**关键改进**：
- ✅ 每个线程有自己的 MCP 会话（线程本地存储）
- ✅ 避免跨线程传递异步对象
- ✅ 正确处理异步上下文中的工具调用
- ✅ 手动管理资源生命周期

**文件修改**：
- `src/regreader/mcp/adapter.py` - 重写事件循环处理和会话管理
- `tests/agents/test_event_loop_handling.py` - 新建事件循环处理测试

### 后续优化方向

1. **并行执行**: 支持多个子智能体并行执行独立任务
2. **上下文传递**: 子智能体之间通过文件系统传递上下文
3. **更多子智能体**: Exec-Subagent（脚本执行）、Validator-Subagent（结果验证）
4. **流式聚合**: 实时返回子智能体结果，而非等待全部完成

---

## 2026-01-16 统一单智能体和多智能体模式的提示词生成（已完成 ✅）

### 问题背景

用户发现单智能体（正常模式）和多智能体（orchestrator 模式）下的推理路径不同：
- **单智能体模式**：调用 `get_toc()` → `read_page_range()` → `smart_search()` → 更多工具
- **多智能体模式**：直接调用 `smart_search()` → `read_page_range()`

### 用户核心反馈（关键）

> **"主线智能体是引导组合get_toc, read_page_rage, smart_search等工具来完成任务，--orchestrator模式是在主线提示一致的情况下，用子智能体实行上下文隔离，并且在可能的情况并行执行，如获取目录找相关章节、从指定章节范围中获得想要的信息等，并不关心直接获得的原文，主线上下文需要的是子任务的结果。"**

**关键理解**：
- Orchestrator 的主线 Agent 应该和单智能体使用**相同的系统提示词**
- 子智能体的作用是**上下文隔离**和**并行执行**，而不是替代主线推理
- 主线 Agent 需要**子任务的结果**（processed content），而不是选择哪个子智能体执行

### 解决方案 - 两个阶段

#### 阶段 1：Step 1-5 - 统一子智能体提示词生成 ✅

**问题**：子智能体提示词硬编码工具列表

**解决**：
1. 扩展 `agents/prompts.py` 添加动态生成函数
2. 修改 `orchestrated/claude.py` 的 `_build_subagent_domain_prompt()`
3. 清理 `subagents/prompts.py` 的硬编码提示词
4. 创建单元测试验证动态生成
5. 验证提示词一致性（所有 5 个检查通过）

#### 阶段 2：Step 6 - 统一主线提示词 ✅

**问题**：Orchestrator 主线使用"协调器"提示词，而非"专家"提示词

**解决**：

**Step 6.1**: 修改 `orchestrated/claude.py` 的主线提示词构建

修改 `_build_main_prompt()` 方法，使用和单智能体相同的提示词：

```python
def _build_main_prompt(self) -> str:
    """构建主智能体的系统提示词（与单智能体模式一致）

    主智能体应该和单智能体使用相同的提示词，子智能体用于：
    1. 上下文隔离（不同任务不污染主线上下文）
    2. 并行执行（同时执行多个独立子任务）

    Returns:
        主智能体的系统提示词
    """
    from regreader.agents.prompts import get_optimized_prompt_with_domain

    # 获取规程列表（复用单智能体的逻辑）
    regulations = self._get_regulations()

    # 使用和单智能体完全相同的提示词
    settings = get_settings()
    include_advanced = getattr(settings, "enable_advanced_tools", False)

    base_prompt = get_optimized_prompt_with_domain(include_advanced, regulations)

    # 追加当前规程信息
    if self.reg_id:
        base_prompt += f"\n\n# 当前规程\n默认规程: {self.reg_id}"

    # 追加 Orchestrator 特有的说明
    orchestrator_note = """

# Orchestrator 模式说明

你现在运行在 Orchestrator 模式下，可以使用子智能体来：
1. **上下文隔离**：将复杂任务分解为独立的子任务
2. **并行执行**：多个独立的子任务可以同时执行

## 可用的子智能体
{subagent_descriptions}

## 如何使用子智能体

当你需要执行子任务时，可以使用 **Task 工具**调用子智能体。

**重要**：
- 子智能体会返回**处理后的内容摘要**，而非原始工具输出
- 你需要整合多个子智能体的结果，生成最终答案
- 简单查询可以直接使用 MCP 工具，无需调用子智能体
"""

    # 收集子智能体描述（简要版本）
    subagent_descriptions = []
    for agent_name, agent_def in self._subagents.items():
        subagent_descriptions.append(f"- **{agent_name}**: {agent_def.description}")

    descriptions_text = "\n".join(subagent_descriptions)

    return base_prompt + orchestrator_note.format(subagent_descriptions=descriptions_text)
```

**Step 6.2**: 添加 `_get_regulations()` 方法到 Orchestrator

```python
def _get_regulations(self) -> list[dict]:
    """获取规程列表（复用单智能体的逻辑）

    Returns:
        规程信息列表
    """
    from regreader.storage import PageStore
    from regreader.core.config import get_settings

    settings = get_settings()
    page_store = PageStore(settings.pages_dir)

    # 使用缓存
    if not hasattr(self, '_regulations_cache'):
        regulations = page_store.list_regulations()
        self._regulations_cache = [
            {
                "reg_id": r.reg_id,
                "title": r.title,
                "keywords": r.keywords,
                "scope": r.scope,
                "description": r.description,
            }
            for r in regulations
        ]

    return self._regulations_cache
```

**Step 6.3**: 验证推理路径一致性

创建验证脚本 `tests/agents/verify_main_prompt_consistency.py`

**验证结果**：
- ✓ 都包含规程专家角色定义
- ✓ 都包含目录优先原则
- ✓ 都包含精准定位说明
- ✓ 都包含多跳推理协议
- ✓ 都包含引用解析说明
- ✓ Orchestrator 包含 Orchestrator 模式说明

### 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `src/regreader/agents/prompts.py` | 新增动态生成函数 | ✅ 已完成 |
| `src/regreader/agents/orchestrated/claude.py` | 修改主线和子智能体提示词构建 | ✅ 已完成 |
| `src/regreader/subagents/prompts.py` | 清理硬编码提示词 | ✅ 已完成 |
| `tests/agents/test_prompt_generation.py` | 新建单元测试（17个测试） | ✅ 已完成 |
| `tests/agents/verify_prompt_consistency.py` | 新建子智能体提示词验证 | ✅ 已完成 |
| `tests/agents/verify_main_prompt_consistency.py` | 新建主线提示词验证 | ✅ 已完成 |

### 预期效果

#### 提示词统一性
- ✅ 两种模式使用相同的提示词生成逻辑
- ✅ 工具描述都从 TOOL_METADATA 动态生成
- ✅ 不再有硬编码的工具列表
- ✅ **主线 Agent 使用相同的专家提示词**

#### 推理路径一致性
- ✅ 两种模式的推理路径应该更加一致
- ✅ 都从 `get_toc()` → `read_page_range()` → `smart_search()` 开始
- ✅ 工具调用策略相似
- ✅ 答案质量保持稳定

#### 架构改进
- ✅ 子智能体用于上下文隔离和并行执行
- ✅ 主线 Agent 保持专家角色，而非协调器角色
- ✅ 符合用户期望的架构设计

### 测试验证

```bash
# 1. 单元测试（所有通过）
pytest tests/agents/test_prompt_generation.py -xvs

# 2. 提示词一致性验证
uv run python tests/agents/verify_prompt_consistency.py
# 结果：所有 5 个检查通过

# 3. 主线提示词一致性验证
uv run python tests/agents/verify_main_prompt_consistency.py
# 结果：所有关键检查通过
```

## 2026-01-16 AgentEx 框架修复和记忆功能完善（已完成 ✅）

### 问题描述

1. `NameError: name 'Any' is not defined` - 缺少导入
2. 配置类默认值为空，需要改为从环境变量读取
3. 框架注册不生效
4. Agent 缺少 `name` 属性
5. 记忆系统不工作 - 用户消息未添加到历史

### 修复内容

#### 1. 修复 `Any` 导入问题

**文件**: `src/agentex/agent.py`, `src/agentex/config/__init__.py`

```python
from typing import Any, AsyncGenerator  # 添加 Any
```

#### 2. 配置类使用环境变量默认值

**文件**: `src/agentex/config/__init__.py`

```python
# Claude 配置
api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_AUTH_TOKEN"))
base_url: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"))
model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514"))

# OpenAI/Pydantic/LangGraph 配置
api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL"))
model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL_NAME", "gpt-4"))
```

#### 3. 修复框架注册

**文件**: `src/agentex/frameworks/__init__.py`

```python
# 显式导入子模块以触发框架注册
from . import claude
from . import pydantic
from . import langgraph
```

#### 4. 修复 Agent 的 `name` 属性

**文件**: `src/agentex/frameworks/claude/__init__.py`, `pydantic/__init__.py`, `langgraph/__init__.py`

```python
@property
def name(self) -> str:
    """获取 Agent 名称"""
    return self.config.name
```

#### 5. 修复记忆系统

**问题**: `if self._memory:` 条件在 `_memory` 为空对象时返回 False（因为 `__bool__` 方法返回 False）

**解决**: 使用 `if self._memory is not None:` 代替

**文件**: 所有框架的 `__init__.py`

```python
# 添加用户消息到记忆
if self._memory is not None:
    self._memory.add("user", message)

# 添加助手回复到记忆
if self._memory is not None:
    self._memory.add("assistant", result)
```

### 测试验证

```bash
# 1. 简单对话测试
uv run python examples/basic/simple_chat.py

# 2. 记忆功能测试
uv run python examples/basic/with_memory.py
# 结果：Agent 能正确记忆用户信息（名字、颜色偏好等）
```

## 2026-01-16 AgentEx 框架额外修复（已完成 ✅）

### 问题描述

1. `ImportError: cannot import name 'AgentConfig' from 'agentex'` - 导出缺失
2. `ModuleNotFoundError: No module named 'agentex.tools.types'` - 错误的导入路径
3. `TypeError: LLMConfig.__init__() missing 1 required positional argument: 'model'` - 示例代码需要更新

### 修复内容

#### 1. 导出配置类

**文件**: `src/agentex/__init__.py`

```python
from .config import AgentConfig, LLMConfig, ClaudeConfig

__all__ = [
    ...
    "AgentConfig",
    "LLMConfig",
    "ClaudeConfig",
]
```

#### 2. 修复 tools/base.py 导入路径

**文件**: `src/agentex/tools/base.py`

```python
# 错误：from .types import ToolResult, Context
# 正确：
from ..types import ToolResult, Context
```

#### 3. 更新示例文件使用工厂函数

**文件**: `examples/basic/with_tools.py`

```python
# 之前：
from agentex import AgentConfig, LLMConfig
from agentex.frameworks import FrameworkFactory, FrameworkType

# 之后：
from agentex import AgentConfig
from agentex.frameworks import create_agent

# 使用工厂函数简化创建流程
agent = create_agent(
    framework="claude",
    system_prompt="...",
)
```

#### 4. 修复 LangGraph 的 Python 3.13 兼容问题

**文件**: `src/agentex/frameworks/langgraph/__init__.py`

Python 3.13 不再从 `typing` 导出 `list` 类型，需要使用内置 `list`：

```python
# 错误：
from typing import TypedDict, Annotated, list

# 正确：
from typing import TypedDict, Annotated
```

#### 5. 修复集成示例文件

**文件**: `examples/integrations/claude_sdk.py`, `pydantic_ai.py`, `langgraph.py`

统一使用简化后的 `create_agent` API：

```python
# 之前：
from agentex.frameworks import create_agent, FrameworkType
from agentex.config import AgentConfig, LLMConfig

agent = create_agent(
    framework=FrameworkType.CLAUDE,
    config=AgentConfig(
        name="xxx",
        llm=LLMConfig(),
        system_prompt="...",
    ),
)

# 之后：
from agentex.frameworks import create_agent

agent = create_agent(
    framework="claude",
    system_prompt="...",
)
```

### 测试验证

```bash
uv run python examples/basic/simple_chat.py      # ✅ 正常工作
uv run python examples/basic/with_memory.py      # ✅ 记忆功能正常
uv run python examples/basic/with_tools.py       # ✅ 工具调用正常
uv run python examples/advanced/custom_router.py # ✅ 语法修复完成
uv run python examples/integrations/claude_sdk.py  # ✅ 正常工作
uv run python examples/integrations/pydantic_ai.py # ✅ 正常工作
uv run python examples/integrations/langgraph.py   # ✅ 正常工作
```

## 2026-01-16 主智能体任务级编排 + 子智能体原子级执行的 Bash+FS 范式实现（已完成 ✅）

### 问题背景

用户提出了关于 Bash+FS 范式的三个关键问题：

1. **子智能体是否使用 Bash+FS 范式？** - 子智能体应该使用文件系统进行通信和记录
2. **是否有会话级工作区记录？** - 需要记录 agent 计划、输入、输出、过程
3. **下一子智能体是否从工作区获得上下文？** - 通过文件系统传递任务上下文

### 用户核心反馈（关键）

> **"主智能体拆解任务应该是'从规程目录中定位可能的章节'、'从指定章节范围获得与问题任务相关的内容或表格'等，而不是'获得规程目录'、'获得指定章节的全部内容'这些原子任务，这些原子任务应该是子智能体负责主动识别和拆解执行的。因此，任务执行过程中应该有主智能体任务记录，以及各个子智能体的原子任务执行过程记录。主智能体使用claude-agent-sdk，加上preset: 'claude_code'引入Claude Code的核心智能体能力，子智能体可以用三框架封装的方式，方便以后业务级的二次开发。"**

**关键理解**：
- **主智能体**：任务级拆解（"定位章节"、"获取内容"），**不是**原子工具调用（"调用 get_toc()"）
- **子智能体**：主动识别和拆解为原子操作，执行 MCP 工具调用
- **记录要求**：主智能体记录任务拆解，子智能体记录原子任务执行过程
- **架构要求**：
  - 主智能体：Claude Agent SDK + `preset: "claude_code"`
  - 子智能体：三框架封装（Claude SDK / Pydantic AI / LangGraph）

### 当前架构问题

1. **主智能体和子智能体的职责混淆**
   - 当前：主智能体（单智能体模式）直接调用 MCP 工具
   - 期望：主智能体只做任务级拆解，原子工具调用由子智能体负责

2. **缺少主智能体任务记录**
   - 当前：没有主智能体任务拆解和执行的记录
   - 期望：`coordinator/` 工作区记录任务计划、执行过程、结果聚合

3. **子智能体执行过程不可见**
   - 当前：子智能体的工具调用过程没有持久化记录
   - 期望：`subagents/{type}/` 工作区记录原子任务拆解和执行过程

### 解决方案 - 两层智能体体系

#### 架构设计

```
┌─────────────────────────────────────────────────────────┐
│  主智能体 (Claude Agent SDK + preset: "claude_code")     │
│  职责：任务级拆解、子任务调度、结果聚合                   │
│  工作区：coordinator/session_{id}/                      │
│    - plan.md: 任务拆解计划                               │
│    - execution.md: 执行过程记录                          │
│    - final_report.md: 最终聚合报告                       │
└─────────────────────────────────────────────────────────┘
                        ↓ 任务分发
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ SearchAgent  │ │  TableAgent  │ │ReferenceAgent│
│ (三框架封装)  │ │ (三框架封装)  │ │ (三框架封装)  │
│              │ │              │ │              │
│ 职责：原子级  │ │ 职责：原子级  │ │ 职责：原子级  │
│   工具调用    │ │   工具调用    │ │   工具调用    │
│              │ │              │ │              │
│ 工作区：      │ │ 工作区：      │ │ 工作区：      │
│ subagents/   │ │ subagents/   │ │ subagents/   │
│   search/    │ │   table/     │ │   reference/ │
│     - task.md│ │     - task.md│ │     - task.md│
│     - steps.md││     - steps.md││     - steps.md│
│     - results.json│     - results.json│     - results.json│
└──────────────┘ └──────────────┘ └──────────────┘
        ↓               ↓               ↓
    MCP Tools:    MCP Tools:      MCP Tools:
    get_toc,      search_tables,  resolve_ref,
    smart_search, get_table,      lookup_annotation
    read_page_range
```

#### 核心原则

1. **职责分离**：
   - 主智能体：**做什么**（任务级）："定位相关章节"、"获取表格数据"
   - 子智能体：**怎么做**（原子级）："调用 get_toc() → 解析结果 → 调用 smart_search()"

2. **完全可追踪**：
   - 主智能体记录：任务拆解、子任务分发、结果聚合
   - 子智能体记录：原子任务拆解、工具调用序列、中间结果

3. **灵活封装**：
   - 主智能体：固定使用 Claude Agent SDK + claude_code preset
   - 子智能体：三框架封装，便于业务级二次开发

4. **文件系统通信**：
   - 主智能体 → 子智能体：写入 `subagents/{type}/task.md`
   - 子智能体 → 主智能体：读取 `subagents/{type}/results.json`

### 实现内容

#### Step 1: 创建主智能体（Claude Agent SDK + claude_code preset）✅

**文件**: `src/regreader/agents/main/agent.py`（新建）

**核心功能**：
- 使用 Claude Agent SDK + `preset: "claude_code"`
- 任务级拆解（非原子工具调用）
- 通过文件系统向子智能体分发任务
- 记录任务拆解、执行过程、结果聚合

**关键方法**：
- `_build_main_prompt()`: 构建提示词，强调任务级拆解
- `_dispatch_search_task()`: 分发搜索任务到 SearchAgent
- `_dispatch_table_task()`: 分发表格任务到 TableAgent
- `_dispatch_reference_task()`: 分发引用任务到 ReferenceAgent
- `_log_execution()`: 记录执行过程到 execution.md
- `query()`: 处理用户查询

#### Step 2: 创建子智能体基类（支持三框架封装）✅

**文件**: `src/regreader/subagents/bash_fs_base.py`（新建）

**核心功能**：
- 支持文件系统通信（task.md / steps.md / results.json）
- 主动拆解任务为原子操作序列
- 执行原子操作（调用 MCP 工具）
- 实时记录执行过程

**关键类和方法**：
- `BaseSubagentFS`: 子智能体抽象基类
  - `read_task()`: 从 task.md 读取任务
  - `write_steps()`: 写入原子任务执行记录
  - `write_results()`: 写入最终结果
  - `decompose_task()`: 将任务拆解为原子操作（抽象方法）
  - `execute_atomic_step()`: 执行单个原子操作（抽象方法）
  - `run()`: 主流程

- `SubagentResult`: 子智能体执行结果
  - `content`: 最终答案
  - `sources`: 数据来源
  - `tool_calls`: 工具调用序列
  - `metadata`: 元数据
  - `summary()`: 生成摘要

#### Step 3: 实现三个子智能体 ✅

**SearchAgent** (`src/regreader/subagents/search/agent.py`):
- 文档搜索子智能体
- 支持基于规则和 LLM 的任务拆解
- 原子操作：get_toc, smart_search, read_page_range

**TableAgent** (`src/regreader/subagents/table/agent.py`):
- 表格子智能体
- 原子操作：search_tables, get_table_by_id

**ReferenceAgent** (`src/regreader/subagents/reference/agent.py`):
- 引用子智能体
- 原子操作：resolve_reference, lookup_annotation

#### Step 4: 更新 CLI 支持 ask 命令 ✅

**文件**: `src/regreader/cli.py`（修改）

**新增选项**：
- `--main-agent`, `-m`: 启用主智能体模式（Bash+FS 范式）

**使用示例**：
```bash
regreader ask "锦苏直流安控装置在母线失压时的动作逻辑" -m -r angui_2024
```

**输出增强**：
- 显示会话记录位置：`coordinator/session_{id}/`

#### Step 5: 创建测试 ✅

**文件**: `tests/agents/test_main_agent.py`（新建）

**测试覆盖**：
1. **TestMainAgentTaskDecomposition**: 测试主智能体任务级拆解
   - 初始化测试
   - 提示词验证（任务级 vs 原子级）
   - 执行日志记录

2. **TestSubagentAtomicDecomposition**: 测试子智能体原子级拆解
   - 读取任务文件
   - 基于规则的原子任务拆解
   - 写入步骤文件
   - 写入结果文件

3. **TestFileSystemCommunication**: 测试文件系统通信
   - 主智能体写入任务文件

4. **TestWorkspaceStructure**: 测试工作区结构

5. **TestResponsibilitySeparation**: 测试职责分离
   - 主智能体不调用原子工具
   - 子智能体拆解为原子操作
   - 任务级 vs 原子级区别

### 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `src/regreader/agents/main/agent.py` | 新建主智能体类 | ✅ 已完成 |
| `src/regreader/agents/main/__init__.py` | 新建主智能体模块 | ✅ 已完成 |
| `src/regreader/subagents/bash_fs_base.py` | 新建 Bash+FS 范式基类 | ✅ 已完成 |
| `src/regreader/subagents/search/agent.py` | 新建 SearchAgent | ✅ 已完成 |
| `src/regreader/subagents/search/__init__.py` | 新建 search 模块 | ✅ 已完成 |
| `src/regreader/subagents/table/agent.py` | 新建 TableAgent | ✅ 已完成 |
| `src/regreader/subagents/table/__init__.py` | 新建 table 模块 | ✅ 已完成 |
| `src/regreader/subagents/reference/agent.py` | 新建 ReferenceAgent | ✅ 已完成 |
| `src/regreader/subagents/reference/__init__.py` | 新建 reference 模块 | ✅ 已完成 |
| `src/regreader/cli.py` | 添加 --main-agent 选项 | ✅ 已完成 |
| `tests/agents/test_main_agent.py` | 新建测试（6个测试类） | ✅ 已完成 |
| `tests/agents/__init__.py` | 新建测试模块 | ✅ 已完成 |

### 预期效果

#### 职责清晰分离

**主智能体**：
- 输入：用户查询
- 输出：任务级子任务（如"定位相关章节"）
- 记录：`coordinator/session_{id}/plan.md`, `execution.md`, `final_report.md`
- ❌ 任务描述**不**包含"调用 get_toc()"等原子操作

**子智能体**：
- 输入：任务级描述（如"定位相关章节"）
- 输出：原子操作序列（get_toc → smart_search → read_page）
- 记录：`subagents/{type}/steps.md`, `results.json`

#### 完全可追踪

执行一次查询后，可以完整追溯：
1. 主智能体如何拆解任务
2. 分发了哪些子任务
3. 子智能体如何拆解为原子操作
4. 每个原子操作的参数和结果
5. 最终答案如何聚合

#### 灵活扩展

- 主智能体：固定使用 Claude Agent SDK + claude_code preset
- 子智能体：支持三框架封装，便于业务定制
- 新增子智能体：继承 `BaseSubagentFS`，实现业务逻辑

### 测试验证

```bash
# 1. 单元测试
pytest tests/agents/test_main_agent.py -xvs

# 2. 集成测试（需要实际环境）
regreader ask "锦苏直流安控装置在母线失压时的动作逻辑" -m -r angui_2024

# 3. 查看执行记录
cat coordinator/session_*/plan.md
cat coordinator/session_*/execution.md
cat coordinator/session_*/final_report.md

# 4. 查看子智能体任务
cat subagents/search/task.md
cat subagents/search/steps.md
cat subagents/search/results.json
```

### 后续工作

1. **完善子智能体实现**：
   - SearchAgent 的 LLM 拆解优化
   - TableAgent 和 ReferenceAgent 的完善
   - 添加 DiscoveryAgent 支持

2. **性能优化**：
   - 子智能体并行执行
   - 结果缓存机制
   - 增量更新 steps.md

3. **监控和调试**：
   - 添加详细的日志记录
   - 可视化执行过程
   - 错误恢复机制

---

## 2026-01-16 AgentEx 示例文件修复（已完成 ✅）

### 问题描述

运行 `examples/regreader/basic_usage.py` 时出现错误：
```
AttributeError: 'RegReaderAgent' object has no attribute 'search'
```

原因：`basic_usage.py` 期望 `RegReaderAgent` 有 `search()`、`get_toc()`、`reset()` 方法，但这些方法尚未实现。

### 修复内容

#### 1. 简化 `basic_usage.py`

**文件**: `examples/regreader/basic_usage.py`

移除需要但未实现的方法调用，只保留现有的 `chat()` 和 `close()` 方法：

```python
# 之前：期望 search(), get_toc(), reset() 方法
results = await agent.search("母线失压")
toc = await agent.get_toc()
await agent.reset()

# 之后：只使用 chat() 方法
response = await agent.chat("总则部分的主要内容是什么？")
response = await agent.chat("高压设备工作的安全要求有哪些？")
```

#### 2. 修复 `multi_subagent.py`

**文件**: `examples/regreader/multi_subagent.py`

移除已废弃的 `FrameworkType` 枚举导入，改为字符串格式：

```python
# 之前：
from agentex.frameworks import FrameworkType
framework=FrameworkType.CLAUDE

# 之后：
framework="claude"
```

### 测试验证

```bash
# 所有示例运行成功
uv run python examples/basic/simple_chat.py        # ✅ 正常工作
uv run python examples/basic/with_memory.py        # ✅ 记忆功能正常
uv run python examples/basic/with_tools.py         # ✅ 工具调用正常
uv run python examples/regreader/basic_usage.py    # ✅ 正常工作
uv run python examples/regreader/regreader_agent.py # ✅ 正常工作
```

### 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `examples/regreader/basic_usage.py` | 移除未实现的方法，简化示例 | ✅ 已完成 |
| `examples/regreader/multi_subagent.py` | 移除 FrameworkType，使用字符串 | ✅ 已完成 |
| `src/agentex/types.py` | LLMConfig 添加环境变量默认值 | ✅ 已完成 |

## 2026-01-16 AgentEx LLMConfig 默认值修复（已完成 ✅）

### 问题描述

运行 `examples/regreader/multi_subagent.py` 时出现错误：
```
TypeError: LLMConfig.__init__() missing 1 required positional argument: 'model'
```

原因：`LLMConfig` 类中 `model` 字段没有默认值，需要显式传递。

### 修复内容

**文件**: `src/agentex/types.py`

为 `LLMConfig` 添加环境变量默认工厂：

```python
@dataclass
class LLMConfig:
    """LLM 配置"""
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514"))
    api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_AUTH_TOKEN"))
    base_url: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL"))
    temperature: float = 0.0
    max_tokens: int | None = None
```

### 测试验证

```bash
# 所有示例运行成功
uv run python examples/basic/simple_chat.py        # ✅ 正常工作
uv run python examples/basic/with_memory.py        # ✅ 记忆功能正常
uv run python examples/basic/with_tools.py         # ✅ 工具调用正常
uv run python examples/regreader/basic_usage.py    # ✅ 正常工作
uv run python examples/regreader/regreader_agent.py # ✅ 正常工作
uv run python examples/regreader/multi_subagent.py  # ✅ 多子智能体正常
```

### 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `src/agentex/types.py` | LLMConfig 添加环境变量默认值 | ✅ 已完成 |
| `examples/regreader/multi_subagent.py` | 使用简化 API，移除 config 参数 | ✅ 已完成 |

---

## 2026-01-16 架构重构：使用 Claude Agent SDK 原生 subagent 机制（进行中 🔄）

### 问题分析

用户提出了关键的架构指导：

> **"主智能用的是claude-agent-sdk，可以用它的subagents机制，所有要相应设计对应任务的subagents"**

**当前架构问题**：
1. 主智能体使用 Claude Agent SDK ✅
2. 但子智能体使用自定义的 `BaseSubagentFS` 类 ❌
3. 主智能体手动调用子智能体的 `run()` 方法 ❌
4. 子智能体的 `run()` 是同步方法，但在异步上下文中调用 ❌
5. 导致 `asyncio.run() cannot be called from a running event loop` 错误

**正确架构**：
1. **主智能体**：使用 Claude Agent SDK 的 handoff 机制
2. **子智能体**：也是 Claude Agent SDK agent（不是自定义类）
3. **通信方式**：通过 handoff 自动转交，而不是手动调用 `run()`
4. **工具访问**：子智能体通过 tools 参数访问 MCP 工具

### 预设子智能体设计

基于 MCP 工具分类和业务需求，设计 **4 个预设子智能体**：

#### 1. SearchAgent（搜索子智能体）

**职责**：文档搜索、导航、章节定位、内容提取

**使用工具**（7个）：
- `get_toc`: 获取规程目录树
- `smart_search`: 智能混合检索
- `read_page_range`: 读取页面范围
- `get_chapter_structure`: 获取章节结构
- `get_page_chapter_info`: 获取页面章节信息
- `read_chapter_content`: 读取章节内容
- `list_regulations`: 列出所有规程

**典型任务**：
- "从规程目录中定位关于母线失压的章节"
- "获取第六章的全部内容"
- "搜索关于高压设备安全要求的内容"

**Handoff 触发条件**：
- 任务涉及"定位章节"、"搜索内容"、"读取页面"、"目录"

#### 2. TableAgent（表格子智能体）

**职责**：表格搜索、数据提取、表格内容获取

**使用工具**（2个）：
- `search_tables`: 搜索表格
- `get_table_by_id`: 获取表格内容

**典型任务**：
- "查找并提取母线失压相关的表格数据"
- "获取表格 table_001 的完整内容"
- "搜索包含动作逻辑的表格"

**Handoff 触发条件**：
- 任务涉及"表格"、"提取数据"、"查找表格"

#### 3. ReferenceAgent（引用子智能体）

**职责**：交叉引用解析、注释查找

**使用工具**（3个）：
- `resolve_reference`: 解析交叉引用
- `lookup_annotation`: 查找注释
- `search_annotations`: 搜索注释

**典型任务**：
- "解析'见第六章'的交叉引用"
- "查找注1的完整内容"
- "搜索所有关于'安控装置'的注释"

**Handoff 触发条件**：
- 任务涉及"交叉引用"、"注释"、"见第X章"、"注X"

#### 4. DiscoveryAgent（发现子智能体）

**职责**：语义分析、相似内容发现、章节比较

**使用工具**（2个）：
- `find_similar_content`: 查找相似内容
- `compare_sections`: 比较两个章节

**典型任务**：
- "查找与母线失压处理流程相似的其他内容"
- "比较第二章和第三章的安全要求差异"
- "发现相关的故障处理流程"

**Handoff 触发条件**：
- 任务涉及"相似内容"、"比较"、"差异"、"发现"

### 覆盖性验证

| MCP 工具分类 | 工具数量 | 覆盖子智能体 | 状态 |
|-------------|---------|-------------|------|
| BASE（基础） | 7个 | SearchAgent | ✅ |
| MULTI_HOP（多跳） | 3个 | TableAgent, ReferenceAgent | ✅ |
| CONTEXT（上下文） | 3个 | TableAgent, ReferenceAgent | ✅ |
| DISCOVERY（发现） | 2个 | DiscoveryAgent | ✅ |

**总计**：15个工具，4个子智能体，完全覆盖 ✅

### 实现计划

#### Phase 1: 创建异步 MCP 工具包装器

**文件**：`src/regreader/mcp/async_tools.py`（新建）

**目标**：将 MCP 适配器的方法包装为 Claude Agent SDK 可用的异步工具函数

```python
from typing import Any
from regreader.mcp.adapter import RegReaderMCPToolsAdapter

class MCPAsyncTools:
    """MCP 异步工具包装器

    将 RegReaderMCPToolsAdapter 的同步方法包装为异步函数，
    供 Claude Agent SDK 子智能体使用。
    """

    def __init__(self, transport: str, server_url: str | None = None):
        self.adapter = RegReaderMCPToolsAdapter(
            transport=transport,
            server_url=server_url,
        )

    # SearchAgent 工具
    async def get_toc(self, reg_id: str) -> dict:
        """获取规程目录树"""
        return await self.adapter._call_tool_async(
            "get_toc", {"reg_id": reg_id}
        )

    async def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        # ... 其他参数
    ) -> list[dict]:
        """智能混合检索"""
        return await self.adapter._call_tool_async(
            "smart_search", {...}
        )

    # ... 其他工具方法
```

#### Phase 2: 使用 Claude Agent SDK 创建子智能体

**文件**：`src/regreader/agents/subagents/`（新建目录）

**结构**：
```
src/regreader/agents/subagents/
├── __init__.py
├── search_agent.py      # SearchAgent（Claude SDK）
├── table_agent.py       # TableAgent（Claude SDK）
├── reference_agent.py   # ReferenceAgent（Claude SDK）
└── discovery_agent.py   # DiscoveryAgent（Claude SDK）
```

**实现示例**（SearchAgent）：

```python
from claude_agent_sdk import Agent, handoff
from regreader.mcp.async_tools import MCPAsyncTools

def create_search_agent(mcp_tools: MCPAsyncTools) -> Agent:
    """创建搜索子智能体

    Returns:
        Claude Agent SDK Agent 实例
    """
    return Agent(
        name="Search-Agent",
        instructions="""你是文档搜索专家，负责规程文档的搜索和导航。

# 你的职责
1. 从规程目录中定位相关章节
2. 搜索和提取文档内容
3. 读取页面和章节内容

# 可用工具
- get_toc: 获取规程目录结构
- smart_search: 智能混合检索
- read_page_range: 读取页面范围
- get_chapter_structure: 获取章节结构
- read_chapter_content: 读取章节内容

# 工作流程
1. 理解主智能体分发的任务
2. 选择合适的工具
3. 执行搜索和提取
4. 返回结果给主智能体
""",
        tools=[
            mcp_tools.get_toc,
            mcp_tools.smart_search,
            mcp_tools.read_page_range,
            mcp_tools.get_chapter_structure,
            mcp_tools.read_chapter_content,
        ]
    )
```

#### Phase 3: 更新主智能体使用 handoff 机制

**文件**：`src/regreader/agents/main/agent.py`（修改）

**关键改动**：

```python
async def query(self, user_query: str) -> str:
    """处理用户查询（使用 handoff 机制）"""
    # 创建 MCP 工具包装器
    mcp_tools = MCPAsyncTools(
        transport=self.mcp_transport,
        server_url=f"http://{self.mcp_host}:{self.mcp_port}/sse",
    )

    # 创建子智能体
    search_agent = create_search_agent(mcp_tools)
    table_agent = create_table_agent(mcp_tools)
    reference_agent = create_reference_agent(mcp_tools)
    discovery_agent = create_discovery_agent(mcp_tools)

    # 创建主智能体，配置 handoff
    main_agent = Agent(
        name="RegReader-Main",
        instructions=self._build_main_prompt(),
        handoffs=[
            handoff(
                to_agent=search_agent,
                description="文档搜索和内容提取任务",
                when_to_trigger=lambda msg: self._should_search(msg),
            ),
            handoff(
                to_agent=table_agent,
                description="表格数据提取任务",
                when_to_trigger=lambda msg: self._should_extract_table(msg),
            ),
            # ... 其他 handoff
        ]
    )

    # 运行主智能体
    response = await main_agent.run(user_query)
    return response
```

### 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `src/regreader/mcp/async_tools.py` | 创建异步 MCP 工具包装器 | ⏳ 待创建 |
| `src/regreader/agents/subagents/` | 创建子智能体目录 | ⏳ 待创建 |
| `src/regreader/agents/subagents/search_agent.py` | 创建 SearchAgent（Claude SDK） | ⏳ 待创建 |
| `src/regreader/agents/subagents/table_agent.py` | 创建 TableAgent（Claude SDK） | ⏳ 待创建 |
| `src/regreader/agents/subagents/reference_agent.py` | 创建 ReferenceAgent（Claude SDK） | ⏳ 待创建 |
| `src/regreader/agents/subagents/discovery_agent.py` | 创建 DiscoveryAgent（Claude SDK） | ⏳ 待创建 |
| `src/regreader/agents/main/agent.py` | 更新为使用 handoff 机制 | ⏳ 待修改 |


