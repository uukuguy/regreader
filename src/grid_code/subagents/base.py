"""Subagent 抽象基类

定义统一的 Subagent 接口，供三个框架（Claude SDK / Pydantic AI / LangGraph）实现。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grid_code.subagents.config import SubagentConfig
    from grid_code.subagents.result import SubagentResult


@dataclass
class SubagentContext:
    """Subagent 执行上下文

    由 Orchestrator 传递给 Subagent，包含执行任务所需的上下文信息。
    """

    query: str
    """原始用户查询"""

    reg_id: str | None = None
    """目标规程标识（如已知）"""

    chapter_scope: str | None = None
    """章节范围提示（如「第六章」）"""

    hints: dict[str, Any] = field(default_factory=dict)
    """额外提示信息

    可能包含：
    - page_hint: 页码提示
    - table_hint: 表格标识提示
    - annotation_hint: 注释标识提示
    - reference_text: 引用文本
    """

    parent_sources: list[str] = field(default_factory=list)
    """父级已收集的来源（避免重复）"""

    max_iterations: int | None = None
    """最大迭代次数（覆盖配置）"""


class BaseSubagent(ABC):
    """Subagent 抽象基类

    定义统一接口，确保三个框架实现的一致性。

    Attributes:
        config: Subagent 配置
        _tool_calls: 工具调用记录
        _sources: 收集的来源
    """

    def __init__(self, config: "SubagentConfig"):
        """初始化 Subagent

        Args:
            config: Subagent 配置（包含工具列表、提示词等）
        """
        self.config = config
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

    @property
    @abstractmethod
    def name(self) -> str:
        """Subagent 标识名

        Returns:
            标识名如 'search', 'table', 'reference'
        """
        pass

    @property
    def tools(self) -> list[str]:
        """可用工具列表

        Returns:
            MCP 工具名列表
        """
        return self.config.tools

    @property
    def system_prompt(self) -> str:
        """获取系统提示词

        Returns:
            专用系统提示词
        """
        return self.config.system_prompt

    @abstractmethod
    async def execute(self, context: SubagentContext) -> "SubagentResult":
        """执行 Subagent 任务

        Args:
            context: 执行上下文

        Returns:
            SubagentResult 包含内容、来源、工具调用记录
        """
        pass

    @abstractmethod
    async def reset(self) -> None:
        """重置 Subagent 状态

        清除工具调用记录和来源，准备下一次执行。
        """
        pass

    def _add_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: Any = None,
        duration_ms: float | None = None,
    ) -> None:
        """记录工具调用

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数
            tool_result: 工具返回结果
            duration_ms: 执行耗时（毫秒）
        """
        self._tool_calls.append({
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_result,
            "duration_ms": duration_ms,
        })

    def _add_source(self, source: str) -> None:
        """添加来源（去重）

        Args:
            source: 来源标识（如 'angui_2024 P85'）
        """
        if source and source not in self._sources:
            self._sources.append(source)

    def _extract_sources_from_result(self, result: Any) -> list[str]:
        """从工具结果中提取来源

        递归遍历字典和列表，提取 'source' 字段。

        Args:
            result: 工具返回结果

        Returns:
            提取的来源列表
        """
        sources = []

        if isinstance(result, dict):
            if "source" in result:
                sources.append(result["source"])
            for value in result.values():
                sources.extend(self._extract_sources_from_result(value))
        elif isinstance(result, list):
            for item in result:
                sources.extend(self._extract_sources_from_result(item))

        return sources

    def _clear_state(self) -> None:
        """清除内部状态"""
        self._tool_calls.clear()
        self._sources.clear()
