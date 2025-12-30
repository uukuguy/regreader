"""Agent 实现模块

提供三种框架的 GridCode Agent 实现：
- ClaudeAgent: 基于 Claude Agent SDK
- PydanticAIAgent: 基于 Pydantic AI
- LangGraphAgent: 基于 LangGraph
"""

from .base import AgentResponse, BaseGridCodeAgent
from .claude_agent import ClaudeAgent
from .hooks import AUDIT_HOOKS, post_tool_audit_hook, pre_tool_audit_hook, source_extraction_hook
from .langgraph_agent import LangGraphAgent
from .pydantic_agent import PydanticAIAgent
from .session import SessionManager, SessionState

__all__ = [
    # Base
    "AgentResponse",
    "BaseGridCodeAgent",
    # Agents
    "ClaudeAgent",
    "LangGraphAgent",
    "PydanticAIAgent",
    # Session
    "SessionManager",
    "SessionState",
    # Hooks
    "AUDIT_HOOKS",
    "pre_tool_audit_hook",
    "post_tool_audit_hook",
    "source_extraction_hook",
]
