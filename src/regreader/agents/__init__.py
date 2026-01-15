"""Agent 实现模块

提供三种框架的 RegReader Agent 实现：
- ClaudeAgent: 基于 Claude Agent SDK
- PydanticAIAgent: 基于 Pydantic AI
- LangGraphAgent: 基于 LangGraph

Subagent 架构（Orchestrator 模式）：
- ClaudeOrchestrator: 基于 Claude Agent SDK Handoff Pattern 的协调器
- LangGraphOrchestrator: 基于 LangGraph Subgraph 的协调器
- PydanticOrchestrator: 基于 Pydantic AI Dependent Agents 的协调器

统一 MCP 连接管理：
- MCPConnectionConfig: MCP 连接配置
- MCPConnectionManager: MCP 连接管理器（单例）
- configure_mcp: 全局配置函数

状态回调系统：
- AgentEvent/AgentEventType: 事件系统
- StatusCallback: 回调协议
- AgentStatusDisplay: 状态显示组件
"""

from .base import AgentResponse, BaseRegReaderAgent
from .shared.callbacks import CompositeCallback, LoggingCallback, NullCallback, StatusCallback
from .direct.claude import ClaudeAgent
from .shared.display import AgentStatusDisplay, SimpleStatusDisplay
from .shared.events import (
    AgentEvent,
    AgentEventType,
    iteration_event,
    response_complete_event,
    thinking_event,
    tool_end_event,
    tool_error_event,
    tool_start_event,
)
from .hooks import (
    AUDIT_HOOKS,
    get_status_callback,
    post_tool_audit_hook,
    pre_tool_audit_hook,
    set_status_callback,
    source_extraction_hook,
)
from .direct.langgraph import LangGraphAgent
from .orchestrated.langgraph import LangGraphOrchestrator
from .orchestrated.pydantic import PydanticOrchestrator
from .orchestrated.claude import ClaudeOrchestrator
from .shared.mcp_connection import MCPConnectionConfig, MCPConnectionManager, configure_mcp, get_mcp_manager
from .direct.pydantic import PydanticAIAgent
from .session import SessionManager, SessionState

__all__ = [
    # Base
    "AgentResponse",
    "BaseRegReaderAgent",
    # Agents (Original)
    "ClaudeAgent",
    "LangGraphAgent",
    "PydanticAIAgent",
    # Orchestrators (Subagent Architecture)
    "ClaudeOrchestrator",
    "LangGraphOrchestrator",
    "PydanticOrchestrator",
    # MCP Connection
    "MCPConnectionConfig",
    "MCPConnectionManager",
    "configure_mcp",
    "get_mcp_manager",
    # Session
    "SessionManager",
    "SessionState",
    # Events
    "AgentEvent",
    "AgentEventType",
    "tool_start_event",
    "tool_end_event",
    "tool_error_event",
    "thinking_event",
    "iteration_event",
    "response_complete_event",
    # Callbacks
    "StatusCallback",
    "NullCallback",
    "CompositeCallback",
    "LoggingCallback",
    # Display
    "AgentStatusDisplay",
    "SimpleStatusDisplay",
    # Hooks
    "AUDIT_HOOKS",
    "pre_tool_audit_hook",
    "post_tool_audit_hook",
    "source_extraction_hook",
    "set_status_callback",
    "get_status_callback",
]
