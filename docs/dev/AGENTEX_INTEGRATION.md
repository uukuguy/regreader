# AgentEx 集成设计文档

## 概述

AgentEx 是一个通用多框架智能体编排库，已集成到 RegReader 项目中作为内部模块。该库提供统一的 Agent 接口，支持 Claude SDK、Pydantic AI、LangGraph 三种框架的无缝切换。

## 目录结构

```
src/regreader/agentex/
├── __init__.py              # 模块入口，导出所有公共 API
├── types.py                 # 通用类型定义 (AgentResponse, ToolResult, AgentEvent, LLMConfig)
├── exceptions.py            # 异常类定义
├── agent.py                 # BaseAgent 抽象基类和 AgentState
├── config/
│   └── __init__.py          # 配置类 (AgentConfig, ClaudeConfig, PydanticConfig, LangGraphConfig)
├── tools/
│   ├── __init__.py          # 工具模块导出
│   ├── base.py              # Tool 抽象基类和 FunctionTool
│   └── registry.py          # ToolRegistry 和 ToolExecutor
├── shared/
│   ├── __init__.py          # 共享模块导出
│   ├── callbacks.py         # 回调系统 (StatusCallback, NullCallback, LoggingCallback)
│   ├── events.py            # 事件系统 (EventType, Event)
│   └── memory.py            # 记忆系统 (AgentMemory, MemoryStore)
├── frameworks/
│   ├── __init__.py          # 框架模块导出
│   ├── base.py              # FrameworkFactory 和 FrameworkType
│   ├── claude/
│   │   └── __init__.py      # ClaudeAgent 实现
│   ├── pydantic/
│   │   └── __init__.py      # PydanticAgent 实现
│   └── langgraph/
│       └── __init__.py      # LangGraphAgent 实现
├── orchestration/
│   ├── __init__.py          # 编排模块导出
│   └── parallel.py          # ParallelExecutor 和 TaskPool
└── mcp_adapter.py           # MCP 工具适配器
```

## 核心组件

### 1. 类型系统 (types.py)

```python
@dataclass
class AgentResponse:
    content: str              # 回答内容
    sources: list[str]        # 来源引用
    tool_calls: list[dict]    # 工具调用记录
    metadata: dict            # 元数据

@dataclass
class ToolResult:
    name: str                 # 工具名称
    output: Any               # 输出结果
    success: bool             # 是否成功
    error: str | None         # 错误信息

@dataclass
class AgentEvent:
    event_type: str           # 事件类型
    data: dict                # 事件数据
    timestamp: float          # 时间戳

@dataclass
class LLMConfig:
    model: str                # 模型名称
    api_key: str | None       # API Key
    base_url: str | None      # 基础 URL
    temperature: float        # 温度
    max_tokens: int | None    # 最大 token 数
```

### 2. Agent 抽象基类 (agent.py)

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def chat(self, message: str, context: Context | None = None) -> AgentResponse: ...

    @abstractmethod
    async def stream(self, message: str, context: Context | None = None) -> AsyncGenerator[AgentEvent, None]: ...

    @abstractmethod
    async def reset(self): ...

    @abstractmethod
    async def close(self): ...
```

### 3. 框架工厂 (frameworks/base.py)

```python
class FrameworkType(str, Enum):
    CLAUDE = "claude"
    PYDANTIC = "pydantic"
    LANGGRAPH = "langgraph"

class FrameworkFactory:
    @classmethod
    def register(cls, framework_type: FrameworkType): ...

    @classmethod
    def create(cls, framework_type: FrameworkType, config: AgentConfig, **kwargs) -> BaseAgent: ...

    @classmethod
    def is_available(cls, framework_type: FrameworkType) -> bool: ...

    @classmethod
    def list_available(cls) -> list[FrameworkType]: ...
```

### 4. 工具系统 (tools/)

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def parameters(self) -> dict: ...

    async def execute(self, context: Context, **kwargs) -> ToolResult: ...

class FunctionTool(Tool):
    """基于函数的工具，简化工具创建"""
    def __init__(self, name: str, description: str, func: callable, parameters: dict | None = None): ...

class ToolRegistry:
    """工具注册表，管理工具的注册和查找"""
    def register(self, tool: Tool) -> "ToolRegistry": ...
    def get(self, name: str) -> Tool | None: ...
    def generate_schema(self) -> list[dict]: ...

class ToolExecutor:
    """工具执行器，协调工具的执行"""
    async def execute(self, tool_name: str, context: dict, **kwargs) -> Any: ...
```

### 5. MCP 适配器 (mcp_adapter.py)

```python
class MCPToolAdapter(Tool):
    """将 MCP Server 工具包装为 AgentEx Tool"""
    def __init__(self, tool_name: str, tool_description: str, tool_parameters: dict, mcp_client: Any): ...

class MCPToolRegistry:
    """从 MCP Server 自动发现并注册工具"""
    async def initialize(self) -> "MCPToolRegistry": ...
    def get_tool(self, name: str) -> Tool | None: ...

async def create_mcp_tool_registry(mcp_client: Any) -> MCPToolRegistry: ...
```

### 6. 并行执行器 (orchestration/parallel.py)

```python
@dataclass
class ExecutionResult:
    task_id: str
    success: bool
    result: Any
    error: str | None
    duration_ms: float

class ParallelExecutor:
    """支持顺序/并行两种模式的任务执行器"""
    def __init__(self, mode: str = "parallel", fail_strategy: str = "continue"): ...
    async def execute(self, tasks: list[tuple[str, Callable]]) -> list[ExecutionResult]: ...

class TaskPool:
    """带并发限制的任务池"""
    def __init__(self, max_concurrent: int = 10): ...
    async def submit(self, coro: Awaitable) -> Any: ...
    async def map(self, func: Callable, items: list) -> list: ...
```

## 使用示例

### 基本用法

```python
from regreader.agentex import create_agent, FrameworkType

# 使用便捷函数创建 Agent
agent = create_agent(
    framework="claude",
    system_prompt="You are a helpful assistant."
)

# 发送消息
response = await agent.chat("Hello!")
print(response.content)

# 关闭连接
await agent.close()
```

### 使用工厂模式

```python
from regreader.agentex import FrameworkFactory, FrameworkType, ClaudeConfig

# 创建配置
config = ClaudeConfig(
    name="my-agent",
    model="claude-sonnet-4-20250514",
    system_prompt="You are a regulation expert."
)

# 使用工厂创建 Agent
agent = FrameworkFactory.create(FrameworkType.CLAUDE, config)

# 使用 Agent
response = await agent.chat("What is the safety regulation?")
```

### 使用工具系统

```python
from regreader.agentex import FunctionTool, ToolRegistry, ToolExecutor

# 定义工具函数
async def search_docs(context, query: str = "", **kwargs):
    return f"Search results for: {query}"

# 创建工具
tool = FunctionTool(
    name="search_docs",
    description="Search documents",
    func=search_docs,
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        }
    }
)

# 注册和执行
registry = ToolRegistry()
registry.register(tool)

executor = ToolExecutor(registry)
result = await executor.execute("search_docs", {}, query="safety")
```

### 使用 MCP 适配器

```python
from regreader.agentex import create_mcp_tool_registry

# 假设已有 MCP 客户端
mcp_client = ...

# 创建 MCP 工具注册表
mcp_registry = await create_mcp_tool_registry(mcp_client)

# 获取工具 schema（供 LLM 使用）
schema = mcp_registry.generate_schema()

# 获取特定工具
tool = mcp_registry.get_tool("smart_search")
```

### 并行执行

```python
from regreader.agentex import ParallelExecutor, TaskPool

# 使用 ParallelExecutor
executor = ParallelExecutor(mode="parallel", fail_strategy="continue")

async def task1():
    return "result1"

async def task2():
    return "result2"

results = await executor.execute([
    ("t1", task1),
    ("t2", task2),
])

# 使用 TaskPool
pool = TaskPool(max_concurrent=5)

async def process(item):
    return item * 2

results = await pool.map(process, [1, 2, 3, 4, 5])
```

## 与 RegReader 集成

AgentEx 作为 RegReader 的底层 Agent 框架，提供以下集成点：

1. **MCP 工具集成**: 通过 `MCPToolAdapter` 将 RegReader 的 MCP 工具暴露给 Agent
2. **框架切换**: 支持在 Claude SDK、Pydantic AI、LangGraph 之间无缝切换
3. **统一接口**: 所有框架实现共享相同的 `BaseAgent` 接口
4. **并行执行**: 支持多子智能体的并行调度

## 测试

测试文件位于 `tests/agentex/test_agentex.py`，覆盖以下模块：

- 类型系统 (TestTypes)
- Agent 状态 (TestAgentState)
- 配置类 (TestAgentConfig)
- 工具系统 (TestToolSystem)
- 记忆系统 (TestMemory)
- 事件系统 (TestEvents)
- 回调系统 (TestCallbacks)
- 框架工厂 (TestFrameworkFactory)
- 并行执行器 (TestParallelExecutor)
- 任务池 (TestTaskPool)
- MCP 适配器 (TestMCPAdapter)

运行测试：

```bash
PYTHONPATH=src pytest tests/agentex/test_agentex.py -v
```

## 注意事项

1. **Python 版本兼容性**: 代码使用 `from __future__ import annotations` 以支持 Python 3.9+
2. **框架依赖**: 各框架实现使用延迟导入，仅在实际使用时才需要安装对应依赖
3. **配置继承**: 子配置类 (ClaudeConfig 等) 通过 `__post_init__` 自动构建 LLMConfig
