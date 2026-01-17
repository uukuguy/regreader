# AgentEx

AgentEx (Agent Executor) 是一个通用的多框架智能体编排库，为 Claude SDK、Pydantic AI 和 LangGraph 提供统一的接口抽象。

## 特性

- **统一接口**: 三种框架使用相同的 API，降低学习成本和切换成本
- **工具系统**: 可扩展的工具注册表，支持自定义工具和 MCP 适配
- **并行执行**: 内置并行执行器，支持顺序/并行两种模式
- **事件系统**: 完整的生命周期事件回调，支持监控和日志
- **记忆管理**: 对话历史自动管理，支持重置和持久化
- **可组合**: 易于创建子智能体系统，支持复杂工作流编排

## 安装

### 基础安装

```bash
pip install agentex
```

### 完整安装（包含所有框架）

```bash
pip install agentex[all]
```

### 单独框架安装

```bash
# 仅 Anthropic SDK
pip install agentex[claude]

# 仅 Pydantic AI
pip install agentex[pydantic-ai]

# 仅 LangGraph
pip install agentex[langgraph]
```

## 快速开始

### 基础对话

```python
import asyncio
from agentex.frameworks import create_agent, FrameworkType
from agentex.config import AgentConfig, LLMConfig

async def main():
    # 使用工厂函数创建 Agent
    agent = create_agent(
        framework=FrameworkType.CLAUDE,
        config=AgentConfig(
            name="my-agent",
            llm=LLMConfig(
                api_key="your-api-key",
                model="claude-sonnet-4-20250514",
            ),
            system_prompt="You are a helpful assistant.",
        ),
    )

    try:
        response = await agent.chat("Hello, please introduce yourself.")
        print(f"Agent: {response.content}")
    finally:
        await agent.close()

asyncio.run(main())
```

### 使用工具

```python
import asyncio
from agentex import Tool
from agentex.frameworks import create_agent, FrameworkType
from agentex.config import AgentConfig, LLMConfig

class CalculatorTool(Tool):
    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "Perform mathematical calculations"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression"}
            },
            "required": ["expression"]
        }

    async def execute(self, context, expression: str) -> str:
        # Safe evaluation with validation
        import re
        if not re.match(r'^[\d\+\-\*\/\(\)\.\s]+$', expression):
            return "Error: Invalid characters in expression"
        result = eval(expression)
        return f"Result: {result}"

async def main():
    agent = create_agent(
        framework=FrameworkType.CLAUDE,
        config=AgentConfig(
            name="calculator-agent",
            llm=LLMConfig(api_key="your-api-key"),
            tools=[CalculatorTool()],
            system_prompt="You are a math assistant.",
        ),
    )

    response = await agent.chat("Please calculate 25 * 4 + 10")
    print(f"Agent: {response.content}")

    await agent.close()

asyncio.run(main())
```

### 多轮对话与记忆

```python
import asyncio
from agentex.frameworks import create_agent, FrameworkType
from agentex.config import AgentConfig

async def main():
    agent = create_agent(
        framework=FrameworkType.CLAUDE,
        config=AgentConfig(
            name="memory-agent",
            llm=LLMConfig(api_key="your-api-key"),
            system_prompt="You are a helpful assistant with memory.",
            memory_enabled=True,
        ),
    )

    await agent.chat("My name is Zhang San.")
    response = await agent.chat("Do you know my name?")
    print(f"Agent: {response.content}")

    await agent.close()

asyncio.run(main())
```

### 并行执行

```python
import asyncio
from agentex.orchestration import ParallelExecutor

async def task_1():
    await asyncio.sleep(0.1)
    return "Result 1"

async def task_2():
    await asyncio.sleep(0.2)
    return "Result 2"

async def main():
    executor = ParallelExecutor(mode="parallel")

    results = await executor.execute([
        ("task_1", task_1),
        ("task_2", task_2),
    ])

    for result in results:
        if result.success:
            print(f"OK {result.task_id}: {result.result}")

asyncio.run(main())
```

## 文档结构

```
agentex/
├── src/agentex/
│   ├── agent.py          # BaseAgent abstract class
│   ├── types.py          # Core type definitions
│   ├── exceptions.py     # Exception definitions
│   ├── config/           # Configuration classes
│   ├── frameworks/       # Framework implementations
│   │   ├── claude/       # Claude SDK implementation
│   │   ├── pydantic/     # Pydantic AI implementation
│   │   └── langgraph/    # LangGraph implementation
│   ├── shared/           # Shared components
│   │   ├── callbacks.py  # Callback system
│   │   ├── events.py     # Event system
│   │   └── memory.py     # Memory system
│   ├── tools/            # Tool system
│   │   ├── base.py       # Tool base class
│   │   └── registry.py   # Tool registry
│   └── orchestration/    # Orchestration system
│       └── parallel.py   # Parallel executor
├── examples/
│   ├── basic/            # Basic examples
│   ├── advanced/         # Advanced examples
│   ├── integrations/     # Framework integration examples
│   └── regreader/        # RegReader-specific examples
└── tests/
```

## 示例

See `examples/` directory for complete examples:

- `examples/basic/simple_chat.py` - Simple chat
- `examples/basic/with_tools.py` - Tool usage
- `examples/basic/with_memory.py` - Memory system
- `examples/advanced/multi_subagent.py` - Multi-subagent
- `examples/advanced/parallel_execution.py` - Parallel execution
- `examples/advanced/custom_router.py` - Custom routing
- `examples/regreader/regreader_agent.py` - RegReaderAgent implementation

## API Reference

### Core Types

```python
@dataclass
class AgentResponse:
    content: str              # Response content
    sources: list[str]        # Source list
    tool_calls: list[dict]    # Tool call list
    metadata: dict            # Metadata
```

### BaseAgent

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

### Tool

```python
class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def parameters(self) -> dict: ...

    async def execute(self, context: Context, **kwargs: Any) -> ToolResult: ...
```

## Framework Support

| Framework | Pattern | Package Requirements |
|-----------|---------|---------------------|
| Anthropic SDK | Direct API | `anthropic>=0.25.0` |
| Pydantic AI | Delegation Pattern | `pydantic-ai>=1.0.0` |
| LangGraph | Subgraph Pattern | `langgraph>=0.2.0` |

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest -xvs

# Code formatting
black . && isort .

# Type checking
mypy src/
```

## License

MIT License
