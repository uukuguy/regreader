"""Agent 事件系统

定义 Agent 运行时的事件类型和事件数据结构，
用于实时状态输出和监控。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class AgentEventType(Enum):
    """Agent 事件类型

    覆盖 Agent 执行的完整生命周期：
    1. 思考阶段
    2. 工具调用阶段
    3. 迭代阶段
    4. 结果阶段
    5. 流式输出阶段
    """

    # === 思考阶段 ===
    THINKING_START = auto()      # 开始思考（LLM 推理中）
    THINKING_END = auto()        # 思考完成

    # === 工具调用阶段 ===
    TOOL_CALL_START = auto()     # 工具调用开始
    TOOL_CALL_END = auto()       # 工具调用完成
    TOOL_CALL_ERROR = auto()     # 工具调用出错

    # === 多跳推理阶段 ===
    ITERATION_START = auto()     # 新一轮迭代开始

    # === 结果阶段 ===
    RESPONSE_COMPLETE = auto()   # 响应完成

    # === 流式输出阶段 ===
    TEXT_DELTA = auto()          # 文本增量（流式输出）
    THINKING_DELTA = auto()      # 思考增量（模型内部推理）
    PHASE_CHANGE = auto()        # 阶段变化（分析问题 → 查找目录 → 检索章节）


@dataclass
class AgentEvent:
    """Agent 事件数据

    所有事件共享此结构，通过 event_type 区分类型，
    通过 data 字段传递特定事件的详细信息。

    Attributes:
        event_type: 事件类型
        timestamp: 事件发生时间
        data: 事件数据（根据类型不同包含不同字段）

    事件数据字段说明：

    TOOL_CALL_START:
        - tool_name: str        工具名称
        - tool_input: dict      工具输入参数
        - tool_id: str          工具调用ID
        - tool_brief: str       工具简述（来自元数据）
        - tool_category: str    工具分类
        - thinking_duration_ms: float  思考耗时（从上一工具结束到本工具开始）

    TOOL_CALL_END:
        - tool_name: str
        - tool_id: str
        - duration_ms: float    执行耗时（毫秒）
        - result_summary: str   结果摘要
        - result_count: int     结果数量（如有）
        - sources: list[str]    提取的来源
        - tool_input: dict      工具输入参数
        - result_type: str      结果类型（如 chapters, search_results, pages）
        - chapter_count: int    涉及章节数
        - page_sources: list[int] 来源页码列表
        - content_preview: str  内容预览

    TOOL_CALL_ERROR:
        - tool_name: str
        - tool_id: str
        - error: str

    ITERATION_START:
        - iteration: int        当前迭代次数

    RESPONSE_COMPLETE:
        - total_tool_calls: int
        - total_sources: int
        - duration_ms: float

    TEXT_DELTA:
        - delta: str            文本增量
        - part_index: int       部分索引

    THINKING_DELTA:
        - delta: str            思考文本增量

    PHASE_CHANGE:
        - phase: str            阶段名称
        - description: str      阶段描述
    """

    event_type: AgentEventType
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_name(self) -> str | None:
        """快捷获取工具名称"""
        return self.data.get("tool_name")

    @property
    def is_tool_event(self) -> bool:
        """是否为工具相关事件"""
        return self.event_type in (
            AgentEventType.TOOL_CALL_START,
            AgentEventType.TOOL_CALL_END,
            AgentEventType.TOOL_CALL_ERROR,
        )


# ==================== 便捷工厂函数 ====================


def tool_start_event(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_id: str = "",
) -> AgentEvent:
    """创建工具调用开始事件

    Args:
        tool_name: 工具名称
        tool_input: 工具输入参数
        tool_id: 工具调用ID

    Returns:
        AgentEvent 实例
    """
    from grid_code.mcp.tool_metadata import get_tool_metadata

    meta = get_tool_metadata(tool_name)
    return AgentEvent(
        event_type=AgentEventType.TOOL_CALL_START,
        data={
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_id": tool_id,
            "tool_brief": meta.brief if meta else tool_name,
            "tool_category": meta.category.value if meta else "unknown",
        },
    )


def tool_end_event(
    tool_name: str,
    tool_id: str = "",
    duration_ms: float = 0,
    result_summary: str = "",
    result_count: int | None = None,
    sources: list[str] | None = None,
    tool_input: dict | None = None,
    # 新增详细信息字段
    result_type: str | None = None,
    chapter_count: int | None = None,
    page_sources: list[int] | None = None,
    content_preview: str | None = None,
    thinking_duration_ms: float | None = None,
) -> AgentEvent:
    """创建工具调用完成事件

    Args:
        tool_name: 工具名称
        tool_id: 工具调用ID
        duration_ms: 执行耗时（毫秒）
        result_summary: 结果摘要
        result_count: 结果数量
        sources: 提取的来源列表
        tool_input: 工具调用参数（用于详细模式显示）
        result_type: 结果类型（如 chapters, search_results, pages）
        chapter_count: 涉及章节数
        page_sources: 来源页码列表
        content_preview: 内容预览
        thinking_duration_ms: 思考耗时（从上一工具结束到本工具开始）

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.TOOL_CALL_END,
        data={
            "tool_name": tool_name,
            "tool_id": tool_id,
            "duration_ms": duration_ms,
            "result_summary": result_summary,
            "result_count": result_count,
            "sources": sources or [],
            "tool_input": tool_input or {},
            "result_type": result_type,
            "chapter_count": chapter_count,
            "page_sources": page_sources or [],
            "content_preview": content_preview,
            "thinking_duration_ms": thinking_duration_ms,
        },
    )


def tool_error_event(
    tool_name: str,
    error: str,
    tool_id: str = "",
) -> AgentEvent:
    """创建工具调用错误事件

    Args:
        tool_name: 工具名称
        error: 错误信息
        tool_id: 工具调用ID

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.TOOL_CALL_ERROR,
        data={
            "tool_name": tool_name,
            "tool_id": tool_id,
            "error": error,
        },
    )


def thinking_event(start: bool = True) -> AgentEvent:
    """创建思考事件

    Args:
        start: True 表示开始思考，False 表示结束思考

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.THINKING_START if start else AgentEventType.THINKING_END,
    )


def iteration_event(iteration: int) -> AgentEvent:
    """创建迭代开始事件

    Args:
        iteration: 当前迭代次数（从1开始）

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.ITERATION_START,
        data={"iteration": iteration},
    )


def response_complete_event(
    total_tool_calls: int = 0,
    total_sources: int = 0,
    duration_ms: float = 0,
) -> AgentEvent:
    """创建响应完成事件

    Args:
        total_tool_calls: 总工具调用次数
        total_sources: 总来源数量
        duration_ms: 总耗时（毫秒）

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.RESPONSE_COMPLETE,
        data={
            "total_tool_calls": total_tool_calls,
            "total_sources": total_sources,
            "duration_ms": duration_ms,
        },
    )


def text_delta_event(delta: str, part_index: int = 0) -> AgentEvent:
    """创建文本增量事件（流式输出）

    Args:
        delta: 文本增量
        part_index: 部分索引

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.TEXT_DELTA,
        data={
            "delta": delta,
            "part_index": part_index,
        },
    )


def thinking_delta_event(delta: str) -> AgentEvent:
    """创建思考增量事件

    Args:
        delta: 思考文本增量

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.THINKING_DELTA,
        data={
            "delta": delta,
        },
    )


def phase_change_event(phase: str, description: str = "") -> AgentEvent:
    """创建阶段变化事件

    Args:
        phase: 阶段名称（如 analyzing, searching, reading）
        description: 阶段描述

    Returns:
        AgentEvent 实例
    """
    return AgentEvent(
        event_type=AgentEventType.PHASE_CHANGE,
        data={
            "phase": phase,
            "description": description,
        },
    )
