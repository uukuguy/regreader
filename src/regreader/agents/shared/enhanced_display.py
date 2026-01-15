"""增强版 CLI 显示组件

本模块提供与 Claude Code 同等水平的精致 CLI 界面，包括：
- 历史记录流式输出（向上滚动）
- 当前操作 Live 更新（底部显示）
- 无边框设计（简洁输出）
- 自适应返回值显示（auto/summary/full）
"""

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.table import Table


class DisplayState(Enum):
    """显示状态枚举"""

    IDLE = "idle"
    ANALYZING = "analyzing"
    TOOL_CALLING = "tool_calling"
    THINKING = "thinking"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class StepRecord:
    """步骤记录

    记录单个执行步骤的完整信息，用于历史记录显示。

    Attributes:
        step_number: 步骤编号（从 1 开始）
        description: 步骤描述
        state: 当前状态
        start_time: 开始时间
        end_time: 结束时间（可选）
        duration: 执行时长（秒）
        depth: 嵌套深度（0 为顶层）
        parent_step: 父步骤编号（可选）
        metadata: 额外元数据
        result_summary: 结果摘要（可选）
    """

    step_number: int
    description: str
    state: DisplayState
    start_time: datetime
    end_time: datetime | None = None
    duration: float | None = None
    depth: int = 0
    parent_step: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    result_summary: str | None = None

    def is_completed(self) -> bool:
        """是否已完成"""
        return self.state in (DisplayState.COMPLETED, DisplayState.ERROR)

    def get_icon(self) -> str:
        """获取状态图标"""
        icons = {
            DisplayState.IDLE: "⏳",
            DisplayState.ANALYZING: "🔍",
            DisplayState.TOOL_CALLING: "🔧",
            DisplayState.THINKING: "💭",
            DisplayState.AGGREGATING: "📊",
            DisplayState.COMPLETED: "✓",
            DisplayState.ERROR: "✗",
        }
        return icons.get(self.state, "•")

    def get_color(self) -> str:
        """获取状态颜色"""
        colors = {
            DisplayState.IDLE: "dim",
            DisplayState.ANALYZING: "cyan",
            DisplayState.TOOL_CALLING: "magenta",
            DisplayState.THINKING: "cyan",
            DisplayState.AGGREGATING: "blue",
            DisplayState.COMPLETED: "green",
            DisplayState.ERROR: "red",
        }
        return colors.get(self.state, "white")


class HistoryManager:
    """历史记录管理器

    管理执行步骤的历史记录，支持：
    - 固定大小的滚动窗口（避免内存溢出）
    - 树状结构层级关系
    - Rich Table 渲染
    """

    def __init__(self, max_size: int = 50):
        """初始化历史记录管理器

        Args:
            max_size: 最大历史记录数量（默认 50）
        """
        self._history: deque[StepRecord] = deque(maxlen=max_size)
        self._current_step_number: int = 0
        self._depth_stack: list[int] = []  # 用于追踪嵌套深度

    def add_step(
        self,
        description: str,
        state: DisplayState = DisplayState.IDLE,
        metadata: dict[str, Any] | None = None,
    ) -> StepRecord:
        """添加新步骤到历史记录

        Args:
            description: 步骤描述
            state: 初始状态
            metadata: 额外元数据

        Returns:
            新创建的步骤记录
        """
        self._current_step_number += 1
        current_depth = len(self._depth_stack)
        parent_step = self._depth_stack[-1] if self._depth_stack else None

        step = StepRecord(
            step_number=self._current_step_number,
            description=description,
            state=state,
            start_time=datetime.now(),
            depth=current_depth,
            parent_step=parent_step,
            metadata=metadata or {},
        )

        self._history.append(step)
        return step

    def update_step(
        self,
        step: StepRecord,
        state: DisplayState | None = None,
        result_summary: str | None = None,
    ) -> None:
        """更新步骤状态

        Args:
            step: 要更新的步骤
            state: 新状态（可选）
            result_summary: 结果摘要（可选）
        """
        if state is not None:
            step.state = state

        if result_summary is not None:
            step.result_summary = result_summary

        if step.is_completed() and step.end_time is None:
            step.end_time = datetime.now()
            step.duration = (step.end_time - step.start_time).total_seconds()

    def enter_context(self, step: StepRecord) -> None:
        """进入子上下文（增加嵌套深度）

        Args:
            step: 父步骤
        """
        self._depth_stack.append(step.step_number)

    def exit_context(self) -> None:
        """退出子上下文（减少嵌套深度）"""
        if self._depth_stack:
            self._depth_stack.pop()

    def render(self) -> Table:
        """渲染历史记录为 Rich Table

        Returns:
            Rich Table 对象
        """
        table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        table.add_column("content", no_wrap=False)

        for step in self._history:
            formatted_step = self._format_step(step)
            table.add_row(formatted_step)

        return table

    def _format_step(self, step: StepRecord) -> str:
        """格式化单个步骤

        Args:
            step: 步骤记录

        Returns:
            格式化后的字符串
        """
        # 缩进前缀
        indent = "  " * step.depth

        # 树状结构字符
        tree_char = "└─" if step.is_completed() else "├─"
        if step.depth == 0:
            tree_char = ""

        # 图标和颜色
        icon = step.get_icon()
        color = step.get_color()

        # 时长显示
        duration_str = ""
        if step.duration is not None:
            duration_str = f" ({step.duration:.1f}s)"

        # 基础行
        base_line = (
            f"{indent}{tree_char} [{color}]{icon} {step.description}[/{color}]{duration_str}"
        )

        # 结果摘要（如果有）
        if step.result_summary:
            summary_indent = "  " * (step.depth + 1)
            summary_line = f"\n{summary_indent}└─ {step.result_summary}"
            return base_line + summary_line

        return base_line

    def get_current_depth(self) -> int:
        """获取当前嵌套深度"""
        return len(self._depth_stack)

    def clear(self) -> None:
        """清空历史记录"""
        self._history.clear()
        self._current_step_number = 0
        self._depth_stack.clear()


class HybridDisplay:
    """混合显示管理器

    历史记录使用流式输出，当前操作使用 Live 更新。
    """

    def __init__(self, console: Console, detail_mode: str = "auto"):
        """初始化混合显示管理器

        Args:
            console: Rich Console 实例
            detail_mode: 返回值显示详细程度（auto/summary/full）
        """
        self._console = console
        self._detail_mode = detail_mode
        self._live: Live | None = None
        self._current_content: str = ""

    def print_completed_step(self, step: StepRecord) -> None:
        """输出已完成的步骤（流式输出，不可变）

        Args:
            step: 已完成的步骤记录
        """
        icon = step.get_icon()
        color = step.get_color()
        duration = f" ({step.duration:.1f}s)" if step.duration else ""

        # 输出主行
        self._console.print(f"[{color}]{icon} {step.description}{duration}[/{color}]")

        # 输出返回值（如果有）
        if step.result_summary:
            # 根据 detail_mode 决定显示内容
            summary = self._format_summary(step.result_summary)
            self._console.print(f"  [dim]└─ {summary}[/dim]")

    def update_current_step(self, step: StepRecord, spinner: str) -> None:
        """更新当前正在执行的步骤（Live 更新）

        Args:
            step: 当前步骤记录
            spinner: Spinner 字符
        """
        icon = step.get_icon()
        color = step.get_color()
        elapsed = (datetime.now() - step.start_time).total_seconds()

        # 构建当前内容
        self._current_content = (
            f"[{color}]{spinner} {icon} {step.description}[/{color}] "
            f"([dim]{elapsed:.1f}s[/dim])"
        )

        # 更新 Live 显示
        if self._live:
            self._live.update(self._current_content)

    def clear_current(self) -> None:
        """清空当前操作显示"""
        self._current_content = ""
        if self._live:
            self._live.update("")

    def print_status_bar(self, stats: dict[str, Any], final: bool = False) -> None:
        """打印状态栏（无边框）

        Args:
            stats: 统计信息字典
            final: 是否为最终状态栏（只有最终状态栏才会打印）
        """
        # 只在最终状态时打印，避免中间状态栏滚动
        if not final:
            return

        # 分隔线
        self._console.print(f"\n[dim]{'─' * 60}[/dim]")

        # 状态信息
        parts = [
            f"[cyan]工具调用:[/cyan] {stats['tool_calls']}",
            f"[cyan]总耗时:[/cyan] {stats['elapsed']:.1f}s",
        ]

        if stats['tool_calls'] > 0 and stats.get('avg_duration', 0) > 0:
            parts.append(f"[cyan]平均:[/cyan] {stats['avg_duration']:.2f}s")

        self._console.print(" | ".join(parts))

    def _format_summary(self, summary: str) -> str:
        """根据 detail_mode 格式化摘要

        Args:
            summary: 原始摘要字符串

        Returns:
            格式化后的摘要
        """
        if self._detail_mode == "full":
            return summary  # 显示完整内容

        if self._detail_mode == "summary":
            # 强制显示摘要（截断长内容）
            return summary[:100] + "..." if len(summary) > 100 else summary

        # auto 模式：自适应
        if len(summary) <= 100:
            return summary  # 短内容显示完整
        else:
            # 长内容显示摘要
            return summary[:100] + "..."

    def start_live(self) -> None:
        """启动 Live 上下文"""
        self._live = Live(
            self._current_content,
            console=self._console,
            refresh_per_second=10,
            transient=False,
        )
        self._live.start()

    def stop_live(self) -> None:
        """停止 Live 上下文"""
        if self._live:
            self._live.stop()
            self._live = None


class EnhancedAgentStatusDisplay:
    """增强版 Agent 状态显示器（混合模式）

    实现 StatusCallback 协议，提供：
    - 历史记录流式输出（Console.print）
    - 当前操作 Live 更新
    - 状态栏无边框，固定底部

    使用方式：
        display = EnhancedAgentStatusDisplay(console, verbose=True, detail_mode="auto")
        async with display.live_context():
            await display.on_event(event)
    """

    def __init__(
        self,
        console: Console | None = None,
        verbose: bool = False,
        history_size: int = 50,
        detail_mode: str = "auto",
    ):
        """初始化增强版状态显示器

        Args:
            console: Rich Console 实例
            verbose: 详细模式
            history_size: 历史记录最大数量
            detail_mode: 返回值显示详细程度（auto/summary/full）
        """
        self._console = console or Console()
        self._verbose = verbose
        self._detail_mode = detail_mode

        # 核心组件
        self._history = HistoryManager(max_size=history_size)
        self._display = HybridDisplay(self._console, detail_mode)

        # 状态追踪
        self._current_step: StepRecord | None = None
        self._spinner_frame: int = 0
        self._thinking_content: str = ""  # 思考内容累积

        # 统计信息
        self._stats = {
            "tool_calls": 0,
            "total_duration": 0.0,
            "start_time": None,
        }

    async def on_event(self, event: "AgentEvent") -> None:
        """实现 StatusCallback 协议的事件处理方法

        Args:
            event: Agent 事件
        """
        # DEBUG: 添加调试日志
        from loguru import logger

        from regreader.agents.shared.events import AgentEventType

        logger.debug(
            f"[EnhancedAgentStatusDisplay.on_event] 收到事件: {event.event_type}, 实例 ID: {id(self)}"
        )

        event_type = event.event_type

        # 根据事件类型调用相应的处理方法
        if event_type == AgentEventType.THINKING_START:
            # 将 THINKING_START 视为查询开始
            query = event.data.get("query", "")
            if query:
                self.on_query_start(query)
            else:
                self.on_thinking_start("思考中")
        elif event_type == AgentEventType.TOOL_CALL_START:
            self.on_tool_call_start(
                event.data.get("tool_name", ""),
                event.data.get("arguments", {}),
            )
        elif event_type == AgentEventType.TOOL_CALL_END:
            # 从事件数据中提取结果信息
            # 注意：hooks 已经生成了 result_summary，直接使用
            duration_ms = event.data.get("duration_ms", 0)
            duration_sec = duration_ms / 1000 if duration_ms else None

            self.on_tool_call_end(
                event.data.get("tool_name", ""),
                event.data.get("result_summary", ""),  # 使用 hooks 生成的摘要
                duration_sec,
            )
        elif event_type == AgentEventType.TOOL_CALL_ERROR:
            self.on_error(event.data.get("error", "工具调用失败"))
        elif event_type == AgentEventType.THINKING_END:
            self.on_thinking_end()
        elif event_type == AgentEventType.THINKING_DELTA:
            # 思考增量 - 累积思考内容
            delta = event.data.get("delta", "")
            if delta:
                self._thinking_content += delta
                # 更新当前步骤的描述（显示思考内容片段）
                if self._current_step:
                    # 只显示最后 100 个字符，避免过长
                    preview = (
                        self._thinking_content[-100:]
                        if len(self._thinking_content) > 100
                        else self._thinking_content
                    )
                    self._current_step.description = f"💭 思考中: {preview}"
                    self._refresh()
        elif event_type == AgentEventType.TEXT_DELTA:
            # 文本增量（暂时忽略，避免过多输出）
            pass
        elif event_type == AgentEventType.PHASE_CHANGE:
            phase = event.data.get("phase", "")
            if phase:
                self.on_analyzing(f"阶段: {phase}")
        elif event_type == AgentEventType.ITERATION_START:
            iteration = event.data.get("iteration", 0)
            self.on_analyzing(f"第 {iteration} 轮迭代")
        elif event_type == AgentEventType.RESPONSE_COMPLETE:
            self.on_completed("响应完成")

    def _get_spinner_char(self) -> str:
        """获取当前 spinner 字符"""
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        char = frames[self._spinner_frame]
        self._spinner_frame = (self._spinner_frame + 1) % len(frames)
        return char

    def _refresh(self) -> None:
        """刷新显示（混合模式下为空操作）

        在旧的 Live 模式中，此方法用于刷新 Live 显示。
        在新的混合模式中，历史记录使用流式输出，不需要刷新。
        保留此方法以保持向后兼容性。
        """
        pass

    def on_query_start(self, query: str) -> None:
        """处理查询开始事件

        Args:
            query: 查询内容
        """
        step = self._history.add_step(
            description=f"开始处理查询: {query[:50]}...",
            state=DisplayState.ANALYZING,
            metadata={"query": query},
        )
        self._current_step = step
        self._refresh()

    def on_analyzing(self, message: str = "分析查询意图") -> None:
        """处理分析事件

        Args:
            message: 分析消息
        """
        step = self._history.add_step(
            description=message,
            state=DisplayState.ANALYZING,
        )
        self._current_step = step
        self._refresh()

    def on_tool_call_start(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """处理工具调用开始事件

        Args:
            tool_name: 工具名称
            arguments: 工具参数
        """
        # 更新统计信息
        self._stats["tool_calls"] += 1

        # 格式化参数显示
        # verbose 模式：显示所有参数
        # 普通模式：只显示前3个参数
        if self._verbose:
            args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
        else:
            args_str = ", ".join(f"{k}={v}" for k, v in list(arguments.items())[:3])
            if len(arguments) > 3:
                args_str += ", ..."

        step = self._history.add_step(
            description=f"调用 {tool_name}({args_str})",
            state=DisplayState.TOOL_CALLING,
            metadata={"tool_name": tool_name, "arguments": arguments},
        )
        self._current_step = step

        # 更新 Live 显示（当前操作）
        self._display.update_current_step(step, self._get_spinner_char())

    def on_tool_call_end(self, tool_name: str, result_summary: str, duration: float | None = None) -> None:
        """处理工具调用结束事件

        Args:
            tool_name: 工具名称
            result_summary: 结果摘要（由 hooks 生成）
            duration: 执行时长（秒）
        """
        # 更新统计信息
        if duration:
            self._stats["total_duration"] += duration

        if self._current_step:
            # 直接使用 hooks 生成的结果摘要
            # 不再需要调用 _format_result_summary()

            # 更新步骤状态
            self._history.update_step(
                self._current_step,
                state=DisplayState.COMPLETED,
                result_summary=result_summary,
            )

            # 如果有时长信息，更新
            if duration is not None:
                self._current_step.duration = duration

            # 输出到历史记录（流式）
            self._display.print_completed_step(self._current_step)

            # 清空 Live 区域
            self._display.clear_current()

            # 更新状态栏
            self._update_status_bar()

        self._current_step = None

    def on_thinking_start(self, message: str = "思考中") -> None:
        """处理思考开始事件

        Args:
            message: 思考消息
        """
        # 重置思考内容累积
        self._thinking_content = ""

        # 记录开始时间（如果是第一次）
        if self._stats["start_time"] is None:
            self._stats["start_time"] = time.time()

        step = self._history.add_step(
            description=message,
            state=DisplayState.THINKING,
        )
        self._current_step = step
        self._refresh()

    def on_thinking_end(self) -> None:
        """处理思考结束事件"""
        if self._current_step:
            self._history.update_step(
                self._current_step,
                state=DisplayState.COMPLETED,
            )
        self._current_step = None
        self._refresh()

    def on_aggregating(self, message: str = "聚合结果") -> None:
        """处理结果聚合事件

        Args:
            message: 聚合消息
        """
        step = self._history.add_step(
            description=message,
            state=DisplayState.AGGREGATING,
        )
        self._current_step = step
        self._refresh()

    def on_completed(self, message: str = "查询完成") -> None:
        """处理完成事件

        Args:
            message: 完成消息
        """
        if self._current_step:
            self._history.update_step(
                self._current_step,
                state=DisplayState.COMPLETED,
            )

        step = self._history.add_step(
            description=message,
            state=DisplayState.COMPLETED,
        )
        self._current_step = None
        self._refresh()

        # 打印最终状态栏
        self._update_status_bar(final=True)

    def on_error(self, error_message: str) -> None:
        """处理错误事件

        Args:
            error_message: 错误消息
        """
        if self._current_step:
            self._history.update_step(
                self._current_step,
                state=DisplayState.ERROR,
                result_summary=f"错误: {error_message}",
            )
        else:
            step = self._history.add_step(
                description="执行出错",
                state=DisplayState.ERROR,
                metadata={"error": error_message},
            )
            step.result_summary = error_message

        self._current_step = None
        self._refresh()

    def _format_result_summary(self, result: Any) -> str:
        """格式化结果摘要

        Args:
            result: 工具返回结果

        Returns:
            格式化后的摘要字符串
        """
        if result is None:
            return "✓ 完成"  # 改进：显示"完成"而不是"返回: None"

        # 如果是字典，提取关键信息
        if isinstance(result, dict):
            # 优先显示有意义的字段
            if "sources" in result:
                sources = result["sources"]
                if isinstance(sources, list) and sources:
                    return f"✓ 找到 {len(sources)} 个结果"
            if "content" in result:
                content = str(result["content"])
                preview = content[:80] + "..." if len(content) > 80 else content
                return f"✓ {preview}"
            if "error" in result:
                return f"✗ 错误: {result['error']}"

            # 空字典
            if not result:
                return "✓ 完成（无返回数据）"  # 改进：更友好的消息

            # 显示字典的前几个键值对
            items = list(result.items())[:2]
            summary = ", ".join(f"{k}={v}" for k, v in items)
            if len(result) > 2:
                summary += f", ... ({len(result)} 个字段)"
            return f"✓ {summary}"

        # 如果是列表
        if isinstance(result, list):
            if not result:
                return "✓ 完成（空列表）"  # 改进：更友好的消息
            first_item = str(result[0])[:50]
            return f"✓ {len(result)} 项 (首项: {first_item}...)"

        # 如果是字符串
        if isinstance(result, str):
            if not result:
                return "✓ 完成（空字符串）"  # 改进：更友好的消息
            preview = result[:100] + "..." if len(result) > 100 else result
            return f"✓ {preview}"

        # 其他类型
        return f"✓ {type(result).__name__}: {str(result)[:50]}"

    def _update_status_bar(self, final: bool = False) -> None:
        """更新状态栏

        Args:
            final: 是否为最终状态栏（只有最终状态栏才会打印）
        """
        if self._stats["start_time"]:
            elapsed = time.time() - self._stats["start_time"]
        else:
            elapsed = 0.0

        avg_duration = 0.0
        if self._stats["tool_calls"] > 0 and self._stats["total_duration"] > 0:
            avg_duration = self._stats["total_duration"] / self._stats["tool_calls"]

        self._display.print_status_bar({
            "tool_calls": self._stats["tool_calls"],
            "elapsed": elapsed,
            "avg_duration": avg_duration,
        }, final=final)

    def live_context(self):
        """Live 上下文管理器

        使用方式:
            async with display.live_context():
                await display.on_event(event)
        """
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _context():
            self._display.start_live()
            try:
                yield self
            finally:
                self._display.stop_live()

        return _context()

    def clear(self) -> None:
        """清空所有状态"""
        self._history.clear()
        self._current_step = None
        self._spinner_frame = 0

    def print_summary(self) -> None:
        """打印执行摘要（在 Live 结束后调用）"""
        self._console.print("\n[bold green]✓ 执行完成[/bold green]\n")
        self._console.print(self._history.render())
