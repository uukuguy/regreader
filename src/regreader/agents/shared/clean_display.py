"""Clean Agent 状态显示模块

简洁的实时状态输出，解决现有显示系统的三个问题：
1. 图标混乱 - 只使用 ✓ ✗ ⚠ → ⠋ 等小巧清晰的符号
2. 缺少底部状态栏 - 固定底部统计区域
3. 布局混乱 - 清晰的三区域布局（历史 70% + 当前 20% + 状态栏 10%）
"""

import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from regreader.agents.shared.callbacks import StatusCallback
from regreader.agents.shared.events import AgentEvent, AgentEventType
from regreader.mcp.tool_metadata import get_tool_metadata


# ==================== 简洁图标系统 ====================


class CleanIcons:
    """简洁图标系统 - 只使用小巧清晰的符号"""

    # 核心状态图标
    SUCCESS = "✓"      # 成功完成
    ERROR = "✗"        # 错误失败
    WARNING = "⚠"      # 警告提示
    ARROW = "→"        # 信息指示

    # 动画图标
    SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    # 层级结构
    TREE_BRANCH = "├─"
    TREE_LAST = "└─"
    INDENT = "  "


# ==================== 显示模式 ====================


class DisplayMode(Enum):
    """显示模式"""
    COMPACT = "compact"    # 紧凑模式 - 只显示关键信息
    VERBOSE = "verbose"    # 详细模式 - 显示完整参数和结果
    QUIET = "quiet"        # 静默模式 - 不显示任何信息


# ==================== 历史记录 ====================


@dataclass
class HistoryRecord:
    """历史记录条目"""
    description: str           # 操作描述
    icon: str                  # 图标（✓/✗/⚠）
    duration_ms: float         # 执行耗时（毫秒）
    timestamp: datetime        # 时间戳
    details: list[str]         # 详细信息（多行）
    thinking_time_ms: float | None = None   # 思考耗时
    api_time_ms: float | None = None        # API耗时
    api_call_count: int | None = None       # API调用次数


class HistoryManager:
    """历史记录管理器"""

    def __init__(self, max_size: int = 50):
        """初始化历史管理器

        Args:
            max_size: 最大保留记录数
        """
        self._records: deque[HistoryRecord] = deque(maxlen=max_size)

    def add(self, record: HistoryRecord) -> None:
        """添加记录

        Args:
            record: 历史记录
        """
        self._records.append(record)

    def get_all(self) -> list[HistoryRecord]:
        """获取所有记录

        Returns:
            记录列表（最新的在最后）
        """
        return list(self._records)

    def clear(self) -> None:
        """清空所有记录"""
        self._records.clear()

    def get_recent(self, n: int = 10) -> list[HistoryRecord]:
        """获取最近的 N 条记录

        Args:
            n: 记录数量

        Returns:
            最近的记录列表
        """
        return list(self._records)[-n:] if len(self._records) > n else list(self._records)


# ==================== 状态栏统计 ====================


@dataclass
class StatusBarStats:
    """状态栏统计数据"""
    total_tools: int = 0           # 工具调用次数
    total_thinking_ms: float = 0   # 总思考时间
    total_api_ms: float = 0        # 总API时间
    total_sources: int = 0         # 来源数量
    thinking_count: int = 0        # 思考次数
    api_call_count: int = 0        # API调用次数

    def format(self) -> str:
        """格式化为状态栏字符串

        Returns:
            格式化的统计字符串
        """
        parts = []

        if self.total_tools > 0:
            parts.append(f"工具: {self.total_tools}次")

        if self.total_thinking_ms > 0:
            thinking_sec = self.total_thinking_ms / 1000
            parts.append(f"思考: {thinking_sec:.1f}s/{self.thinking_count}次")

        if self.total_api_ms > 0:
            api_sec = self.total_api_ms / 1000
            parts.append(f"API: {api_sec:.1f}s/{self.api_call_count}次")

        if self.total_sources > 0:
            parts.append(f"来源: {self.total_sources}个")

        return " | ".join(parts) if parts else "准备就绪"


# ==================== 时间追踪 ====================


class TimeTracker:
    """时间追踪器 - 追踪思考/API/执行三层时间"""

    def __init__(self):
        """初始化时间追踪器"""
        # 工具级别追踪
        self._tool_start_times: dict[str, float] = {}
        self._tool_thinking_times: dict[str, float] = {}
        self._tool_api_times: dict[str, float] = {}

        # 会话级别追踪
        self._query_start_time: float | None = None
        self._last_tool_end_time: float | None = None
        self._llm_call_start_time: float | None = None

        # 累计统计
        self._total_thinking_ms: float = 0
        self._total_api_ms: float = 0
        self._thinking_count: int = 0
        self._api_call_count: int = 0

    def start_query(self) -> None:
        """开始查询"""
        self._query_start_time = time.time()
        self._last_tool_end_time = None
        self._llm_call_start_time = None
        self._total_thinking_ms = 0
        self._total_api_ms = 0
        self._thinking_count = 0
        self._api_call_count = 0

    def start_thinking(self) -> None:
        """开始思考（LLM调用）"""
        self._llm_call_start_time = time.time()

    def end_thinking(self) -> float | None:
        """结束思考，返回耗时

        Returns:
            思考耗时（毫秒），如果没有开始时间则返回 None
        """
        if self._llm_call_start_time is None:
            return None

        duration_ms = (time.time() - self._llm_call_start_time) * 1000
        self._total_thinking_ms += duration_ms
        self._thinking_count += 1
        self._llm_call_start_time = None
        return duration_ms

    def start_tool(self, tool_id: str) -> tuple[float | None, float | None]:
        """开始工具调用，返回思考耗时和LLM耗时

        Args:
            tool_id: 工具ID

        Returns:
            (思考耗时, LLM耗时) 的元组
        """
        now = time.time()
        self._tool_start_times[tool_id] = now

        # 计算LLM调用耗时（从LLM开始到工具开始）
        llm_duration_ms = None
        if self._llm_call_start_time is not None:
            llm_duration_ms = (now - self._llm_call_start_time) * 1000
            self._total_thinking_ms += llm_duration_ms
            self._thinking_count += 1
            self._llm_call_start_time = None

        # 计算思考耗时（从上一工具结束到本工具开始）
        thinking_duration_ms = None
        if self._last_tool_end_time is not None:
            thinking_duration_ms = (now - self._last_tool_end_time) * 1000
        elif self._query_start_time is not None:
            thinking_duration_ms = (now - self._query_start_time) * 1000

        # 保存耗时供后续使用
        if thinking_duration_ms is not None:
            self._tool_thinking_times[tool_id] = thinking_duration_ms
        if llm_duration_ms is not None:
            self._tool_api_times[tool_id] = llm_duration_ms

        return thinking_duration_ms, llm_duration_ms

    def end_tool(self, tool_id: str) -> float:
        """结束工具调用，返回执行耗时

        Args:
            tool_id: 工具ID

        Returns:
            执行耗时（毫秒）
        """
        start_time = self._tool_start_times.pop(tool_id, None)
        if start_time is None:
            return 0

        now = time.time()
        duration_ms = (now - start_time) * 1000

        # 记录工具结束时间，作为下一次LLM调用的开始时间
        self._last_tool_end_time = now
        self._llm_call_start_time = now

        return duration_ms

    def record_api_call(self, duration_ms: float, call_count: int = 1) -> None:
        """记录API调用统计

        Args:
            duration_ms: API耗时
            call_count: 调用次数
        """
        self._total_api_ms += duration_ms
        self._api_call_count += call_count

    def get_stats(self) -> tuple[float, int, float, int]:
        """获取累计统计

        Returns:
            (总思考时间, 思考次数, 总API时间, API调用次数)
        """
        return (
            self._total_thinking_ms,
            self._thinking_count,
            self._total_api_ms,
            self._api_call_count,
        )

    def get_tool_times(self, tool_id: str) -> tuple[float | None, float | None]:
        """获取工具的思考和API耗时

        Args:
            tool_id: 工具ID

        Returns:
            (思考耗时, API耗时)
        """
        thinking_time = self._tool_thinking_times.pop(tool_id, None)
        api_time = self._tool_api_times.pop(tool_id, None)
        return thinking_time, api_time


# ==================== 三区域布局 ====================


class CleanLayout:
    """三区域布局管理器

    布局结构：
    ┌─────────────────────────────────────────────────┐
    │              历史区 (History)                    │
    │              70% 高度                            │
    ├─────────────────────────────────────────────────┤
    │              当前区 (Current)                    │
    │              20% 高度                            │
    ├─────────────────────────────────────────────────┤
    │              状态栏 (Status Bar)                 │
    │              10% 高度                            │
    └─────────────────────────────────────────────────┘
    """

    def __init__(self):
        """初始化布局"""
        self._layout = Layout()
        self._layout.split_column(
            Layout(name="history", ratio=7),
            Layout(name="current", ratio=2),
            Layout(name="status", ratio=1),
        )

    def update_history(self, content: Any) -> None:
        """更新历史区

        Args:
            content: Rich 可渲染对象（Text, Panel, Table等）
        """
        self._layout["history"].update(content)

    def update_current(self, content: Any) -> None:
        """更新当前区

        Args:
            content: Rich 可渲染对象
        """
        self._layout["current"].update(content)

    def update_status(self, content: Any) -> None:
        """更新状态栏

        Args:
            content: Rich 可渲染对象
        """
        self._layout["status"].update(content)

    def get_layout(self) -> Layout:
        """获取 Rich Layout 对象

        Returns:
            Layout 对象
        """
        return self._layout


# ==================== 主显示器类 ====================


class CleanAgentStatusDisplay(StatusCallback):
    """简洁的 Agent 状态显示器

    解决现有显示系统的三个问题：
    1. 图标混乱 - 只使用 ✓ ✗ ⚠ → ⠋
    2. 缺少底部状态栏 - 固定底部统计区域
    3. 布局混乱 - 清晰的三区域布局

    显示效果示例（紧凑模式）：
    ┌─────────────────────────────────────────────────┐
    │ 执行历史                                         │
    │ ✓ 获取目录结构 (1.2s)                           │
    │   ├─ 12 条结果                                   │
    │   └─ 第1章 总则, 第2章 运行管理...              │
    ├─────────────────────────────────────────────────┤
    │ 当前操作                                         │
    │ ⠋ 正在调用 read_page_range...                   │
    ├─────────────────────────────────────────────────┤
    │ 工具: 3次 | 思考: 5.1s | API: 4.8s | 来源: 6个  │
    └─────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        console: Console | None = None,
        mode: DisplayMode = DisplayMode.COMPACT,
    ):
        """初始化显示器

        Args:
            console: Rich Console 实例
            mode: 显示模式
        """
        self._console = console or Console()
        self._mode = mode

        # 核心组件
        self._layout = CleanLayout()
        self._history = HistoryManager(max_size=50)
        self._time_tracker = TimeTracker()
        self._stats = StatusBarStats()

        # 当前状态
        self._current_operation: str | None = None
        self._spinner_frame: int = 0

        # Live 实例
        self._live: Live | None = None

    def _get_spinner_char(self) -> str:
        """获取当前 spinner 字符"""
        char = CleanIcons.SPINNER[self._spinner_frame]
        self._spinner_frame = (self._spinner_frame + 1) % len(CleanIcons.SPINNER)
        return char

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

    def _strip_tool_prefix(self, tool_name: str) -> str:
        """去除工具名称的 MCP 前缀

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

    def _render_history(self) -> Panel:
        """渲染历史区

        Returns:
            包含历史记录的 Panel
        """
        records = self._history.get_all()
        if not records:
            return Panel("等待操作...", title="执行历史", border_style="dim")

        content = Text()
        for record in records:
            # 主行：图标 + 描述 + 耗时
            content.append(f"{record.icon} ", style="green" if record.icon == CleanIcons.SUCCESS else "red")
            content.append(f"{record.description} ", style="white")

            # 时间信息
            if record.thinking_time_ms or record.api_time_ms:
                content.append("(", style="dim")
                time_parts = []
                if record.thinking_time_ms:
                    time_parts.append(f"思考 {self._format_duration(record.thinking_time_ms)}")
                if record.api_time_ms:
                    api_str = f"API {self._format_duration(record.api_time_ms)}"
                    if record.api_call_count and record.api_call_count > 1:
                        api_str += f"/{record.api_call_count}次"
                    time_parts.append(api_str)
                time_parts.append(f"执行 {self._format_duration(record.duration_ms)}")
                content.append(", ".join(time_parts), style="cyan")
                content.append(")", style="dim")
            else:
                content.append(f"({self._format_duration(record.duration_ms)})", style="dim")

            content.append("\n")

            # 详细信息
            for i, detail in enumerate(record.details):
                is_last = i == len(record.details) - 1
                prefix = CleanIcons.TREE_LAST if is_last else CleanIcons.TREE_BRANCH
                content.append(f"{CleanIcons.INDENT}{prefix} {detail}\n", style="dim")

        return Panel(content, title="执行历史", border_style="cyan")

    def _render_current(self) -> Panel:
        """渲染当前区

        Returns:
            包含当前操作的 Panel
        """
        if self._current_operation:
            content = Text()
            content.append(f"{self._get_spinner_char()} ", style="cyan")
            content.append(self._current_operation, style="white")
            return Panel(content, title="当前操作", border_style="yellow")
        else:
            return Panel("空闲", title="当前操作", border_style="dim")

    def _render_status_bar(self) -> Panel:
        """渲染状态栏

        Returns:
            包含统计信息的 Panel
        """
        stats_text = self._stats.format()
        return Panel(
            Text(stats_text, style="bold green"),
            border_style="green",
            padding=(0, 1),
        )

    def _refresh_display(self) -> None:
        """刷新显示"""
        if self._live:
            self._layout.update_history(self._render_history())
            self._layout.update_current(self._render_current())
            self._layout.update_status_bar(self._render_status_bar())
            self._live.update(self._layout.get_layout())

    # ==================== 事件处理方法 ====================

    def _handle_thinking_start(self, event: AgentEvent) -> None:
        """处理思考开始事件"""
        self._time_tracker.start_thinking()
        self._current_operation = "思考中..."

    def _handle_thinking_end(self, event: AgentEvent) -> None:
        """处理思考结束事件"""
        self._time_tracker.end_thinking()
        self._current_operation = None

    def _handle_tool_start(self, event: AgentEvent) -> None:
        """处理工具调用开始事件"""
        tool_name = event.data["tool_name"]
        tool_brief = event.data.get("tool_brief", tool_name)
        tool_id = event.data.get("tool_id") or tool_name

        # 开始追踪时间
        thinking_time, llm_time = self._time_tracker.start_tool(tool_id)

        # 更新当前操作
        display_name = self._strip_tool_prefix(tool_name)
        if self._mode == DisplayMode.VERBOSE:
            tool_input = event.data.get("tool_input", {})
            params = self._format_params(tool_input)
            self._current_operation = f"正在调用 {display_name}({params})..."
        else:
            self._current_operation = f"正在{tool_brief}..."

    def _handle_tool_end(self, event: AgentEvent) -> None:
        """处理工具调用完成事件"""
        tool_name = event.data["tool_name"]
        tool_id = event.data.get("tool_id") or tool_name

        # 获取时间信息
        exec_time = self._time_tracker.end_tool(tool_id)
        thinking_time, llm_time = self._time_tracker.get_tool_times(tool_id)

        # 获取API统计
        api_duration_ms = event.data.get("api_duration_ms")
        api_call_count = event.data.get("api_call_count")
        if api_duration_ms:
            self._time_tracker.record_api_call(api_duration_ms, api_call_count or 1)

        # 获取工具元数据
        meta = get_tool_metadata(tool_name)
        brief = meta.brief if meta else self._strip_tool_prefix(tool_name)

        # 构建详细信息
        details = []
        result_count = event.data.get("result_count")
        result_type = event.data.get("result_type")
        chapter_count = event.data.get("chapter_count")

        if result_count is not None:
            result_str = f"{result_count} 条结果"
            if result_type:
                result_str += f" ({result_type})"
            if chapter_count and chapter_count > 0:
                result_str += f"，涉及 {chapter_count} 个章节"
            details.append(result_str)

        # 页面来源
        page_sources = event.data.get("page_sources", [])
        if page_sources:
            pages_str = ", ".join(f"P{p}" for p in sorted(set(page_sources))[:10])
            if len(page_sources) > 10:
                pages_str += "..."
            details.append(f"来源: {pages_str}")

        # 内容预览
        content_preview = event.data.get("content_preview")
        if content_preview:
            preview = content_preview[:60] + "..." if len(content_preview) > 60 else content_preview
            details.append(preview)

        # 添加到历史
        record = HistoryRecord(
            description=brief,
            icon=CleanIcons.SUCCESS,
            duration_ms=exec_time,
            timestamp=datetime.now(),
            details=details,
            thinking_time_ms=llm_time,
            api_time_ms=api_duration_ms,
            api_call_count=api_call_count,
        )
        self._history.add(record)

        # 更新统计
        self._stats.total_tools += 1
        if page_sources:
            self._stats.total_sources += len(set(page_sources))

        # 清除当前操作
        self._current_operation = None

    def _handle_tool_error(self, event: AgentEvent) -> None:
        """处理工具调用错误事件"""
        tool_name = event.data["tool_name"]
        error = event.data.get("error", "未知错误")

        # 获取工具元数据
        meta = get_tool_metadata(tool_name)
        brief = meta.brief if meta else self._strip_tool_prefix(tool_name)

        # 截断错误信息
        error_preview = error[:80] + "..." if len(error) > 80 else error

        # 添加到历史
        record = HistoryRecord(
            description=brief,
            icon=CleanIcons.ERROR,
            duration_ms=0,
            timestamp=datetime.now(),
            details=[f"错误: {error_preview}"],
        )
        self._history.add(record)

        # 清除当前操作
        self._current_operation = None

    def _handle_iteration_start(self, event: AgentEvent) -> None:
        """处理迭代开始事件"""
        iteration = event.data.get("iteration", 1)
        # 只有从第2轮开始才显示迭代标记
        if iteration > 1:
            record = HistoryRecord(
                description=f"第{iteration}轮推理",
                icon=CleanIcons.ARROW,
                duration_ms=0,
                timestamp=datetime.now(),
                details=[],
            )
            self._history.add(record)

    def _handle_text_delta(self, event: AgentEvent) -> None:
        """处理文本增量事件"""
        # 流式文本输出 - 暂不处理，避免频繁刷新
        pass

    def _handle_thinking_delta(self, event: AgentEvent) -> None:
        """处理思考增量事件"""
        # 思考增量 - 暂不处理，避免频繁刷新
        pass

    def _handle_phase_change(self, event: AgentEvent) -> None:
        """处理阶段变化事件"""
        phase = event.data.get("phase", "")
        description = event.data.get("description", "")
        if phase:
            record = HistoryRecord(
                description=f"阶段: {phase}",
                icon=CleanIcons.ARROW,
                duration_ms=0,
                timestamp=datetime.now(),
                details=[description] if description else [],
            )
            self._history.add(record)

    def _handle_answer_start(self, event: AgentEvent) -> None:
        """处理答案生成开始事件"""
        if self._mode == DisplayMode.VERBOSE:
            self._current_operation = "生成最终答案..."

    def _handle_answer_end(self, event: AgentEvent) -> None:
        """处理答案生成完成事件"""
        # 累计API统计
        api_duration_ms = event.data.get("api_duration_ms")
        api_call_count = event.data.get("api_call_count")
        if api_duration_ms:
            self._time_tracker.record_api_call(api_duration_ms, api_call_count or 1)

        # 累计思考时间
        thinking_duration_ms = event.data.get("thinking_duration_ms")
        if thinking_duration_ms:
            self._stats.total_thinking_ms += thinking_duration_ms
            self._stats.thinking_count += 1

        # 详细模式下显示答案生成完成
        if self._mode == DisplayMode.VERBOSE:
            record = HistoryRecord(
                description="答案生成",
                icon=CleanIcons.SUCCESS,
                duration_ms=0,
                timestamp=datetime.now(),
                details=[],
                thinking_time_ms=thinking_duration_ms,
                api_time_ms=api_duration_ms,
                api_call_count=api_call_count,
            )
            self._history.add(record)

        self._current_operation = None

    def _handle_response_complete(self, event: AgentEvent) -> None:
        """处理响应完成事件"""
        # 更新最终统计
        thinking_ms, thinking_count, api_ms, api_count = self._time_tracker.get_stats()
        self._stats.total_thinking_ms = thinking_ms
        self._stats.thinking_count = thinking_count
        self._stats.total_api_ms = api_ms
        self._stats.api_call_count = api_count

        # 清除当前操作
        self._current_operation = None

    def _format_params(self, params: dict[str, Any]) -> str:
        """格式化工具参数

        Args:
            params: 参数字典

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
        if len(result) > 60:
            result = result[:60] + "..."
        return result

    async def on_event(self, event: AgentEvent) -> None:
        """处理事件并更新显示

        Args:
            event: Agent 事件
        """
        # 静默模式不显示任何内容
        if self._mode == DisplayMode.QUIET:
            return

        # 思考阶段
        if event.event_type == AgentEventType.THINKING_START:
            self._handle_thinking_start(event)
        elif event.event_type == AgentEventType.THINKING_END:
            self._handle_thinking_end(event)

        # 工具调用阶段
        elif event.event_type == AgentEventType.TOOL_CALL_START:
            self._handle_tool_start(event)
        elif event.event_type == AgentEventType.TOOL_CALL_END:
            self._handle_tool_end(event)
        elif event.event_type == AgentEventType.TOOL_CALL_ERROR:
            self._handle_tool_error(event)

        # 迭代阶段
        elif event.event_type == AgentEventType.ITERATION_START:
            self._handle_iteration_start(event)

        # 流式输出阶段
        elif event.event_type == AgentEventType.TEXT_DELTA:
            self._handle_text_delta(event)
        elif event.event_type == AgentEventType.THINKING_DELTA:
            self._handle_thinking_delta(event)
        elif event.event_type == AgentEventType.PHASE_CHANGE:
            self._handle_phase_change(event)

        # 答案生成阶段
        elif event.event_type == AgentEventType.ANSWER_GENERATION_START:
            self._handle_answer_start(event)
        elif event.event_type == AgentEventType.ANSWER_GENERATION_END:
            self._handle_answer_end(event)

        # 结果阶段
        elif event.event_type == AgentEventType.RESPONSE_COMPLETE:
            self._handle_response_complete(event)

        # 刷新显示
        self._refresh_display()

    @asynccontextmanager
    async def live_context(self):
        """Live 显示上下文管理器

        Usage:
            display = CleanAgentStatusDisplay()
            async with display.live_context():
                response = await agent.chat(query)

        Yields:
            self: 当前显示器实例
        """
        # 重置状态
        self._history.clear()
        self._time_tracker = TimeTracker()
        self._stats = StatusBarStats()
        self._current_operation = None
        self._spinner_frame = 0

        try:
            with Live(
                self._layout.get_layout(),
                console=self._console,
                refresh_per_second=10,
                transient=False,
            ) as live:
                self._live = live
                try:
                    yield self
                finally:
                    self._live = None
        finally:
            pass
