"""Agent 共享组件

提供所有 Agent 实现共享的基础设施：
- callbacks: 状态回调系统
- events: 事件定义和工厂函数
- display: Rich-based 状态显示
- memory: 对话历史和 TOC 缓存
- result_parser: 结果解析工具
- mcp_connection: MCP 连接管理
- mcp_config: MCP 配置
- llm_timing: LLM API 计时
- otel_hooks: OpenTelemetry 钩子
"""

from .callbacks import (
    CompositeCallback,
    LoggingCallback,
    NullCallback,
    StatusCallback,
)
from .clean_display import CleanAgentStatusDisplay, DisplayMode
from .display import AgentStatusDisplay
from .enhanced_display import EnhancedAgentStatusDisplay
from .events import (
    AgentEvent,
    AgentEventType,
    response_complete_event,
    text_delta_event,
    thinking_event,
    tool_end_event,
    tool_start_event,
)
from .mcp_connection import (
    MCPConnectionConfig,
    get_mcp_manager,
)
from .memory import AgentMemory, ContentChunk
from .result_parser import ToolResultSummary, parse_tool_result

__all__ = [
    # Callbacks
    "StatusCallback",
    "NullCallback",
    "CompositeCallback",
    "LoggingCallback",
    # Events
    "AgentEvent",
    "AgentEventType",
    "thinking_event",
    "text_delta_event",
    "tool_start_event",
    "tool_end_event",
    "response_complete_event",
    # Display
    "AgentStatusDisplay",
    "EnhancedAgentStatusDisplay",
    "CleanAgentStatusDisplay",
    "DisplayMode",
    # Memory
    "AgentMemory",
    "ContentChunk",
    # Result Parser
    "ToolResultSummary",
    "parse_tool_result",
    # MCP Connection
    "MCPConnectionConfig",
    "get_mcp_manager",
]
