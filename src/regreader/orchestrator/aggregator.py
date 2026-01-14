"""结果聚合器

聚合多个 Subagent 的结果，生成最终响应。
"""

from typing import TYPE_CHECKING

from regreader.subagents.config import SubagentType
from regreader.subagents.result import AggregatedResult, SubagentResult

if TYPE_CHECKING:
    from regreader.agents.base import AgentResponse


class ResultAggregator:
    """结果聚合器

    聚合多个 SubagentResult，生成统一的最终响应。

    聚合策略：
    1. 内容合并：按 Subagent 类型组织内容
    2. 来源去重：合并所有来源并去重
    3. 工具调用合并：汇总所有工具调用记录
    """

    def __init__(self, include_agent_labels: bool = True):
        """初始化聚合器

        Args:
            include_agent_labels: 是否在输出中包含 Subagent 标签
        """
        self.include_agent_labels = include_agent_labels

    def aggregate(
        self,
        results: list[SubagentResult],
        original_query: str | None = None,
    ) -> AggregatedResult:
        """聚合 Subagent 结果

        Args:
            results: Subagent 结果列表
            original_query: 原始用户查询（可选，用于上下文）

        Returns:
            AggregatedResult 聚合结果
        """
        if not results:
            return AggregatedResult(
                content="未获取到任何结果",
                sources=[],
                tool_calls=[],
                subagent_results=[],
            )

        # 分离成功和失败的结果
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        # 聚合内容
        content = self._aggregate_content(successful, failed)

        # 聚合来源（去重）
        sources = self._aggregate_sources(results)

        # 聚合工具调用
        tool_calls = self._aggregate_tool_calls(results)

        return AggregatedResult(
            content=content,
            sources=sources,
            tool_calls=tool_calls,
            subagent_results=results,
        )

    def _aggregate_content(
        self,
        successful: list[SubagentResult],
        failed: list[SubagentResult],
    ) -> str:
        """聚合内容

        Args:
            successful: 成功的结果
            failed: 失败的结果

        Returns:
            聚合后的内容
        """
        parts = []

        # 处理成功的结果
        if len(successful) == 1:
            # 单一结果，直接返回内容
            parts.append(successful[0].content)
        elif len(successful) > 1:
            # 多个结果，按类型组织
            for result in successful:
                if result.has_content:
                    if self.include_agent_labels:
                        label = self._get_agent_label(result.agent_type)
                        parts.append(f"## {label}\n\n{result.content}")
                    else:
                        parts.append(result.content)

        # 处理失败的结果
        if failed and not successful:
            # 所有都失败了
            error_msgs = [f"- {r.agent_type.value}: {r.error}" for r in failed]
            parts.append("执行过程中遇到错误：\n" + "\n".join(error_msgs))

        return "\n\n".join(parts) if parts else "未找到相关内容"

    def _aggregate_sources(self, results: list[SubagentResult]) -> list[str]:
        """聚合来源（去重）

        Args:
            results: 所有结果

        Returns:
            去重后的来源列表
        """
        sources = []
        seen = set()

        for result in results:
            for source in result.sources:
                if source and source not in seen:
                    sources.append(source)
                    seen.add(source)

        return sources

    def _aggregate_tool_calls(self, results: list[SubagentResult]) -> list[dict]:
        """聚合工具调用

        Args:
            results: 所有结果

        Returns:
            工具调用列表
        """
        tool_calls = []
        for result in results:
            for tc in result.tool_calls:
                # 添加来源标记
                tc_with_source = tc.copy()
                tc_with_source["subagent"] = result.agent_type.value
                tool_calls.append(tc_with_source)
        return tool_calls

    def _get_agent_label(self, agent_type: SubagentType) -> str:
        """获取 Subagent 显示标签

        Args:
            agent_type: Subagent 类型

        Returns:
            显示标签
        """
        labels = {
            SubagentType.SEARCH: "搜索结果",
            SubagentType.TABLE: "表格内容",
            SubagentType.REFERENCE: "引用内容",
            SubagentType.DISCOVERY: "相关发现",
        }
        return labels.get(agent_type, agent_type.value)

    def to_agent_response(self, aggregated: AggregatedResult) -> "AgentResponse":
        """转换为 AgentResponse 格式

        Args:
            aggregated: 聚合结果

        Returns:
            AgentResponse 实例
        """
        from regreader.agents.base import AgentResponse

        return AgentResponse(
            content=aggregated.content,
            sources=aggregated.sources,
            tool_calls=aggregated.tool_calls,
        )


class StreamingAggregator:
    """流式聚合器

    支持实时聚合 Subagent 的流式输出。
    """

    def __init__(self):
        """初始化流式聚合器"""
        self._results: dict[SubagentType, SubagentResult] = {}
        self._current_content: dict[SubagentType, list[str]] = {}

    def add_delta(self, agent_type: SubagentType, delta: str) -> None:
        """添加内容增量

        Args:
            agent_type: Subagent 类型
            delta: 内容增量
        """
        if agent_type not in self._current_content:
            self._current_content[agent_type] = []
        self._current_content[agent_type].append(delta)

    def add_result(self, result: SubagentResult) -> None:
        """添加完整结果

        Args:
            result: Subagent 结果
        """
        self._results[result.agent_type] = result

    def get_current_content(self, agent_type: SubagentType) -> str:
        """获取当前累积的内容

        Args:
            agent_type: Subagent 类型

        Returns:
            累积的内容
        """
        if agent_type in self._current_content:
            return "".join(self._current_content[agent_type])
        return ""

    def finalize(self) -> AggregatedResult:
        """完成聚合

        Returns:
            最终聚合结果
        """
        aggregator = ResultAggregator()
        return aggregator.aggregate(list(self._results.values()))

    def reset(self) -> None:
        """重置状态"""
        self._results.clear()
        self._current_content.clear()
