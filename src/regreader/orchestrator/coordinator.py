"""RegReader Coordinator（协调器）

系统的核心调度中心，负责：
1. 接收用户查询请求
2. 分析查询意图
3. 调度合适的 Subagent 执行任务
4. 聚合并返回结果

支持 Bash+FS 范式的文件系统任务分派和事件通信。
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from regreader.infrastructure.event_bus import Event, EventBus, SubagentEvent
from regreader.orchestrator.aggregator import ResultAggregator
from regreader.orchestrator.analyzer import QueryAnalyzer, QueryIntent
from regreader.orchestrator.router import SubagentRouter
from regreader.subagents.base import SubagentContext
from regreader.subagents.config import SubagentType
from regreader.subagents.result import SubagentResult

if TYPE_CHECKING:
    from regreader.subagents.base import BaseSubagent


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

    last_intent: dict[str, Any] | None = None
    """最后一次意图分析结果"""

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
            "last_intent": self.last_intent,
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
            last_intent=data.get("last_intent"),
            accumulated_sources=data.get("accumulated_sources", []),
        )


class Coordinator:
    """RegReader 协调器

    系统的核心调度中心，整合查询分析、Subagent 路由和结果聚合。
    支持文件系统模式的任务分派和事件通信。

    Attributes:
        work_dir: 协调器工作目录
        analyzer: 查询分析器
        router: Subagent 路由器
        aggregator: 结果聚合器
        event_bus: 事件总线（可选）
        session_state: 会话状态
    """

    def __init__(
        self,
        subagents: dict[SubagentType, "BaseSubagent"],
        work_dir: Path | None = None,
        event_bus: EventBus | None = None,
        router_mode: str = "sequential",
    ):
        """初始化协调器

        Args:
            subagents: 可用的 Subagent 实例映射
            work_dir: 工作目录（默认 coordinator/）
            event_bus: 事件总线（可选）
            router_mode: 路由执行模式（sequential/parallel）
        """
        self.work_dir = work_dir or Path("coordinator")
        self.analyzer = QueryAnalyzer()
        self.router = SubagentRouter(subagents, mode=router_mode)
        self.aggregator = ResultAggregator()
        self.event_bus = event_bus

        # 初始化会话状态
        import uuid
        self.session_state = SessionState(session_id=str(uuid.uuid4())[:8])

        # 确保目录存在
        if self.uses_file_system:
            self._ensure_directories()

    @property
    def uses_file_system(self) -> bool:
        """是否使用文件系统模式"""
        return self.work_dir.exists() or self.work_dir.parent.exists()

    def _ensure_directories(self) -> None:
        """确保工作目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)
        (self.work_dir / "logs").mkdir(exist_ok=True)

    async def process_query(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        hints: dict[str, Any] | None = None,
    ) -> SubagentResult:
        """处理用户查询

        完整的查询处理流程：
        1. 分析查询意图
        2. 写入计划文件（文件系统模式）
        3. 发布任务开始事件
        4. 路由并执行 Subagent
        5. 聚合结果
        6. 发布任务完成事件
        7. 更新会话状态

        Args:
            query: 用户查询
            reg_id: 规程标识
            chapter_scope: 章节范围
            hints: 额外提示

        Returns:
            聚合后的 SubagentResult
        """
        logger.info(f"处理查询: {query}")

        # 1. 分析查询意图
        intent = await self.analyzer.analyze(query, reg_id)
        logger.debug(f"意图分析: primary={intent.primary_type}, hints={intent.hints}")

        # 合并提示
        combined_hints = {**intent.hints}
        if hints:
            combined_hints.update(hints)

        # 2. 写入计划文件
        if self.uses_file_system:
            self._write_plan(query, intent, reg_id, chapter_scope, combined_hints)

        # 3. 发布任务开始事件
        task_id = f"task_{self.session_state.query_count + 1}"
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=SubagentEvent.TASK_STARTED,
                source="coordinator",
                target=intent.primary_type.value if intent.primary_type else "unknown",
                payload={
                    "task_id": task_id,
                    "query": query,
                    "reg_id": reg_id,
                    "intent": {
                        "primary": intent.primary_type.value if intent.primary_type else None,
                        "secondary": [t.value for t in intent.secondary_types],
                    },
                },
            ))

        # 4. 构建上下文
        context = SubagentContext(
            query=query,
            reg_id=reg_id or self.session_state.current_reg_id,
            chapter_scope=chapter_scope,
            hints=combined_hints,
            parent_sources=self.session_state.accumulated_sources.copy(),
        )

        # 5. 路由并执行
        try:
            results = await self.router.execute(intent, context)
        except Exception as e:
            logger.error(f"执行失败: {e}")
            # 发布失败事件
            if self.event_bus:
                self.event_bus.publish(Event(
                    event_type=SubagentEvent.TASK_FAILED,
                    source="coordinator",
                    target=None,
                    payload={"task_id": task_id, "error": str(e)},
                ))
            return SubagentResult(
                content=f"查询处理失败: {e}",
                sources=[],
                tool_calls=[],
                success=False,
            )

        # 6. 聚合结果
        final_result = self.aggregator.aggregate(results)

        # 7. 发布任务完成事件
        if self.event_bus:
            self.event_bus.publish(Event(
                event_type=SubagentEvent.TASK_COMPLETED,
                source="coordinator",
                target=None,
                payload={
                    "task_id": task_id,
                    "success": final_result.success,
                    "source_count": len(final_result.sources),
                },
            ))

        # 8. 更新会话状态
        self._update_session_state(query, intent, reg_id, final_result)

        return final_result

    def _write_plan(
        self,
        query: str,
        intent: QueryIntent,
        reg_id: str | None,
        chapter_scope: str | None,
        hints: dict[str, Any],
    ) -> None:
        """写入计划文件

        Args:
            query: 用户查询
            intent: 查询意图
            reg_id: 规程标识
            chapter_scope: 章节范围
            hints: 提示信息
        """
        plan_content = f"""# 当前任务计划

## 查询
{query}

## 目标规程
{reg_id or "未指定"}

## 章节范围
{chapter_scope or "全文"}

## 意图分析
- 主要类型: {intent.primary_type.value if intent.primary_type else "未知"}
- 次要类型: {", ".join(t.value for t in intent.secondary_types) or "无"}

## 提示信息
{json.dumps(hints, ensure_ascii=False, indent=2)}

## 状态
- 创建时间: {datetime.now().isoformat()}
- 状态: 进行中
"""
        plan_path = self.work_dir / "plan.md"
        plan_path.write_text(plan_content, encoding="utf-8")
        logger.debug(f"计划已写入: {plan_path}")

    def _update_session_state(
        self,
        query: str,
        intent: QueryIntent,
        reg_id: str | None,
        result: SubagentResult,
    ) -> None:
        """更新会话状态

        Args:
            query: 查询
            intent: 意图
            reg_id: 规程标识
            result: 执行结果
        """
        self.session_state.query_count += 1
        self.session_state.last_query = query
        self.session_state.last_intent = {
            "primary": intent.primary_type.value if intent.primary_type else None,
            "secondary": [t.value for t in intent.secondary_types],
            "hints": intent.hints,
        }
        if reg_id:
            self.session_state.current_reg_id = reg_id

        # 累积来源（去重）
        for source in result.sources:
            if source not in self.session_state.accumulated_sources:
                self.session_state.accumulated_sources.append(source)

        # 持久化
        if self.uses_file_system:
            self._save_session_state()

    def _save_session_state(self) -> None:
        """保存会话状态到文件"""
        state_path = self.work_dir / "session_state.json"
        state_path.write_text(
            json.dumps(self.session_state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_session_state(self) -> bool:
        """从文件加载会话状态

        Returns:
            是否成功加载
        """
        state_path = self.work_dir / "session_state.json"
        if state_path.exists():
            try:
                data = json.loads(state_path.read_text(encoding="utf-8"))
                self.session_state = SessionState.from_dict(data)
                logger.info(f"恢复会话: {self.session_state.session_id}")
                return True
            except Exception as e:
                logger.warning(f"加载会话状态失败: {e}")
        return False

    def read_subagent_result(self, subagent_name: str) -> dict[str, Any] | None:
        """读取 Subagent 的结果文件

        Args:
            subagent_name: Subagent 名称（如 'regsearch'）

        Returns:
            结果字典，或 None
        """
        result_path = Path(f"subagents/{subagent_name}/scratch/results.json")
        if result_path.exists():
            try:
                return json.loads(result_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"读取结果失败: {e}")
        return None

    def get_subagent(self, agent_type: SubagentType) -> "BaseSubagent | None":
        """获取指定类型的 Subagent

        Args:
            agent_type: Subagent 类型

        Returns:
            Subagent 实例，或 None
        """
        return self.router.get_subagent(agent_type)

    async def reset(self) -> None:
        """重置协调器状态"""
        import uuid
        self.session_state = SessionState(session_id=str(uuid.uuid4())[:8])
        if self.uses_file_system:
            self._save_session_state()

    def log_event(self, message: str) -> None:
        """记录事件日志

        Args:
            message: 日志消息
        """
        if not self.uses_file_system:
            return

        log_path = self.work_dir / "logs" / "events.jsonl"
        event = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_state.session_id,
            "message": message,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
