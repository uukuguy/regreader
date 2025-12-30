"""Agent 实现模块

提供三种框架的 GridCode Agent 实现：
- ClaudeAgent: 基于 Claude Agent SDK
- PydanticAIAgent: 基于 Pydantic AI
- LangGraphAgent: 基于 LangGraph

统一 MCP 连接管理：
- MCPConnectionConfig: MCP 连接配置
- MCPConnectionManager: MCP 连接管理器（单例）
- configure_mcp: 全局配置函数
"""

from .base import AgentResponse, BaseGridCodeAgent
from .claude_agent import ClaudeAgent
from .hooks import AUDIT_HOOKS, post_tool_audit_hook, pre_tool_audit_hook, source_extraction_hook
from .langgraph_agent import LangGraphAgent
from .mcp_connection import MCPConnectionConfig, MCPConnectionManager, configure_mcp, get_mcp_manager
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
    # MCP Connection
    "MCPConnectionConfig",
    "MCPConnectionManager",
    "configure_mcp",
    "get_mcp_manager",
    # Session
    "SessionManager",
    "SessionState",
    # Hooks
    "AUDIT_HOOKS",
    "pre_tool_audit_hook",
    "post_tool_audit_hook",
    "source_extraction_hook",
]
