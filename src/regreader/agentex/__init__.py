"""AgentEx - 通用多框架智能体编排库

提供统一的 Agent 接口，支持 Claude SDK、Pydantic AI、LangGraph 三种框架。

Usage:
    from regreader.agentex import create_agent, FrameworkType

    # 创建 Claude Agent
    agent = create_agent("claude", system_prompt="You are a helpful assistant.")

    # 或使用工厂
    from regreader.agentex import FrameworkFactory, ClaudeConfig
    config = ClaudeConfig(name="my-agent", system_prompt="...")
    agent = FrameworkFactory.create(FrameworkType.CLAUDE, config)

    # 使用 Agent
    response = await agent.chat("Hello!")
    print(response.content)
"""

from .types import AgentResponse, ToolResult, AgentEvent, Context, LLMConfig, ToolConfig
from .exceptions import (
    AgentExError,
    AgentError,
    ToolError,
    ConfigurationError,
    ValidationError,
    FrameworkNotFoundError,
)
from .agent import BaseAgent, AgentState
from .config import AgentConfig, ClaudeConfig, PydanticConfig, LangGraphConfig
from .tools import Tool, FunctionTool, ToolRegistry, ToolExecutor, ToolResultParser
from .shared import (
    StatusCallback,
    NullCallback,
    LoggingCallback,
    CompositeCallback,
    CallbackAdapter,
    EventType,
    Event,
    AgentMemory,
    MemoryStore,
    MemoryItem,
)
from .frameworks import FrameworkType, FrameworkFactory, create_agent
from .orchestration import ParallelExecutor, TaskPool, ExecutionResult
from .mcp_adapter import MCPToolAdapter, MCPToolRegistry, create_mcp_tool_registry

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Types
    "AgentResponse",
    "ToolResult",
    "AgentEvent",
    "Context",
    "LLMConfig",
    "ToolConfig",
    # Exceptions
    "AgentExError",
    "AgentError",
    "ToolError",
    "ConfigurationError",
    "ValidationError",
    "FrameworkNotFoundError",
    # Agent
    "BaseAgent",
    "AgentState",
    # Config
    "AgentConfig",
    "ClaudeConfig",
    "PydanticConfig",
    "LangGraphConfig",
    # Tools
    "Tool",
    "FunctionTool",
    "ToolRegistry",
    "ToolExecutor",
    "ToolResultParser",
    # Shared
    "StatusCallback",
    "NullCallback",
    "LoggingCallback",
    "CompositeCallback",
    "CallbackAdapter",
    "EventType",
    "Event",
    "AgentMemory",
    "MemoryStore",
    "MemoryItem",
    # Frameworks
    "FrameworkType",
    "FrameworkFactory",
    "create_agent",
    # Orchestration
    "ParallelExecutor",
    "TaskPool",
    "ExecutionResult",
    # MCP Adapter
    "MCPToolAdapter",
    "MCPToolRegistry",
    "create_mcp_tool_registry",
]
