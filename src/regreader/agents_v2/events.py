"""事件适配器

在 agentex.Event 和 RegReader AgentEvent 之间进行转换。
"""

from __future__ import annotations

from typing import Any

from ..agentex.shared.events import Event, EventType
from ..agents.shared.events import (
    AgentEvent,
    AgentEventType,
    thinking_event,
    tool_start_event,
    tool_end_event,
    tool_error_event,
    iteration_event,
    response_complete_event,
)


class EventAdapter:
    """事件适配器

    在 agentex 事件系统和 RegReader 事件系统之间进行转换。
    """

    # agentex EventType -> RegReader AgentEventType 映射
    _TO_REGREADER_MAP: dict[EventType, AgentEventType] = {
        EventType.THINKING_START: AgentEventType.THINKING_START,
        EventType.THINKING_END: AgentEventType.THINKING_END,
        EventType.TOOL_CALL_START: AgentEventType.TOOL_CALL_START,
        EventType.TOOL_CALL_END: AgentEventType.TOOL_CALL_END,
        EventType.TOOL_CALL_ERROR: AgentEventType.TOOL_CALL_ERROR,
        EventType.TEXT_DELTA: AgentEventType.TEXT_DELTA,
        EventType.RESPONSE_COMPLETE: AgentEventType.RESPONSE_COMPLETE,
    }

    # RegReader AgentEventType -> agentex EventType 映射
    _TO_AGENTEX_MAP: dict[AgentEventType, EventType] = {
        AgentEventType.THINKING_START: EventType.THINKING_START,
        AgentEventType.THINKING_END: EventType.THINKING_END,
        AgentEventType.TOOL_CALL_START: EventType.TOOL_CALL_START,
        AgentEventType.TOOL_CALL_END: EventType.TOOL_CALL_END,
        AgentEventType.TOOL_CALL_ERROR: EventType.TOOL_CALL_ERROR,
        AgentEventType.TEXT_DELTA: EventType.TEXT_DELTA,
        AgentEventType.RESPONSE_COMPLETE: EventType.RESPONSE_COMPLETE,
    }

    @classmethod
    def to_regreader_event(cls, event: Event) -> AgentEvent:
        """将 agentex Event 转换为 RegReader AgentEvent

        Args:
            event: agentex 事件

        Returns:
            RegReader 事件
        """
        event_type = cls._TO_REGREADER_MAP.get(
            event.type, AgentEventType.THINKING_START
        )
        return AgentEvent(
            event_type=event_type,
            data=event.data or {},
        )

    @classmethod
    def to_agentex_event(cls, event: AgentEvent) -> Event:
        """将 RegReader AgentEvent 转换为 agentex Event

        Args:
            event: RegReader 事件

        Returns:
            agentex 事件
        """
        event_type = cls._TO_AGENTEX_MAP.get(
            event.event_type, EventType.THINKING_START
        )
        return Event(
            type=event_type,
            data=event.data,
        )

    @classmethod
    def create_thinking_event(cls, start: bool = True) -> AgentEvent:
        """创建思考事件

        Args:
            start: True 表示开始，False 表示结束

        Returns:
            RegReader 事件
        """
        return thinking_event(start=start)

    @classmethod
    def create_tool_start_event(
        cls, tool_name: str, tool_input: dict[str, Any]
    ) -> AgentEvent:
        """创建工具开始事件

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            RegReader 事件
        """
        return tool_start_event(tool_name, tool_input)

    @classmethod
    def create_tool_end_event(
        cls, tool_name: str, tool_output: Any, duration_ms: float = 0.0
    ) -> AgentEvent:
        """创建工具结束事件

        Args:
            tool_name: 工具名称
            tool_output: 工具输出
            duration_ms: 执行时间（毫秒）

        Returns:
            RegReader 事件
        """
        return tool_end_event(tool_name, tool_output, duration_ms)

    @classmethod
    def create_tool_error_event(
        cls, tool_name: str, error: str
    ) -> AgentEvent:
        """创建工具错误事件

        Args:
            tool_name: 工具名称
            error: 错误信息

        Returns:
            RegReader 事件
        """
        return tool_error_event(tool_name, error)

    @classmethod
    def create_iteration_event(cls, iteration: int) -> AgentEvent:
        """创建迭代事件

        Args:
            iteration: 迭代次数

        Returns:
            RegReader 事件
        """
        return iteration_event(iteration)

    @classmethod
    def create_response_complete_event(
        cls, content: str, sources: list[str]
    ) -> AgentEvent:
        """创建响应完成事件

        Args:
            content: 响应内容
            sources: 来源列表

        Returns:
            RegReader 事件
        """
        return response_complete_event(content, sources)
