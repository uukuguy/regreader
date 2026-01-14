"""RegReader Coordinator（协调器）

简化版协调器，仅负责文件系统功能和事件记录。
路由决策由各个框架的 Orchestrator 通过 LLM 自主完成。

职责：
1. 记录查询和提示到 plan.md
2. 维护会话状态到 session_state.json
3. 发布事件到 EventBus
4. 不执行路由或 Subagent 调用
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from regreader.infrastructure.event_bus import Event, EventBus, SubagentEvent


@dataclass
class SessionState:
    """会话状态

    持久化到 coordinator/session_state.json
    """

    session_id: str
    """会话唯一标识"""

    started_at: datetime = field(default_factory=datetime.now)
    """会话开始时间"""

    query_count: int = 0
    """查询计数"""

    current_reg_id: str | None = None
    """当前规程标识"""

    last_query: str | None = None
    """最后一次查询"""

    last_hints: dict[str, Any] | None = None
    """最后一次提取的提示"""

    accumulated_sources: list[str] = field(default_factory=list)
    """累积的来源（跨查询）"""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "query_count": self.query_count,
            "current_reg_id": self.current_reg_id,
            "last_query": self.last_query,
            "last_hints": self.last_hints,
            "accumulated_sources": self.accumulated_sources,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionState":
        """从字典创建"""
        return cls(
            session_id=data["session_id"],
            started_at=datetime.fromisoformat(data["started_at"]),
            query_count=data.get("query_count", 0),
            current_reg_id=data.get("current_reg_id"),
            last_query=data.get("last_query"),
            last_hints=data.get("last_hints"),
            accumulated_sources=data.get("accumulated_sources", []),
        )


class Coordinator:
    """RegReader 协调器（简化版）

    仅负责文件系统功能和事件记录，不执行路由或 Subagent 调用。
    路由决策由各个框架的 Orchestrator 通过 LLM 自主完成。

    Attributes:
        work_dir: 协调器工作目录
        event_bus: 事件总线（可选）
        session_state: 会话状态
    """

    def __init__(
        self,
        work_dir: Path | None = None,
        event_bus: EventBus | None = None,
    ):
        """初始化协调器

        Args:
            work_dir: 工作目录（默认 coordinator/）
            event_bus: 事件总线（可选）
        """
        self.work_dir = work_dir or Path("coordinator")
        self.event_bus = event_bus

        # 初始化会话状态
        import uuid
        self.session_state = SessionState(session_id=str(uuid.uuid4())[:8])

        # 确保目录存在
        if self.uses_file_system:
            self._ensure_directories()

    @property
    def uses_file_system(self) -> bool:
        """是否使用文件系统模式

        启用条件：work_dir 不为 None
        """
        return self.work_dir is not None

    def _ensure_directories(self) -> None:
        """确保工作目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "logs").mkdir(exist_ok=True)

    async def log_query(
        self,
        query: str,
        hints: dict[str, Any],
        reg_id: str | None = None,
    ) -> None:
        """记录查询到 plan.md

        Args:
            query: 用户查询
            hints: 提取的提示信息
            reg_id: 规程标识
        """
        logger.info(f"记录查询: {query}")

        # 更新会话状态
        self.session_state.query_count += 1
        self.session_state.last_query = query
        self.session_state.last_hints = hints
        if reg_id:
            self.session_state.current_reg_id = reg_id

        # 写入 plan.md
        if self.uses_file_system:
            self._write_plan(query, hints, reg_id)

        # 发布任务开始事件
        task_id = f"task_{self.session_state.query_count}"
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=SubagentEvent.TASK_STARTED,
                source="coordinator",
                target="orchestrator",
                payload={
                    "task_id": task_id,
                    "query": query,
                    "reg_id": reg_id,
                    "hints": hints,
                },
            ))

    def _write_plan(
        self,
        query: str,
        hints: dict[str, Any],
        reg_id: str | None,
    ) -> None:
        """写入计划文件

        Args:
            query: 用户查询
            hints: 提取的提示信息
            reg_id: 规程标识
        """
        plan_file = self.work_dir / "plan.md"

        # 构建计划内容
        plan_content = f"""# Query {self.session_state.query_count}

**Time**: {datetime.now().isoformat()}
**Query**: {query}
**Regulation**: {reg_id or 'N/A'}

## Extracted Hints

"""
        if hints:
            for key, value in hints.items():
                plan_content += f"- **{key}**: {value}\n"
        else:
            plan_content += "- No hints extracted\n"

        plan_content += "\n---\n\n"

        # 追加到文件
        with open(plan_file, "a", encoding="utf-8") as f:
            f.write(plan_content)

        logger.debug(f"Plan written to {plan_file}")

    async def write_result(
        self,
        content: str,
        sources: list[str],
        tool_calls: list[dict],
    ) -> None:
        """记录结果到 plan.md

        Args:
            content: 回答内容
            sources: 来源列表
            tool_calls: 工具调用列表
        """
        logger.info("记录结果")

        # 更新累积来源
        self.session_state.accumulated_sources.extend(sources)
        self.session_state.accumulated_sources = list(set(self.session_state.accumulated_sources))

        # 写入结果
        if self.uses_file_system:
            self._append_result(content, sources, tool_calls)

        # 保存会话状态
        if self.uses_file_system:
            self._save_session_state()

        # 发布任务完成事件
        task_id = f"task_{self.session_state.query_count}"
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=SubagentEvent.TASK_COMPLETED,
                source="coordinator",
                target=None,
                payload={
                    "task_id": task_id,
                    "source_count": len(sources),
                    "tool_call_count": len(tool_calls),
                },
            ))

    def _append_result(
        self,
        content: str,
        sources: list[str],
        tool_calls: list[dict],
    ) -> None:
        """追加结果到 plan.md

        Args:
            content: 回答内容
            sources: 来源列表
            tool_calls: 工具调用列表
        """
        plan_file = self.work_dir / "plan.md"

        result_content = f"""## Result

**Content**:
{content}

**Sources** ({len(sources)}):
"""
        for source in sources:
            result_content += f"- {source}\n"

        result_content += f"\n**Tool Calls** ({len(tool_calls)}):\n"
        for i, call in enumerate(tool_calls, 1):
            result_content += f"{i}. {call.get('name', 'unknown')}\n"

        result_content += "\n---\n\n"

        # 追加到文件
        with open(plan_file, "a", encoding="utf-8") as f:
            f.write(result_content)

        logger.debug(f"Result appended to {plan_file}")

    def _save_session_state(self) -> None:
        """保存会话状态到 session_state.json"""
        state_file = self.work_dir / "session_state.json"

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(self.session_state.to_dict(), f, indent=2, ensure_ascii=False)

        logger.debug(f"Session state saved to {state_file}")

    def load_session_state(self) -> None:
        """从 session_state.json 加载会话状态"""
        state_file = self.work_dir / "session_state.json"

        if not state_file.exists():
            logger.debug("No existing session state found")
            return

        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.session_state = SessionState.from_dict(data)

        logger.debug(f"Session state loaded from {state_file}")

    async def reset_session(self) -> None:
        """重置会话状态"""
        import uuid
        self.session_state = SessionState(session_id=str(uuid.uuid4())[:8])

        if self.uses_file_system:
            self._save_session_state()

        logger.info("Session reset")

    async def close(self) -> None:
        """关闭协调器"""
        if self.uses_file_system:
            self._save_session_state()

        logger.info("Coordinator closed")
