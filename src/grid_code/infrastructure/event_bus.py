"""EventBus 事件总线

Subagent 间松耦合通信机制，支持事件发布/订阅和文件持久化。
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from loguru import logger

# 可选依赖
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


class SubagentEvent(str, Enum):
    """Subagent 事件类型"""

    # 任务生命周期事件
    TASK_STARTED = "task_started"
    """任务开始"""

    TASK_COMPLETED = "task_completed"
    """任务完成"""

    TASK_FAILED = "task_failed"
    """任务失败"""

    TASK_CANCELLED = "task_cancelled"
    """任务取消"""

    # 协作事件
    HANDOFF_REQUEST = "handoff_request"
    """交接请求（请求另一个 Subagent 接手）"""

    HANDOFF_ACCEPTED = "handoff_accepted"
    """交接接受"""

    HANDOFF_REJECTED = "handoff_rejected"
    """交接拒绝"""

    # 工具事件
    TOOL_CALLED = "tool_called"
    """工具调用"""

    TOOL_COMPLETED = "tool_completed"
    """工具完成"""

    TOOL_FAILED = "tool_failed"
    """工具失败"""

    # 结果事件
    RESULT_READY = "result_ready"
    """结果就绪"""

    PARTIAL_RESULT = "partial_result"
    """部分结果"""

    # 系统事件
    SUBAGENT_STARTED = "subagent_started"
    """Subagent 启动"""

    SUBAGENT_STOPPED = "subagent_stopped"
    """Subagent 停止"""

    # 自定义事件
    CUSTOM = "custom"
    """自定义事件"""


@dataclass
class Event:
    """事件数据结构

    Attributes:
        event_type: 事件类型
        source: 事件来源（Subagent 名称）
        target: 事件目标（可选，None 表示广播）
        payload: 事件负载数据
        timestamp: 事件时间戳
        event_id: 事件唯一标识
        correlation_id: 关联 ID（用于追踪相关事件链）
        metadata: 额外元数据
    """

    event_type: SubagentEvent
    """事件类型"""

    source: str
    """事件来源（Subagent 名称）"""

    target: str | None = None
    """事件目标（可选，None 表示广播）"""

    payload: dict[str, Any] = field(default_factory=dict)
    """事件负载数据"""

    timestamp: datetime = field(default_factory=datetime.now)
    """事件时间戳"""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    """事件唯一标识"""

    correlation_id: str | None = None
    """关联 ID（用于追踪相关事件链）"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """额外元数据"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            事件字典表示
        """
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        """转换为 JSON 字符串

        Returns:
            JSON 字符串
        """
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """从字典创建事件

        Args:
            data: 事件字典

        Returns:
            Event 实例
        """
        data = data.copy()
        data["event_type"] = SubagentEvent(data["event_type"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """从 JSON 字符串创建事件

        Args:
            json_str: JSON 字符串

        Returns:
            Event 实例
        """
        return cls.from_dict(json.loads(json_str))


# 事件处理器类型
EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], Any]  # 返回 Awaitable


class EventBus:
    """事件总线

    提供 Subagent 间的松耦合通信机制。

    特点：
    1. 支持同步和异步事件处理
    2. 支持事件持久化到文件
    3. 支持事件重放（从文件恢复）
    4. 支持事件过滤（按类型、来源、目标）

    Attributes:
        project_root: 项目根目录
        events_dir: 事件日志目录
        persist: 是否持久化事件
    """

    def __init__(
        self,
        project_root: Path | None = None,
        events_dir: str = "coordinator/logs",
        persist: bool = True,
    ):
        """初始化事件总线

        Args:
            project_root: 项目根目录
            events_dir: 事件日志目录
            persist: 是否持久化事件
        """
        self.project_root = project_root or Path.cwd()
        self.events_dir = self.project_root / events_dir
        self.persist = persist

        # 订阅者映射：事件类型 -> 处理器列表
        self._subscribers: dict[SubagentEvent, list[EventHandler]] = defaultdict(list)
        self._async_subscribers: dict[SubagentEvent, list[AsyncEventHandler]] = defaultdict(list)

        # 通配符订阅者（接收所有事件）
        self._wildcard_subscribers: list[EventHandler] = []
        self._async_wildcard_subscribers: list[AsyncEventHandler] = []

        # 目标订阅者：subagent_name -> 处理器
        self._target_subscribers: dict[str, list[EventHandler]] = defaultdict(list)

        # 事件历史（内存中保留最近的事件）
        self._history: list[Event] = []
        self._max_history = 1000

        # 确保目录存在
        if self.persist:
            self.events_dir.mkdir(parents=True, exist_ok=True)

    def subscribe(
        self,
        event_type: SubagentEvent | None,
        handler: EventHandler,
    ) -> None:
        """订阅事件（同步处理器）

        Args:
            event_type: 事件类型，None 表示订阅所有事件
            handler: 事件处理函数
        """
        if event_type is None:
            self._wildcard_subscribers.append(handler)
        else:
            self._subscribers[event_type].append(handler)

    def subscribe_async(
        self,
        event_type: SubagentEvent | None,
        handler: AsyncEventHandler,
    ) -> None:
        """订阅事件（异步处理器）

        Args:
            event_type: 事件类型，None 表示订阅所有事件
            handler: 异步事件处理函数
        """
        if event_type is None:
            self._async_wildcard_subscribers.append(handler)
        else:
            self._async_subscribers[event_type].append(handler)

    def subscribe_target(self, target: str, handler: EventHandler) -> None:
        """订阅发送给特定目标的事件

        Args:
            target: 目标 Subagent 名称
            handler: 事件处理函数
        """
        self._target_subscribers[target].append(handler)

    def unsubscribe(
        self,
        event_type: SubagentEvent | None,
        handler: EventHandler,
    ) -> None:
        """取消订阅

        Args:
            event_type: 事件类型
            handler: 要移除的处理函数
        """
        if event_type is None:
            if handler in self._wildcard_subscribers:
                self._wildcard_subscribers.remove(handler)
        else:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        """发布事件（同步）

        Args:
            event: 事件对象
        """
        # 添加到历史
        self._add_to_history(event)

        # 持久化
        if self.persist:
            self._persist_event(event)

        # 调用通配符订阅者
        for handler in self._wildcard_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        # 调用类型订阅者
        for handler in self._subscribers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

        # 调用目标订阅者
        if event.target:
            for handler in self._target_subscribers.get(event.target, []):
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error: {e}")

        logger.debug(
            f"Published event: {event.event_type.value} "
            f"from {event.source} to {event.target or 'broadcast'}"
        )

    async def publish_async(self, event: Event) -> None:
        """发布事件（异步）

        Args:
            event: 事件对象
        """
        # 添加到历史
        self._add_to_history(event)

        # 持久化
        if self.persist:
            await self._persist_event_async(event)

        # 调用同步处理器
        self.publish(event)

        # 调用异步通配符订阅者
        for handler in self._async_wildcard_subscribers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Async event handler error: {e}")

        # 调用异步类型订阅者
        for handler in self._async_subscribers.get(event.event_type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Async event handler error: {e}")

    def _add_to_history(self, event: Event) -> None:
        """添加事件到历史

        Args:
            event: 事件对象
        """
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    def _persist_event(self, event: Event) -> None:
        """同步持久化事件

        Args:
            event: 事件对象
        """
        log_file = self.events_dir / "events.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    async def _persist_event_async(self, event: Event) -> None:
        """异步持久化事件

        Args:
            event: 事件对象
        """
        log_file = self.events_dir / "events.jsonl"
        if HAS_AIOFILES:
            async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
                await f.write(event.to_json() + "\n")
        else:
            # 回退到同步写入
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")

    def replay_events(
        self,
        since: datetime | None = None,
        event_types: list[SubagentEvent] | None = None,
        source: str | None = None,
        target: str | None = None,
    ) -> list[Event]:
        """重放事件（从文件恢复）

        Args:
            since: 起始时间（可选）
            event_types: 事件类型过滤（可选）
            source: 来源过滤（可选）
            target: 目标过滤（可选）

        Returns:
            匹配的事件列表
        """
        events = []
        log_file = self.events_dir / "events.jsonl"

        if not log_file.exists():
            return events

        with log_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = Event.from_json(line)

                    # 时间过滤
                    if since and event.timestamp < since:
                        continue

                    # 类型过滤
                    if event_types and event.event_type not in event_types:
                        continue

                    # 来源过滤
                    if source and event.source != source:
                        continue

                    # 目标过滤
                    if target and event.target != target:
                        continue

                    events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse event: {e}")

        return events

    def get_recent_events(
        self,
        count: int = 100,
        event_types: list[SubagentEvent] | None = None,
    ) -> list[Event]:
        """获取最近的事件（从内存）

        Args:
            count: 返回数量
            event_types: 事件类型过滤

        Returns:
            最近的事件列表
        """
        events = self._history[-count:]
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        return events

    def get_events_by_correlation(self, correlation_id: str) -> list[Event]:
        """获取关联事件链

        Args:
            correlation_id: 关联 ID

        Returns:
            关联的事件列表
        """
        return [e for e in self._history if e.correlation_id == correlation_id]

    def clear_history(self) -> None:
        """清空内存中的事件历史"""
        self._history.clear()

    def rotate_log(self, max_size_mb: int = 10) -> None:
        """轮转日志文件

        Args:
            max_size_mb: 最大文件大小（MB）
        """
        log_file = self.events_dir / "events.jsonl"
        if not log_file.exists():
            return

        size_mb = log_file.stat().st_size / (1024 * 1024)
        if size_mb > max_size_mb:
            # 重命名为带时间戳的备份
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = self.events_dir / f"events_{timestamp}.jsonl"
            log_file.rename(backup)
            logger.info(f"Rotated event log to {backup}")

    # ==================== 便捷方法 ====================

    def emit_task_started(
        self,
        source: str,
        task_id: str,
        task_type: str,
        **kwargs: Any,
    ) -> Event:
        """发布任务开始事件

        Args:
            source: 来源 Subagent
            task_id: 任务 ID
            task_type: 任务类型
            **kwargs: 额外数据

        Returns:
            发布的事件
        """
        event = Event(
            event_type=SubagentEvent.TASK_STARTED,
            source=source,
            payload={"task_id": task_id, "task_type": task_type, **kwargs},
            correlation_id=task_id,
        )
        self.publish(event)
        return event

    def emit_task_completed(
        self,
        source: str,
        task_id: str,
        result: Any = None,
        **kwargs: Any,
    ) -> Event:
        """发布任务完成事件

        Args:
            source: 来源 Subagent
            task_id: 任务 ID
            result: 任务结果
            **kwargs: 额外数据

        Returns:
            发布的事件
        """
        event = Event(
            event_type=SubagentEvent.TASK_COMPLETED,
            source=source,
            payload={"task_id": task_id, "result": result, **kwargs},
            correlation_id=task_id,
        )
        self.publish(event)
        return event

    def emit_handoff_request(
        self,
        source: str,
        target: str,
        task_id: str,
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> Event:
        """发布交接请求事件

        Args:
            source: 来源 Subagent
            target: 目标 Subagent
            task_id: 任务 ID
            reason: 交接原因
            context: 上下文信息

        Returns:
            发布的事件
        """
        event = Event(
            event_type=SubagentEvent.HANDOFF_REQUEST,
            source=source,
            target=target,
            payload={
                "task_id": task_id,
                "reason": reason,
                "context": context or {},
            },
            correlation_id=task_id,
        )
        self.publish(event)
        return event

    def __repr__(self) -> str:
        return (
            f"EventBus("
            f"subscribers={sum(len(s) for s in self._subscribers.values())}, "
            f"history={len(self._history)})"
        )
