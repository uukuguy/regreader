"""Direct Agents - 直接调用 MCP 工具的 Agent 实现

提供三种框架的直接 Agent 实现：
- ClaudeAgent: 基于 Claude Agent SDK
- PydanticAIAgent: 基于 Pydantic AI
- LangGraphAgent: 基于 LangGraph
"""

from __future__ import annotations

# 延迟导入，避免循环依赖
__all__ = [
    "ClaudeAgent",
    "PydanticAIAgent",
    "LangGraphAgent",
]


def __getattr__(name: str):
    """延迟导入 Agent 类"""
    if name == "ClaudeAgent":
        from .claude import ClaudeAgent
        return ClaudeAgent
    elif name == "PydanticAIAgent":
        from .pydantic import PydanticAIAgent
        return PydanticAIAgent
    elif name == "LangGraphAgent":
        from .langgraph import LangGraphAgent
        return LangGraphAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
