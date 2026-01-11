"""测试 EventBus 事件总线"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from grid_code.infrastructure.event_bus import Event, EventBus, SubagentEvent


class TestSubagentEvent:
    """SubagentEvent 枚举测试"""

    def test_event_types(self) -> None:
        """测试事件类型"""
        assert SubagentEvent.TASK_STARTED.value == "task_started"
        assert SubagentEvent.TASK_COMPLETED.value == "task_completed"
        assert SubagentEvent.HANDOFF_REQUEST.value == "handoff_request"

    def test_all_events(self) -> None:
        """测试所有事件类型"""
        expected_events = [
            "task_started", "task_completed", "task_failed",
            "handoff_request", "handoff_accepted", "handoff_rejected",
            "result_ready", "error_occurred", "resource_request",
            "resource_granted", "state_changed", "log_message",
            "heartbeat", "shutdown",
        ]
        actual_events = [e.value for e in SubagentEvent]
        for expected in expected_events:
            assert expected in actual_events


class TestEvent:
    """Event 数据类测试"""

    def test_event_creation(self) -> None:
        """测试事件创建"""
        event = Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="coordinator",
            target="regsearch",
            payload={"task_id": "task_001", "query": "test"},
        )
        assert event.event_type == SubagentEvent.TASK_STARTED
        assert event.source == "coordinator"
        assert event.target == "regsearch"
        assert event.payload["task_id"] == "task_001"

    def test_event_default_timestamp(self) -> None:
        """测试事件默认时间戳"""
        before = datetime.now()
        event = Event(
            event_type=SubagentEvent.HEARTBEAT,
            source="test",
        )
        after = datetime.now()
        assert before <= event.timestamp <= after

    def test_event_to_dict(self) -> None:
        """测试事件序列化"""
        event = Event(
            event_type=SubagentEvent.TASK_COMPLETED,
            source="regsearch",
            target="coordinator",
            payload={"success": True},
        )
        d = event.to_dict()
        assert d["event_type"] == "task_completed"
        assert d["source"] == "regsearch"
        assert "timestamp" in d

    def test_event_from_dict(self) -> None:
        """测试事件反序列化"""
        data = {
            "event_type": "task_started",
            "source": "coordinator",
            "target": "regsearch",
            "payload": {"query": "test"},
            "timestamp": "2024-01-15T10:30:00",
        }
        event = Event.from_dict(data)
        assert event.event_type == SubagentEvent.TASK_STARTED
        assert event.source == "coordinator"


class TestEventBus:
    """EventBus 单元测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def event_bus(self, temp_dir: Path) -> EventBus:
        """创建 EventBus 实例"""
        return EventBus(log_dir=temp_dir)

    def test_publish(self, event_bus: EventBus) -> None:
        """测试事件发布"""
        event = Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="coordinator",
            payload={"task_id": "001"},
        )
        event_bus.publish(event)
        assert len(event_bus._events) == 1

    def test_subscribe_and_notify(self, event_bus: EventBus) -> None:
        """测试事件订阅和通知"""
        received_events = []

        def handler(event: Event) -> None:
            received_events.append(event)

        event_bus.subscribe(SubagentEvent.TASK_COMPLETED, handler)

        # 发布匹配的事件
        event_bus.publish(Event(
            event_type=SubagentEvent.TASK_COMPLETED,
            source="regsearch",
            payload={"success": True},
        ))

        assert len(received_events) == 1
        assert received_events[0].event_type == SubagentEvent.TASK_COMPLETED

    def test_subscribe_no_match(self, event_bus: EventBus) -> None:
        """测试不匹配的订阅"""
        received_events = []

        def handler(event: Event) -> None:
            received_events.append(event)

        event_bus.subscribe(SubagentEvent.TASK_FAILED, handler)

        # 发布不匹配的事件
        event_bus.publish(Event(
            event_type=SubagentEvent.TASK_COMPLETED,
            source="regsearch",
        ))

        assert len(received_events) == 0

    def test_multiple_subscribers(self, event_bus: EventBus) -> None:
        """测试多个订阅者"""
        count = [0]

        def handler1(event: Event) -> None:
            count[0] += 1

        def handler2(event: Event) -> None:
            count[0] += 10

        event_bus.subscribe(SubagentEvent.HEARTBEAT, handler1)
        event_bus.subscribe(SubagentEvent.HEARTBEAT, handler2)

        event_bus.publish(Event(
            event_type=SubagentEvent.HEARTBEAT,
            source="test",
        ))

        assert count[0] == 11

    def test_file_persistence(self, event_bus: EventBus, temp_dir: Path) -> None:
        """测试文件持久化"""
        event_bus.publish(Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="test",
            payload={"id": 1},
        ))
        event_bus.publish(Event(
            event_type=SubagentEvent.TASK_COMPLETED,
            source="test",
            payload={"id": 1, "success": True},
        ))

        # 检查日志文件
        log_path = temp_dir / "events.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_replay_events(self, temp_dir: Path) -> None:
        """测试事件重放"""
        # 创建第一个 EventBus 并发布事件
        bus1 = EventBus(log_dir=temp_dir)
        bus1.publish(Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="test",
            payload={"id": 1},
        ))

        # 创建新的 EventBus 并重放
        bus2 = EventBus(log_dir=temp_dir)
        since = datetime.now() - timedelta(hours=1)
        events = bus2.replay_events(since)

        assert len(events) >= 1
        assert events[0].event_type == SubagentEvent.TASK_STARTED

    def test_get_events(self, event_bus: EventBus) -> None:
        """测试获取事件列表"""
        for i in range(5):
            event_bus.publish(Event(
                event_type=SubagentEvent.HEARTBEAT,
                source="test",
                payload={"count": i},
            ))

        events = event_bus.get_events(limit=3)
        assert len(events) == 3

    def test_clear_events(self, event_bus: EventBus) -> None:
        """测试清除事件"""
        event_bus.publish(Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="test",
        ))
        assert len(event_bus._events) == 1

        event_bus.clear()
        assert len(event_bus._events) == 0


class TestEventBusAsync:
    """EventBus 异步操作测试"""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """创建临时目录"""
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    @pytest.fixture
    def event_bus(self, temp_dir: Path) -> EventBus:
        """创建 EventBus 实例"""
        return EventBus(log_dir=temp_dir)

    @pytest.mark.asyncio
    async def test_async_publish(self, event_bus: EventBus) -> None:
        """测试异步发布"""
        event = Event(
            event_type=SubagentEvent.TASK_STARTED,
            source="async_test",
        )
        await event_bus.async_publish(event)
        assert len(event_bus._events) == 1

    @pytest.mark.asyncio
    async def test_async_wait_for_event(self, event_bus: EventBus) -> None:
        """测试异步等待事件"""
        import asyncio

        # 延迟发布事件
        async def delayed_publish():
            await asyncio.sleep(0.1)
            await event_bus.async_publish(Event(
                event_type=SubagentEvent.TASK_COMPLETED,
                source="test",
            ))

        asyncio.create_task(delayed_publish())

        # 等待事件（带超时）
        event = await event_bus.wait_for_event(
            SubagentEvent.TASK_COMPLETED,
            timeout=1.0,
        )
        assert event is not None
        assert event.event_type == SubagentEvent.TASK_COMPLETED
