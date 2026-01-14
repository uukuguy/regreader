"""Subagent 抽象基类

定义统一的 Subagent 接口，供三个框架（Claude SDK / Pydantic AI / LangGraph）实现。
支持可选的 Bash+FS 范式，通过 FileContext 实现文件系统隔离。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from regreader.infrastructure.file_context import FileContext
    from regreader.subagents.config import SubagentConfig
    from regreader.subagents.result import SubagentResult


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
    支持可选的 FileContext 实现 Bash+FS 范式的文件系统隔离。

    Attributes:
        config: Subagent 配置
        file_context: 文件上下文（可选，启用文件系统模式）
        _tool_calls: 工具调用记录
        _sources: 收集的来源
    """

    def __init__(
        self,
        config: "SubagentConfig",
        file_context: "FileContext | None" = None,
    ):
        """初始化 Subagent

        Args:
            config: Subagent 配置（包含工具列表、提示词等）
            file_context: 文件上下文（可选）。设置后启用文件系统模式，
                          任务通过文件传递，结果写入 scratch 目录。
        """
        self.config = config
        self.file_context = file_context
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

    @property
    def uses_file_system(self) -> bool:
        """是否使用文件系统模式

        Returns:
            True 表示启用 Bash+FS 范式
        """
        return self.file_context is not None

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

    # ==================== 文件系统模式支持 ====================

    def read_task_from_file(self) -> str | None:
        """从文件读取当前任务

        仅在文件系统模式下有效。

        Returns:
            任务内容，或 None（非文件系统模式）
        """
        if not self.file_context:
            return None
        return self.file_context.read_scratch("current_task.md")

    def write_result_to_file(self, result: "SubagentResult") -> None:
        """将结果写入文件

        仅在文件系统模式下有效。

        Args:
            result: Subagent 执行结果
        """
        if not self.file_context:
            return
        # 写入 JSON 结果
        import json
        result_dict = {
            "query": "",
            "content": result.content,
            "sources": result.sources,
            "tool_calls": result.tool_calls,
            "metadata": result.metadata,
            "success": result.success,
        }
        self.file_context.write_scratch("results.json", json.dumps(result_dict, ensure_ascii=False, indent=2))
        # 写入 Markdown 报告
        report = self._generate_report(result)
        self.file_context.write_scratch("final_report.md", report)

    def _generate_report(self, result: "SubagentResult") -> str:
        """生成 Markdown 格式报告

        Args:
            result: Subagent 执行结果

        Returns:
            Markdown 格式的报告内容
        """
        lines = [
            f"# {self.config.name} 执行报告",
            "",
            "## 执行结果",
            "",
            result.content or "无内容",
            "",
            "## 来源",
            "",
        ]
        for source in result.sources:
            lines.append(f"- {source}")
        lines.extend([
            "",
            "## 工具调用",
            "",
            f"共调用 {len(result.tool_calls)} 次工具",
        ])
        return "\n".join(lines)

    def log(self, message: str) -> None:
        """记录日志

        在文件系统模式下写入日志文件，否则使用 loguru。

        Args:
            message: 日志消息
        """
        if self.file_context:
            self.file_context.log(message)
        else:
            from loguru import logger
            logger.info(f"[{self.name}] {message}")
