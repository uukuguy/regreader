"""事件系统

定义 Agent 运行时的事件类型和工厂函数。
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    """标准事件类型"""
    THINKING_START = auto()
    THINKING_END = auto()
    TOOL_CALL_START = auto()
    TOOL_CALL_END = auto()
    TOOL_CALL_ERROR = auto()
    TEXT_DELTA = auto()
    THINKING_DELTA = auto()
    RESPONSE_COMPLETE = auto()
    ERROR = auto()
    ITERATION_START = auto()
    ITERATION_END = auto()


@dataclass
class Event:
    """事件数据"""
    type: EventType
    data: dict[str, Any] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_agent_event(self) -> "types.AgentEvent":
        """转换为通用 AgentEvent"""
        from .types import AgentEvent
        return AgentEvent(
            event_type=self.type.name,
            data=self.data or {},
            timestamp=self.timestamp.timestamp()
        )


# 事件工厂函数
def thinking_event(start: bool) -> Event:
    """思考事件"""
    return Event(
        type=EventType.THINKING_START if start else EventType.THINKING_END
    )


def tool_start_event(name: str, input_: dict) -> Event:
    """工具调用开始事件"""
    return Event(
        type=EventType.TOOL_CALL_START,
        data={"tool": name, "input": input_}
    )


def tool_end_event(name: str, result: Any) -> Event:
    """工具调用结束事件"""
    return Event(
        type=EventType.TOOL_CALL_END,
        data={"tool": name, "result": result}
    )


def tool_error_event(name: str, error: str) -> Event:
    """工具调用错误事件"""
    return Event(
        type=EventType.TOOL_CALL_ERROR,
        data={"tool": name, "error": error}
    )


def text_delta_event(text: str) -> Event:
    """文本增量事件（流式输出）"""
    return Event(
        type=EventType.TEXT_DELTA,
        data={"text": text}
    )


def thinking_delta_event(text: str) -> Event:
    """思考增量事件（模型内部推理）"""
    return Event(
        type=EventType.THINKING_DELTA,
        data={"delta": text}
    )


def response_complete_event(content: str) -> Event:
    """响应完成事件"""
    return Event(
        type=EventType.RESPONSE_COMPLETE,
        data={"content": content}
    )


def error_event(error: str) -> Event:
    """错误事件"""
    return Event(
        type=EventType.ERROR,
        data={"error": error}
    )
