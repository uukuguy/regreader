"""Agent 状态显示模块

使用 Rich Live 实现类似 Claude Code 的实时状态输出。
支持紧凑模式、详细模式和静默模式。

增强功能：
- 双时间显示（思考耗时 + 执行耗时）
- API 时间显示（通过 httpx hooks 精确测量的 HTTP 往返时间）
- 详细结果摘要（结果类型、章节数、页码、内容预览）
- 流式文本输出（模型推理过程）
- 完成统计（总耗时、思考次数/耗时、API 次数/耗时、工具次数、来源数）
"""

import time
from contextlib import asynccontextmanager
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.text import Text

from grid_code.agents.callbacks import StatusCallback
from grid_code.agents.events import AgentEvent, AgentEventType
from grid_code.agents.result_parser import ToolResultSummary, format_page_sources
from grid_code.mcp.tool_metadata import get_tool_metadata


# ==================== 状态图标 ====================


class StatusIcons:
    """状态图标"""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    INFO = "→"
    SEPARATOR = "──"
    # 详细模式图标
    STATS = "📊"
    PAGES = "📄"
    PREVIEW = "📝"
    THINKING = "💭"
    TABLE = "📋"


# ==================== 颜色主题 ====================


class StatusColors:
    """状态颜色（与 Claude Code 风格一致）"""

    SPINNER = "cyan"
    SUCCESS = "green"
    ERROR = "red"
    WARNING = "yellow"
    DIM = "gray" # "dim"
    TOOL_NAME = "bold cyan"
    PARAM_KEY = "dim cyan"
    PARAM_VALUE = "white"
    COUNT = "bold green"
    DURATION = "dim"
    ITERATION = "bold yellow"
    # 详细模式颜色 - 使用更明亮的颜色
    THINKING_TIME = "yellow"  # 思考时间 - 黄色（步骤间总时间）
    API_TIME = "magenta"  # API时间 - 紫红色（httpx测量的HTTP往返）
    EXEC_TIME = "cyan"  # 执行时间 - 青色
    RESULT_TYPE = "green"  # 移除 dim
    PAGE_SOURCE = "blue"  # 移除 dim
    CONTENT_PREVIEW = "white"  # 移除 dim
    # 思考内容 - 使用明显但不刺眼的颜色
    STREAMING_TEXT = "italic cyan"  # 使用 cyan 替代 dim
    THINKING_TEXT = "bold white" # "italic magenta"  # 思考内容使用 magenta


# ==================== 核心显示类 ====================


class AgentStatusDisplay(StatusCallback):
    """Agent 状态显示器

    使用 Rich Live 实现实时状态更新，类似 Claude Code 的输出风格。

    显示效果示例（紧凑模式）：

    ⠋ 获取目录结构...
    ✓ 获取目录结构完成（12个章节）（1.2s）

    显示效果示例（详细模式）：

    💭 让我先查看规程的目录结构...

    ✓ get_toc(reg_id="angui_2024") (思考 1.7s, API 1.5s, 执行 9ms)
        📊 12 条结果 (chapters)
        📝 第1章 总则, 第2章 运行管理...

    💭 我需要在第3章中搜索安全距离相关内容...

    ✓ smart_search(query="安全距离") (思考 63.2s, API 62.5s/3次, 执行 1.4s)
        📊 8 条结果 (search_results)，涉及 3 个章节
        📄 来源: P85, P86, P92, P95
        📝 安全距离不应小于... | 作业人员与带电...

    → 统计: 总耗时 106.6s | 思考 74.0s/3次 | API 73.5s/6次 | 工具 3次 | 来源 5个
    """

    def __init__(
        self,
        console: Console | None = None,
        verbose: bool = False,
        show_duration: bool = True,
        max_history: int = 20,
    ):
        """初始化状态显示器

        Args:
            console: Rich Console 实例
            verbose: 详细模式（显示完整参数和结果摘要）
            show_duration: 是否显示执行耗时
            max_history: 保留的历史记录数量
        """
        self._console = console or Console()
        self._verbose = verbose
        self._show_duration = show_duration
        self._max_history = max_history

        # 状态存储
        self._current_status: Text | None = None
        self._tool_start_times: dict[str, float] = {}
        self._tool_thinking_times: dict[str, float] = {}  # 追踪每个工具的思考耗时
        self._tool_llm_times: dict[str, float] = {}  # 追踪每个工具的LLM调用耗时
        self._iteration_count: int = 0
        self._spinner_frame: int = 0

        # 时间追踪（用于计算思考耗时）
        self._last_tool_end_time: float | None = None
        self._query_start_time: float | None = None

        # LLM调用耗时追踪（思考时间）
        self._llm_call_start_time: float | None = None  # 当前LLM调用开始时间
        self._total_llm_duration_ms: float = 0  # 累计LLM调用耗时（思考时间）
        self._llm_call_count: int = 0  # LLM调用次数（思考次数）

        # API调用耗时追踪（通过 httpx hooks 精确测量）
        self._total_api_duration_ms: float = 0  # 累计API调用耗时
        self._total_api_call_count: int = 0  # API调用次数

        # 流式文本状态
        self._streaming_text: str = ""
        self._is_streaming: bool = False
        self._current_phase: str | None = None
        self._last_committed_text: str = ""  # 追踪已提交的文本，避免重复

        # Live 实例
        self._live: Live | None = None

    def _get_spinner_char(self) -> str:
        """获取当前 spinner 字符"""
        char = StatusIcons.SPINNER_FRAMES[self._spinner_frame]
        self._spinner_frame = (self._spinner_frame + 1) % len(StatusIcons.SPINNER_FRAMES)
        return char

    def _format_tool_params(self, params: dict[str, Any]) -> str:
        """格式化工具参数（只显示关键参数）

        Args:
            params: 工具参数字典

        Returns:
            格式化的参数字符串
        """
        if not params:
            return ""

        # 关键参数列表（按重要性排序）
        key_params = [
            "query", "reg_id", "limit", "start_page", "end_page",
            "section_number", "table_id", "annotation_id", "reference_text",
            "block_id", "pattern", "search_cells",
        ]

        parts = []
        for key in key_params:
            if key in params and params[key] is not None:
                value = params[key]
                # 截断长字符串
                if isinstance(value, str):
                    if len(value) > 25:
                        value = value[:25] + "..."
                    parts.append(f'{key}="{value}"')
                elif isinstance(value, bool):
                    parts.append(f"{key}={str(value).lower()}")
                else:
                    parts.append(f"{key}={value}")

        return ", ".join(parts) if parts else ""

    def _format_tool_call_start(self, event: AgentEvent) -> Text:
        """格式化工具调用开始状态

        Args:
            event: 工具调用开始事件

        Returns:
            格式化的 Text 对象
        """
        tool_name = event.data["tool_name"]
        tool_input = event.data.get("tool_input", {})
        tool_brief = event.data.get("tool_brief", tool_name)

        # 简化工具名（去除 mcp__gridcode__ 前缀）
        display_name = _strip_tool_prefix(tool_name)

        text = Text()
        # 注意：decision_hint 现在在 on_event() 中单独打印到历史，
        # 因为这里的输出是 transient 的 spinner，完成后会被清除
        text.append(f"{self._get_spinner_char()} ", style=StatusColors.SPINNER)

        if self._verbose:
            # 详细模式：显示工具名和参数
            text.append("调用 ", style=StatusColors.DIM)
            text.append(f"{display_name}", style=StatusColors.TOOL_NAME)

            params_str = self._format_tool_params(tool_input)
            if params_str:
                text.append(f"({params_str})", style=StatusColors.DIM)
        else:
            # 紧凑模式：只显示工具简述
            text.append(f"{tool_brief}...", style=StatusColors.DIM)

        return text

    def _format_tool_call_end(self, event: AgentEvent) -> Text:
        """格式化工具调用完成状态

        Args:
            event: 工具调用完成事件

        Returns:
            格式化的 Text 对象
        """
        tool_name = event.data["tool_name"]
        duration_ms = event.data.get("duration_ms", 0)
        result_count = event.data.get("result_count")
        result_summary = event.data.get("result_summary", "")
        tool_input = event.data.get("tool_input", {})
        thinking_duration_ms = event.data.get("thinking_duration_ms")
        llm_duration_ms = event.data.get("llm_duration_ms")

        # API 调用统计（通过 httpx hooks 精确测量）
        api_duration_ms = event.data.get("api_duration_ms")
        api_call_count = event.data.get("api_call_count")

        # 详细模式新增字段
        result_type = event.data.get("result_type")
        chapter_count = event.data.get("chapter_count")
        page_sources = event.data.get("page_sources", [])
        content_preview = event.data.get("content_preview")

        text = Text()
        text.append(f"{StatusIcons.SUCCESS} ", style=StatusColors.SUCCESS)

        # 获取工具元数据
        meta = get_tool_metadata(tool_name)
        brief = meta.brief if meta else tool_name

        # 简化工具名（去除 mcp__gridcode__ 前缀）
        display_name = _strip_tool_prefix(tool_name)

        if self._verbose:
            # 详细模式：工具名(参数) (思考 Xms, API Yms[/N次], 执行 Zms)
            text.append(f"{display_name}", style=StatusColors.TOOL_NAME)
            if tool_input:
                params_str = _format_params_simple(tool_input)
                text.append(f"({params_str})", style=StatusColors.DIM)

            # 三时间显示：思考时间 + API时间 + 执行时间
            text.append(" (", style=StatusColors.DIM)

            # 思考时间（步骤间总时间）
            if llm_duration_ms is not None:
                text.append(f"思考 {self._format_duration(llm_duration_ms)}", style=StatusColors.THINKING_TIME)
                text.append(", ", style=StatusColors.DIM)
            elif thinking_duration_ms is not None:
                # 兼容：如果没有llm_duration_ms但有thinking_duration_ms
                text.append(f"思考 {self._format_duration(thinking_duration_ms)}", style=StatusColors.THINKING_TIME)
                text.append(", ", style=StatusColors.DIM)

            # API时间（精确的HTTP往返时间）
            if api_duration_ms is not None:
                text.append(f"API {self._format_duration(api_duration_ms)}", style=StatusColors.API_TIME)
                if api_call_count is not None and api_call_count > 1:
                    text.append(f"/{api_call_count}次", style=StatusColors.API_TIME)
                text.append(", ", style=StatusColors.DIM)

            # 执行时间
            text.append(f"执行 {self._format_duration(duration_ms)}", style=StatusColors.EXEC_TIME)
            text.append(")", style=StatusColors.DIM)

            # 详细结果摘要（多行）
            detail_lines = self._format_verbose_result_details(
                result_count=result_count,
                result_type=result_type,
                chapter_count=chapter_count,
                page_sources=page_sources,
                content_preview=content_preview,
            )
            if detail_lines:
                text.append("\n")
                text.append_text(detail_lines)
        else:
            # 紧凑模式
            text.append(f"{brief}", style=StatusColors.SUCCESS)

            # 结果摘要
            if result_count is not None:
                text.append("完成", style=StatusColors.DIM)
                text.append(f"（{result_count}条）", style=StatusColors.DIM)
            elif result_summary:
                text.append(f" {result_summary}", style=StatusColors.DIM)
            else:
                text.append(" 完成", style=StatusColors.SUCCESS)

            # 耗时（紧凑模式只显示 > 1s 的）
            if self._show_duration and duration_ms is not None:
                if duration_ms >= 1000:
                    text.append(f"（{duration_ms/1000:.1f}s）", style=StatusColors.DURATION)
                elif duration_ms > 100:
                    text.append(f"（{duration_ms:.0f}ms）", style=StatusColors.DURATION)

        return text

    def _format_duration(self, ms: float | None) -> str:
        """格式化耗时

        Args:
            ms: 毫秒数

        Returns:
            格式化的时间字符串
        """
        if ms is None:
            return "?"
        if ms >= 1000:
            return f"{ms/1000:.1f}s"
        return f"{ms:.0f}ms"

    def _format_verbose_result_details(
        self,
        result_count: int | None = None,
        result_type: str | None = None,
        chapter_count: int | None = None,
        page_sources: list[int] | None = None,
        content_preview: str | None = None,
    ) -> Text:
        """格式化详细结果摘要（多行）

        Args:
            result_count: 结果数量
            result_type: 结果类型
            chapter_count: 涉及章节数
            page_sources: 来源页码列表
            content_preview: 内容预览

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        indent = "    "

        # 📊 N 条结果 (类型)，涉及 M 个章节
        if result_count is not None or result_type:
            text.append(f"{indent}{StatusIcons.STATS} ", style=StatusColors.DIM)
            if result_count is not None:
                text.append(f"{result_count} 条结果", style=StatusColors.COUNT)
            if result_type:
                text.append(f" ({result_type})", style=StatusColors.RESULT_TYPE)
            if chapter_count and chapter_count > 0:
                text.append(f"，涉及 {chapter_count} 个章节", style=StatusColors.DIM)
            text.append("\n")

        # 📄 来源: P1, P2, P3
        if page_sources:
            pages_str = format_page_sources(page_sources)
            if pages_str:
                text.append(f"{indent}{StatusIcons.PAGES} ", style=StatusColors.DIM)
                text.append(f"来源: {pages_str}", style=StatusColors.PAGE_SOURCE)
                text.append("\n")

        # 📝 内容预览
        if content_preview:
            text.append(f"{indent}{StatusIcons.PREVIEW} ", style=StatusColors.DIM)
            # 截断过长的预览
            preview = content_preview[:80] + "..." if len(content_preview) > 80 else content_preview
            text.append(preview, style=StatusColors.CONTENT_PREVIEW)

        # 移除末尾换行
        if text.plain.endswith("\n"):
            text = Text(text.plain.rstrip("\n"))
            # 重新应用样式（简化处理）

        return text

    def _format_tool_call_error(self, event: AgentEvent) -> Text:
        """格式化工具调用错误状态

        Args:
            event: 工具调用错误事件

        Returns:
            格式化的 Text 对象
        """
        tool_name = event.data["tool_name"]
        error = event.data.get("error", "未知错误")

        text = Text()
        text.append(f"{StatusIcons.ERROR} ", style=StatusColors.ERROR)
        text.append(f"{tool_name} ", style=StatusColors.TOOL_NAME)
        # 截断过长的错误信息
        error_preview = error[:50] + "..." if len(error) > 50 else error
        text.append(f"错误: {error_preview}", style=StatusColors.ERROR)

        return text

    def _format_thinking(self, is_start: bool) -> Text:
        """格式化思考状态

        Args:
            is_start: 是否为开始思考

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        if is_start:
            text.append(f"{self._get_spinner_char()} ", style=StatusColors.SPINNER)
            text.append("思考中...", style=StatusColors.DIM)
        else:
            text.append(f"{StatusIcons.SUCCESS} ", style=StatusColors.SUCCESS)
            text.append("思考完成", style=StatusColors.DIM)
        return text

    def _format_iteration(self, iteration: int) -> Text:
        """格式化迭代轮次

        Args:
            iteration: 迭代次数

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        text.append(f"\n{StatusIcons.SEPARATOR} ", style=StatusColors.DIM)
        text.append(f"第{iteration}轮推理", style=StatusColors.ITERATION)
        text.append(f" {StatusIcons.SEPARATOR}", style=StatusColors.DIM)
        return text

    def _format_summary(self, event: AgentEvent) -> Text:
        """格式化响应完成摘要

        Args:
            event: 响应完成事件

        Returns:
            格式化的 Text 对象
        """
        total_tools = event.data.get("total_tool_calls", 0)
        total_sources = event.data.get("total_sources", 0)
        duration = event.data.get("duration_ms", 0)

        text = Text()
        text.append(f"\n{StatusIcons.INFO} ", style=StatusColors.DIM)
        text.append("统计: ", style="bold")

        # 总耗时
        if duration > 0:
            duration_sec = duration / 1000
            text.append(f"总耗时 {duration_sec:.1f}s", style=StatusColors.DURATION)

        # 思考时间统计（步骤间总时间）
        if self._total_llm_duration_ms > 0:
            llm_sec = self._total_llm_duration_ms / 1000
            text.append(" | ", style=StatusColors.DIM)
            text.append(f"思考 {llm_sec:.1f}s/{self._llm_call_count}次", style=StatusColors.THINKING_TIME)

        # API调用统计（精确的HTTP往返时间）
        if self._total_api_duration_ms > 0:
            api_sec = self._total_api_duration_ms / 1000
            text.append(" | ", style=StatusColors.DIM)
            text.append(f"API {api_sec:.1f}s/{self._total_api_call_count}次", style=StatusColors.API_TIME)

        # 工具调用统计
        if total_tools > 0:
            text.append(" | ", style=StatusColors.DIM)
            text.append(f"工具 {total_tools}次", style=StatusColors.EXEC_TIME)

        # 来源统计
        if total_sources > 0:
            text.append(" | ", style=StatusColors.DIM)
            text.append(f"来源 {total_sources}个", style=StatusColors.PAGE_SOURCE)

        return text

    def _format_thinking_text(self, text_content: str) -> Text:
        """格式化思考文本（流式输出）

        Args:
            text_content: 思考文本内容

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        # 使用更明显的图标和颜色
        text.append(f"{StatusIcons.THINKING} ", style="magenta")
        # 截断过长的文本，但保留更多内容
        preview = text_content[:200] + "..." if len(text_content) > 200 else text_content
        text.append(preview, style=StatusColors.THINKING_TEXT)
        return text

    def _format_phase_change(self, phase: str, description: str) -> Text:
        """格式化阶段变化

        Args:
            phase: 阶段名称
            description: 阶段描述

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        text.append(f"\n{StatusIcons.INFO} ", style=StatusColors.DIM)
        text.append(f"阶段: {phase}", style=StatusColors.ITERATION)
        if description:
            text.append(f" - {description}", style=StatusColors.DIM)
        return text

    def _format_answer_generation_start(self) -> Text:
        """格式化答案生成开始状态

        Returns:
            格式化的 Text 对象
        """
        text = Text()
        text.append(f"{self._get_spinner_char()} ", style=StatusColors.SPINNER)
        text.append("生成最终答案...", style=StatusColors.DIM)
        return text

    def _format_answer_generation_end(self, event: AgentEvent) -> Text:
        """格式化答案生成完成状态

        Args:
            event: 答案生成完成事件

        Returns:
            格式化的 Text 对象
        """
        thinking_duration_ms = event.data.get("thinking_duration_ms")
        api_duration_ms = event.data.get("api_duration_ms")
        api_call_count = event.data.get("api_call_count")

        text = Text()
        text.append(f"{StatusIcons.SUCCESS} ", style=StatusColors.SUCCESS)
        text.append("答案生成", style=StatusColors.SUCCESS)

        # 显示时间信息
        text.append(" (", style=StatusColors.DIM)

        # 思考时间
        if thinking_duration_ms is not None:
            text.append(f"思考 {self._format_duration(thinking_duration_ms)}", style=StatusColors.THINKING_TIME)

        # API时间
        if api_duration_ms is not None:
            if thinking_duration_ms is not None:
                text.append(", ", style=StatusColors.DIM)
            text.append(f"API {self._format_duration(api_duration_ms)}", style=StatusColors.API_TIME)
            if api_call_count is not None and api_call_count > 1:
                text.append(f"/{api_call_count}次", style=StatusColors.API_TIME)

        text.append(")", style=StatusColors.DIM)

        return text

    def _render(self) -> Text:
        """渲染当前状态（只渲染当前状态，不含历史）

        Returns:
            当前状态的显示内容
        """
        # 只渲染当前状态，历史记录已经直接打印到 console
        if self._current_status:
            return self._current_status
        return Text("")

    def _print_to_history(self, item: Text) -> None:
        """将完成的项直接打印到控制台（不通过 Live）

        Args:
            item: 要打印的 Text 对象
        """
        if self._live:
            # 暂停 Live，打印内容，然后恢复
            self._live.console.print(item)
        else:
            self._console.print(item)

    async def on_event(self, event: AgentEvent) -> None:
        """处理事件并更新显示

        Args:
            event: Agent 事件
        """
        if event.event_type == AgentEventType.THINKING_START:
            # 记录查询开始时间
            if self._query_start_time is None:
                self._query_start_time = time.time()
                # 重置思考时间统计
                self._total_llm_duration_ms = 0
                self._llm_call_count = 0
                # 重置API调用统计
                self._total_api_duration_ms = 0
                self._total_api_call_count = 0
            # 记录LLM调用开始时间
            self._llm_call_start_time = time.time()
            self._current_status = self._format_thinking(True)

        elif event.event_type == AgentEventType.THINKING_END:
            # 思考结束，计算LLM调用耗时（如果有开始时间且没有工具调用）
            if self._llm_call_start_time is not None:
                llm_duration = (time.time() - self._llm_call_start_time) * 1000
                self._total_llm_duration_ms += llm_duration
                self._llm_call_count += 1
                self._llm_call_start_time = None
            self._current_status = None

        elif event.event_type == AgentEventType.TOOL_CALL_START:
            # 计算LLM调用耗时（从LLM开始到工具调用开始）
            llm_duration_ms = None
            now = time.time()
            if self._llm_call_start_time is not None:
                llm_duration_ms = (now - self._llm_call_start_time) * 1000
                self._total_llm_duration_ms += llm_duration_ms
                self._llm_call_count += 1
                self._llm_call_start_time = None  # 重置，等待下次THINKING_START

            # 计算思考耗时（从上一工具结束到本工具开始）
            thinking_duration_ms = None
            if self._last_tool_end_time is not None:
                thinking_duration_ms = (now - self._last_tool_end_time) * 1000
            elif self._query_start_time is not None:
                # 第一个工具：从查询开始算起
                thinking_duration_ms = (now - self._query_start_time) * 1000

            # 存储耗时到事件数据（供后续使用）
            event.data["thinking_duration_ms"] = thinking_duration_ms
            event.data["llm_duration_ms"] = llm_duration_ms

            # 记录工具开始时间和耗时
            tool_id = event.data.get("tool_id") or event.data["tool_name"]
            self._tool_start_times[tool_id] = now
            if thinking_duration_ms is not None:
                self._tool_thinking_times[tool_id] = thinking_duration_ms
            if llm_duration_ms is not None:
                self._tool_llm_times[tool_id] = llm_duration_ms

            if self._streaming_text and self._verbose:
                if self._streaming_text != self._last_committed_text:
                    self._print_to_history("\n")
                    self._print_to_history(self._format_thinking_text(self._streaming_text))
                    self._last_committed_text = self._streaming_text
                self._streaming_text = ""
                self._is_streaming = False

            # 如果有决策提示，先打印到历史（因为 spinner 是 transient 的）
            decision_hint = event.data.get("decision_hint")
            if decision_hint and self._verbose:
                hint_text = Text()
                hint_text.append("⚡ ", style="yellow")
                hint_text.append(f"{decision_hint}", style="italic yellow")
                self._print_to_history(hint_text)

            # 更新当前状态（spinner）
            self._current_status = self._format_tool_call_start(event)

        elif event.event_type == AgentEventType.TOOL_CALL_END:
            # 计算执行耗时
            tool_id = event.data.get("tool_id") or event.data["tool_name"]
            start_time = self._tool_start_times.pop(tool_id, None)
            if start_time:
                event.data["duration_ms"] = (time.time() - start_time) * 1000

            # 恢复思考耗时（从 TOOL_CALL_START 保存的）
            thinking_duration_ms = self._tool_thinking_times.pop(tool_id, None)
            if thinking_duration_ms is not None and "thinking_duration_ms" not in event.data:
                event.data["thinking_duration_ms"] = thinking_duration_ms

            # 恢复LLM调用耗时（从 TOOL_CALL_START 保存的）
            llm_duration_ms = self._tool_llm_times.pop(tool_id, None)
            if llm_duration_ms is not None and "llm_duration_ms" not in event.data:
                event.data["llm_duration_ms"] = llm_duration_ms

            # 累计 API 调用统计（来自 httpx hooks 精确测量）
            api_duration_ms = event.data.get("api_duration_ms")
            api_call_count = event.data.get("api_call_count")
            if api_duration_ms is not None:
                self._total_api_duration_ms += api_duration_ms
            if api_call_count is not None:
                self._total_api_call_count += api_call_count

            # 记录工具结束时间，同时作为下一次LLM调用的开始时间
            now = time.time()
            self._last_tool_end_time = now
            self._llm_call_start_time = now  # 工具执行完成后，LLM继续推理

            # 直接打印工具结果（不累积到历史）
            self._print_to_history(self._format_tool_call_end(event))
            self._current_status = None

        elif event.event_type == AgentEventType.TOOL_CALL_ERROR:
            self._print_to_history(self._format_tool_call_error(event))
            self._current_status = None
            now = time.time()
            self._last_tool_end_time = now
            self._llm_call_start_time = now  # 错误后LLM继续推理

        elif event.event_type == AgentEventType.ITERATION_START:
            iteration = event.data.get("iteration", 1)
            self._iteration_count = iteration
            # 只有从第2轮开始才显示迭代标记
            if iteration > 1:
                self._print_to_history(self._format_iteration(iteration))

        elif event.event_type == AgentEventType.TEXT_DELTA:
            # 流式文本增量（仅详细模式）
            # 只累积文本，不更新 Live 显示（避免终端刷新问题导致重复）
            if self._verbose:
                delta = event.data.get("delta", "")
                if delta:
                    self._streaming_text += delta
                    self._is_streaming = True
                    # 不再更新 _current_status，避免 Live 刷新导致重复显示

        elif event.event_type == AgentEventType.THINKING_DELTA:
            # 思考增量（仅详细模式）
            # 只累积文本，不更新 Live 显示
            if self._verbose:
                delta = event.data.get("delta", "")
                if delta:
                    self._streaming_text += delta
                    self._is_streaming = True
                    # 不再更新 _current_status，避免 Live 刷新导致重复显示

        elif event.event_type == AgentEventType.PHASE_CHANGE:
            # 阶段变化（仅详细模式）
            if self._verbose:
                phase = event.data.get("phase", "")
                description = event.data.get("description", "")
                if phase:
                    self._current_phase = phase
                    self._print_to_history(self._format_phase_change(phase, description))

        elif event.event_type == AgentEventType.ANSWER_GENERATION_START:
            # 答案生成开始（仅详细模式显示 spinner）
            if self._verbose:
                self._current_status = self._format_answer_generation_start()

        elif event.event_type == AgentEventType.ANSWER_GENERATION_END:
            # 答案生成完成
            # 累计 API 调用统计
            api_duration_ms = event.data.get("api_duration_ms")
            api_call_count = event.data.get("api_call_count")
            if api_duration_ms is not None:
                self._total_api_duration_ms += api_duration_ms
            if api_call_count is not None:
                self._total_api_call_count += api_call_count

            # 累计思考时间
            thinking_duration_ms = event.data.get("thinking_duration_ms")
            if thinking_duration_ms is not None:
                self._total_llm_duration_ms += thinking_duration_ms
                self._llm_call_count += 1

            # 详细模式下显示答案生成完成状态
            if self._verbose:
                self._print_to_history(self._format_answer_generation_end(event))
            self._current_status = None

        elif event.event_type == AgentEventType.RESPONSE_COMPLETE:
            # 清理流式文本状态（避免重复添加）
            if self._streaming_text and self._verbose:
                if self._streaming_text != self._last_committed_text:
                    self._print_to_history("\n")
                    self._print_to_history(self._format_thinking_text(self._streaming_text))
                    self._last_committed_text = self._streaming_text
                self._streaming_text = ""
                self._is_streaming = False

            # 累加最后一步的 API 统计（生成最终答案时的 LLM 调用）
            final_api_duration_ms = event.data.get("final_api_duration_ms")
            final_api_call_count = event.data.get("final_api_call_count")
            if final_api_duration_ms is not None:
                self._total_api_duration_ms += final_api_duration_ms
            if final_api_call_count is not None:
                self._total_api_call_count += final_api_call_count

            # 只在详细模式下显示摘要
            # 修复：不再限制 total_tools > 0，只要有任何活动（工具调用、LLM调用、API调用）就显示
            if self._verbose:
                total_tools = event.data.get("total_tool_calls", 0)
                # 有工具调用、LLM思考、或API调用时都显示摘要
                has_activity = (
                    total_tools > 0
                    or self._llm_call_count > 0
                    or self._total_api_call_count > 0
                )
                if has_activity:
                    self._print_to_history(self._format_summary(event))

            # 重置查询状态，为下一次查询做准备
            self._query_start_time = None
            self._last_tool_end_time = None
            self._llm_call_start_time = None
            self._total_llm_duration_ms = 0
            self._llm_call_count = 0
            self._total_api_duration_ms = 0
            self._total_api_call_count = 0

        # 更新 Live 显示
        if self._live:
            self._live.update(self._render())

    @asynccontextmanager
    async def live_context(self):
        """Live 显示上下文管理器

        Usage:
            display = AgentStatusDisplay()
            async with display.live_context():
                response = await agent.chat(query)

        Yields:
            self: 当前显示器实例
        """
        from loguru import logger

        # 重置状态
        self._current_status = None
        self._tool_start_times = {}
        self._iteration_count = 0
        self._spinner_frame = 0

        # 重置时间追踪
        self._last_tool_end_time = None
        self._query_start_time = None

        # 重置流式文本状态
        self._streaming_text = ""
        self._is_streaming = False
        self._current_phase = None
        self._last_committed_text = ""

        # 临时禁用 DEBUG 级别日志（避免与显示混杂）
        # 只在详细模式下才禁用，因为详细模式会显示思考内容
        handler_id = None
        if self._verbose:
            # 移除默认 handler，添加一个只显示 WARNING 及以上的 handler
            logger.remove()
            handler_id = logger.add(
                lambda msg: self._console.print(f"[dim]{msg}[/dim]", highlight=False),
                level="WARNING",
                format="{message}",
            )

        try:
            with Live(
                self._render(),
                console=self._console,
                refresh_per_second=10,
                transient=True,  # 只显示当前状态，完成后清除
            ) as live:
                self._live = live
                try:
                    yield self
                finally:
                    self._live = None
        finally:
            # 恢复默认日志配置
            if handler_id is not None:
                logger.remove(handler_id)
                logger.add(
                    lambda msg: print(msg, end=""),
                    level="DEBUG",
                    format="{time:HH:mm:ss} | {level: <8} | {message}",
                )

    def print_final(self) -> None:
        """打印最终状态（非 Live 模式）

        已废弃：现在直接打印到控制台，不再累积历史。
        """
        pass


# ==================== 简单显示类 ====================


class SimpleStatusDisplay(StatusCallback):
    """简单状态显示

    使用 console.print 直接输出，不使用 Live。
    适用于非交互场景或作为降级方案。
    """

    def __init__(
        self,
        console: Console | None = None,
        verbose: bool = False,
    ):
        """初始化简单显示器

        Args:
            console: Rich Console 实例
            verbose: 详细模式
        """
        self._console = console or Console()
        self._verbose = verbose

    async def on_event(self, event: AgentEvent) -> None:
        """处理事件并直接打印

        Args:
            event: Agent 事件
        """
        if event.event_type == AgentEventType.TOOL_CALL_START:
            tool_name = event.data["tool_name"]
            meta = get_tool_metadata(tool_name)
            brief = meta.brief if meta else tool_name

            if self._verbose:
                tool_input = event.data.get("tool_input", {})
                params = _format_params_simple(tool_input)
                self._console.print(f"[cyan]⠋[/cyan] 调用 [bold cyan]{tool_name}[/bold cyan]({params})")
            else:
                self._console.print(f"[cyan]⠋[/cyan] [dim]{brief}...[/dim]")

        elif event.event_type == AgentEventType.TOOL_CALL_END:
            tool_name = event.data["tool_name"]
            count = event.data.get("result_count")

            meta = get_tool_metadata(tool_name)
            brief = meta.brief if meta else tool_name

            if count is not None:
                self._console.print(f"[green]✓[/green] {brief}完成（{count}条）")
            else:
                self._console.print(f"[green]✓[/green] {brief}完成")

        elif event.event_type == AgentEventType.TOOL_CALL_ERROR:
            tool_name = event.data["tool_name"]
            error = event.data.get("error", "")[:50]
            self._console.print(f"[red]✗[/red] {tool_name}: {error}")

        elif event.event_type == AgentEventType.ITERATION_START:
            iteration = event.data.get("iteration", 1)
            if iteration > 1:
                self._console.print(f"\n[dim]──[/dim] [bold yellow]第{iteration}轮推理[/bold yellow] [dim]──[/dim]")


def _format_params_simple(params: dict[str, Any], max_len: int = 60) -> str:
    """简单格式化参数

    Args:
        params: 参数字典
        max_len: 最大长度

    Returns:
        格式化的参数字符串
    """
    if not params:
        return ""

    parts = []
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str):
            if len(value) > 20:
                value = value[:20] + "..."
            parts.append(f'{key}="{value}"')
        elif isinstance(value, bool):
            parts.append(f"{key}={str(value).lower()}")
        else:
            parts.append(f"{key}={value}")

    result = ", ".join(parts)
    if len(result) > max_len:
        result = result[:max_len] + "..."
    return result


def _strip_tool_prefix(tool_name: str) -> str:
    """去除工具名称的 MCP 前缀

    将 mcp__gridcode__get_toc 转换为 get_toc

    Args:
        tool_name: 完整工具名称

    Returns:
        简化的工具名称
    """
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return parts[-1]
    return tool_name
