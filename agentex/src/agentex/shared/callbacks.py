"""事件回调系统"""

from abc import ABC, abstractmethod
from typing import Callable

from agentex.types import AgentEvent


class StatusCallback(ABC):
    """状态回调抽象基类"""

    @abstractmethod
    async def on_event(self, event: AgentEvent) -> None:
        """处理事件

        Args:
            event: Agent 事件
        """
        ...


class NullCallback(StatusCallback):
    """空实现（无操作）"""

    async def on_event(self, event: AgentEvent) -> None:
        pass


class LoggingCallback(StatusCallback):
    """日志回调（调试用）"""

    def __init__(self, logger=None):
        self.logger = logger or print

    async def on_event(self, event: AgentEvent) -> None:
        self.logger(f"[{event.event_type}] {event.data}")


class CompositeCallback(StatusCallback):
    """组合回调"""

    def __init__(self, callbacks: list[StatusCallback]):
        self.callbacks = callbacks

    async def on_event(self, event: AgentEvent) -> None:
        for callback in self.callbacks:
            await callback.on_event(event)


class CallbackAdapter:
    """回调适配器

    将回调函数适配为 StatusCallback 接口。
    """

    def __init__(self, callback: Callable[[AgentEvent], None]):
        self._callback = callback

    async def on_event(self, event: AgentEvent) -> None:
        self._callback(event)
