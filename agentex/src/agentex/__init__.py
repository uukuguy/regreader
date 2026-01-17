"""AgentEx - 通用多框架智能体编排库

提供统一的 Agent 接口，支持 Claude SDK、Pydantic AI、LangGraph 三种框架。
"""

from .types import AgentResponse, ToolResult, AgentEvent, Context
from .exceptions import AgentExError, AgentError, ToolError
from .config import AgentConfig, LLMConfig, ClaudeConfig
from .tools import Tool, FunctionTool, ToolRegistry

__version__ = "0.1.0"
__all__ = [
    "AgentResponse",
    "ToolResult",
    "AgentEvent",
    "Context",
    "AgentExError",
    "AgentError",
    "ToolError",
    "AgentConfig",
    "LLMConfig",
    "ClaudeConfig",
    "Tool",
    "FunctionTool",
    "ToolRegistry",
]
