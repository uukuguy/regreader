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

兼容性 Shim：
- 设置环境变量 REGREADER_USE_AGENTEX=true 使用新的 agents_v2 实现
- 默认使用旧的 agents 实现
"""

import os

# 检查是否使用新的 agentex 实现
_USE_AGENTEX = os.environ.get("REGREADER_USE_AGENTEX", "").lower() in ("true", "1", "yes")

if _USE_AGENTEX:
    # 使用新的 agents_v2 实现（基于 agentex）
    from ..agents_v2 import (
        AgentResponse,
        RegReaderAgent as BaseRegReaderAgent,
        ClaudeAgent,
        PydanticAIAgent,
        LangGraphAgent,
        ClaudeOrchestrator,
        PydanticOrchestrator,
        LangGraphOrchestrator,
    )
else:
    # 使用旧的 agents 实现
    from .base import AgentResponse, BaseRegReaderAgent
    from .direct.claude import ClaudeAgent
    from .direct.langgraph import LangGraphAgent
    from .direct.pydantic import PydanticAIAgent
    from .orchestrated.langgraph import LangGraphOrchestrator
    from .orchestrated.pydantic import PydanticOrchestrator
    from .orchestrated.claude import ClaudeOrchestrator

# 以下模块始终从旧实现导入（共享基础设施）
from .shared.callbacks import CompositeCallback, LoggingCallback, NullCallback, StatusCallback
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
from .shared.mcp_connection import MCPConnectionConfig, MCPConnectionManager, configure_mcp, get_mcp_manager
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
