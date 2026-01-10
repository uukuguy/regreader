"""Subagent 结果模型

定义统一的 SubagentResult，用于 Orchestrator 聚合各 Subagent 的输出。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grid_code.subagents.config import SubagentType


@dataclass
class SubagentResult:
    """Subagent 执行结果

    标准化的结果格式，便于 Orchestrator 聚合处理。

    Attributes:
        agent_type: 产生此结果的 Subagent 类型
        success: 执行是否成功
        content: 提取/生成的内容
        sources: 来源引用列表
        tool_calls: 工具调用历史
        data: 结构化数据（如表格、注释等）
        error: 错误信息（如果失败）
        confidence: 结果置信度
        follow_up_hints: 后续 Subagent 提示
    """

    agent_type: "SubagentType"
    """产生此结果的 Subagent 类型"""

    success: bool
    """执行是否成功"""

    content: str
    """提取/生成的内容（Markdown 格式）"""

    sources: list[str] = field(default_factory=list)
    """来源引用列表（如 ['angui_2024 P85', 'angui_2024 P86']）"""

    tool_calls: list[dict] = field(default_factory=list)
    """工具调用记录（用于调试和审计）"""

    data: dict[str, Any] = field(default_factory=dict)
    """结构化数据

    可能包含：
    - tables: 提取的表格数据
    - annotations: 注释内容
    - references: 解析的引用
    - toc: 目录结构
    """

    error: str | None = None
    """错误信息（仅当 success=False）"""

    confidence: float = 1.0
    """结果置信度（0.0-1.0）

    用于 Orchestrator 权衡多个 Subagent 的结果。
    """

    follow_up_hints: dict[str, Any] = field(default_factory=dict)
    """后续 Subagent 提示

    可能包含：
    - needs_reference_resolution: 需要解析引用
    - needs_annotation_lookup: 需要追踪注释
    - suggested_chapters: 建议搜索的章节
    """

    @property
    def has_content(self) -> bool:
        """是否有有效内容"""
        return bool(self.content and self.content.strip())

    @property
    def source_count(self) -> int:
        """来源数量"""
        return len(self.sources)

    @property
    def tool_call_count(self) -> int:
        """工具调用次数"""
        return len(self.tool_calls)

    def merge_sources(self, other_sources: list[str]) -> None:
        """合并来源（去重）

        Args:
            other_sources: 其他来源列表
        """
        for source in other_sources:
            if source and source not in self.sources:
                self.sources.append(source)

    def to_summary(self, max_length: int = 200) -> str:
        """生成简短摘要

        Args:
            max_length: 最大长度

        Returns:
            摘要文本
        """
        if not self.success:
            return f"[{self.agent_type.value}] 失败: {self.error}"

        content_preview = self.content[:max_length]
        if len(self.content) > max_length:
            content_preview += "..."

        return f"[{self.agent_type.value}] {content_preview} ({self.source_count} sources)"


@dataclass
class AggregatedResult:
    """聚合结果

    Orchestrator 汇总多个 SubagentResult 后的最终结果。
    """

    content: str
    """最终内容"""

    sources: list[str] = field(default_factory=list)
    """所有来源（去重）"""

    tool_calls: list[dict] = field(default_factory=list)
    """所有工具调用"""

    subagent_results: list[SubagentResult] = field(default_factory=list)
    """各 Subagent 原始结果"""

    @property
    def success(self) -> bool:
        """至少有一个 Subagent 成功"""
        return any(r.success for r in self.subagent_results)

    @property
    def total_tool_calls(self) -> int:
        """总工具调用次数"""
        return sum(r.tool_call_count for r in self.subagent_results)
