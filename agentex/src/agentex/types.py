"""通用类型定义"""

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResponse:
    """统一的 Agent 响应格式"""
    content: str
    """回答内容"""
    sources: list[str] = field(default_factory=list)
    """来源引用列表"""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """工具调用记录"""
    metadata: dict[str, Any] = field(default_factory=dict)
    """元数据"""


@dataclass
class ToolResult:
    """工具执行结果"""
    name: str
    """工具名称"""
    output: Any = None
    """工具输出"""
    success: bool = True
    """是否成功"""
    error: str | None = None
    """错误信息"""
    duration_ms: float | None = None
    """执行耗时（毫秒）"""
    source: str | None = None
    """来源标识"""


@dataclass
class AgentEvent:
    """Agent 事件"""
    event_type: str
    """事件类型"""
    data: dict[str, Any] = field(default_factory=dict)
    """事件数据"""
    timestamp: float = field(default_factory=lambda: __import__('time').time())
    """时间戳"""


# 类型别名
Context = dict[str, Any]
"""Agent 上下文"""
Message = dict[str, Any]
"""消息"""
Messages = list[Message]
"""消息列表"""


@dataclass
class LLMConfig:
    """LLM 配置"""
    model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL_NAME", "claude-sonnet-4-20250514"))
    api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_AUTH_TOKEN"))
    base_url: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_BASE_URL"))
    temperature: float = 0.0
    max_tokens: int | None = None


@dataclass
class ToolConfig:
    """工具配置"""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
