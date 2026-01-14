"""Agent 回调系统

定义状态回调协议和基础实现，用于 Agent 执行过程中的状态通知。
"""

from typing import Any, Protocol, runtime_checkable

from loguru import logger

from regreader.agents.events import AgentEvent, AgentEventType


@runtime_checkable
class StatusCallback(Protocol):
    """状态回调协议

    定义 Agent 状态变化时的回调接口。
    使用 Protocol 而非 ABC，支持鸭子类型。

    三个 Agent 框架都通过此协议发送状态更新：
    - ClaudeAgent: 通过全局回调注册（hooks.py）
    - PydanticAIAgent: 通过构造函数参数传递
    - LangGraphAgent: 通过构造函数参数传递
    """

    async def on_event(self, event: AgentEvent) -> None:
        """接收事件通知

        Args:
            event: Agent 事件
        """
        ...


class NullCallback:
    """空回调实现

    当不需要状态输出时使用，避免 None 检查。
    """

    async def on_event(self, event: AgentEvent) -> None:
        """忽略所有事件"""
        pass


class CompositeCallback:
    """组合回调

    将多个回调组合在一起，事件会广播给所有回调。
    适用于同时需要显示和日志记录的场景。
    """

    def __init__(self, callbacks: list[StatusCallback] | None = None):
        """初始化组合回调

        Args:
            callbacks: 回调列表
        """
        self._callbacks: list[StatusCallback] = callbacks or []

    def add(self, callback: StatusCallback) -> None:
        """添加回调

        Args:
            callback: 要添加的回调
        """
        self._callbacks.append(callback)

    def remove(self, callback: StatusCallback) -> None:
        """移除回调

        Args:
            callback: 要移除的回调
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def clear(self) -> None:
        """清空所有回调"""
        self._callbacks.clear()

    async def on_event(self, event: AgentEvent) -> None:
        """广播事件到所有回调

        Args:
            event: Agent 事件
        """
        for callback in self._callbacks:
            try:
                await callback.on_event(event)
            except Exception as e:
                logger.warning(f"回调执行失败: {type(callback).__name__}: {e}")


class LoggingCallback:
    """日志回调

    将事件转换为结构化日志，便于调试和分析。
    与 loguru 集成。
    """

    def __init__(self, level: str = "DEBUG"):
        """初始化日志回调

        Args:
            level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        """
        self._level = level.upper()

    async def on_event(self, event: AgentEvent) -> None:
        """将事件记录为日志

        Args:
            event: Agent 事件
        """
        log_func = getattr(logger, self._level.lower(), logger.debug)

        if event.event_type == AgentEventType.THINKING_START:
            log_func("[Agent] 开始思考...")

        elif event.event_type == AgentEventType.THINKING_END:
            log_func("[Agent] 思考完成")

        elif event.event_type == AgentEventType.TOOL_CALL_START:
            tool_name = event.data.get("tool_name", "unknown")
            tool_input = event.data.get("tool_input", {})
            log_func(f"[ToolCall] {tool_name} | args: {_truncate_dict(tool_input)}")

        elif event.event_type == AgentEventType.TOOL_CALL_END:
            tool_name = event.data.get("tool_name", "unknown")
            duration = event.data.get("duration_ms", 0)
            count = event.data.get("result_count")
            count_str = f", {count} 条结果" if count is not None else ""
            log_func(f"[ToolCall] {tool_name} 完成 ({duration:.0f}ms{count_str})")

        elif event.event_type == AgentEventType.TOOL_CALL_ERROR:
            tool_name = event.data.get("tool_name", "unknown")
            error = event.data.get("error", "unknown")
            logger.warning(f"[ToolCall] {tool_name} 错误: {error}")

        elif event.event_type == AgentEventType.ITERATION_START:
            iteration = event.data.get("iteration", 1)
            log_func(f"[Agent] 第 {iteration} 轮推理")

        elif event.event_type == AgentEventType.RESPONSE_COMPLETE:
            total_tools = event.data.get("total_tool_calls", 0)
            duration = event.data.get("duration_ms", 0)
            log_func(f"[Agent] 响应完成: {total_tools} 次工具调用, 耗时 {duration:.0f}ms")


def _truncate_dict(data: dict[str, Any], max_str_len: int = 80) -> dict[str, Any]:
    """截断字典中的长字符串

    Args:
        data: 原始字典
        max_str_len: 字符串最大长度

    Returns:
        截断后的字典（新对象）
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, str) and len(value) > max_str_len:
            result[key] = value[:max_str_len] + "..."
        elif isinstance(value, dict):
            result[key] = _truncate_dict(value, max_str_len)
        elif isinstance(value, list):
            if len(value) > 5:
                result[key] = f"[{len(value)} items]"
            else:
                result[key] = value
        else:
            result[key] = value
    return result
