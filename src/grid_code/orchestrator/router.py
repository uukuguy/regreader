"""Subagent 路由器

根据查询意图选择和调度 Subagent。
"""

from typing import TYPE_CHECKING

from grid_code.orchestrator.analyzer import QueryIntent
from grid_code.subagents.config import SubagentType

if TYPE_CHECKING:
    from grid_code.subagents.base import BaseSubagent, SubagentContext
    from grid_code.subagents.result import SubagentResult


class SubagentRouter:
    """Subagent 路由器

    根据 QueryIntent 选择和调度 Subagent 执行。
    支持顺序和并行执行模式。

    Attributes:
        subagents: 可用的 Subagent 实例映射
        mode: 执行模式（"sequential" 或 "parallel"）
    """

    def __init__(
        self,
        subagents: dict[SubagentType, "BaseSubagent"],
        mode: str = "sequential",
    ):
        """初始化路由器

        Args:
            subagents: 类型到 Subagent 实例的映射
            mode: 执行模式，"sequential" 或 "parallel"
        """
        self.subagents = subagents
        self.mode = mode

    def route(self, intent: QueryIntent) -> list[SubagentType]:
        """根据意图确定要调用的 Subagent

        Args:
            intent: 查询意图分析结果

        Returns:
            需要调用的 Subagent 类型列表（按优先级排序）
        """
        selected = []

        # 添加主要 Subagent
        if intent.primary_type in self.subagents:
            selected.append(intent.primary_type)

        # 添加次要 Subagent
        for agent_type in intent.secondary_types:
            if agent_type in self.subagents and agent_type not in selected:
                selected.append(agent_type)

        # 如果没有匹配，回退到 SearchAgent
        if not selected and SubagentType.SEARCH in self.subagents:
            selected.append(SubagentType.SEARCH)

        return selected

    async def execute(
        self,
        intent: QueryIntent,
        context: "SubagentContext",
    ) -> list["SubagentResult"]:
        """执行路由和调度

        Args:
            intent: 查询意图
            context: Subagent 上下文

        Returns:
            各 Subagent 的执行结果列表
        """
        selected_types = self.route(intent)

        if self.mode == "parallel":
            return await self._execute_parallel(selected_types, context)
        else:
            return await self._execute_sequential(selected_types, context)

    async def _execute_sequential(
        self,
        agent_types: list[SubagentType],
        context: "SubagentContext",
    ) -> list["SubagentResult"]:
        """顺序执行 Subagent

        后续 Subagent 可以使用前置 Subagent 的结果。

        Args:
            agent_types: 要执行的类型列表
            context: 基础上下文

        Returns:
            结果列表
        """
        results = []
        accumulated_sources = list(context.parent_sources)

        for agent_type in agent_types:
            subagent = self.subagents[agent_type]

            # 更新上下文，包含之前的来源
            updated_context = SubagentContext(
                query=context.query,
                reg_id=context.reg_id,
                chapter_scope=context.chapter_scope,
                hints=context.hints.copy(),
                parent_sources=accumulated_sources,
                max_iterations=context.max_iterations,
            )

            result = await subagent.execute(updated_context)
            results.append(result)

            # 累积来源
            accumulated_sources.extend(result.sources)

        return results

    async def _execute_parallel(
        self,
        agent_types: list[SubagentType],
        context: "SubagentContext",
    ) -> list["SubagentResult"]:
        """并行执行 Subagent

        Args:
            agent_types: 要执行的类型列表
            context: 基础上下文

        Returns:
            结果列表
        """
        import asyncio

        tasks = []
        for agent_type in agent_types:
            subagent = self.subagents[agent_type]
            tasks.append(subagent.execute(context))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理异常
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                from grid_code.subagents.result import SubagentResult
                processed_results.append(SubagentResult(
                    agent_type=agent_types[i],
                    success=False,
                    content="",
                    error=str(result),
                ))
            else:
                processed_results.append(result)

        return processed_results

    def get_subagent(self, agent_type: SubagentType) -> "BaseSubagent | None":
        """获取指定类型的 Subagent

        Args:
            agent_type: Subagent 类型

        Returns:
            Subagent 实例，不存在返回 None
        """
        return self.subagents.get(agent_type)

    def has_subagent(self, agent_type: SubagentType) -> bool:
        """检查是否有指定类型的 Subagent

        Args:
            agent_type: Subagent 类型

        Returns:
            是否存在
        """
        return agent_type in self.subagents


# 导入 SubagentContext 用于类型提示
from grid_code.subagents.base import SubagentContext  # noqa: E402
