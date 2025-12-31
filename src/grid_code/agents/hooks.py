"""Claude Agent SDK Hooks

定义工具调用的审计和控制钩子函数。

Hooks 类型:
- PreToolUse: 工具调用前，可以记录日志、验证参数、阻止调用
- PostToolUse: 工具调用后，可以记录结果、提取来源、监控错误

状态回调:
通过 set_status_callback() 注册全局回调，
Hooks 会在执行时发送事件到回调。
"""

import time
from typing import Any

from loguru import logger

from grid_code.agents.callbacks import NullCallback, StatusCallback
from grid_code.agents.events import (
    tool_end_event,
    tool_error_event,
    tool_start_event,
)


# ==================== 全局状态回调 ====================

_status_callback: StatusCallback = NullCallback()
_tool_timers: dict[str, float] = {}


def set_status_callback(callback: StatusCallback | None) -> None:
    """设置全局状态回调

    Args:
        callback: 状态回调实例，None 表示禁用
    """
    global _status_callback
    _status_callback = callback or NullCallback()


def get_status_callback() -> StatusCallback:
    """获取当前状态回调

    Returns:
        当前注册的状态回调
    """
    return _status_callback


# ==================== Hook 函数 ====================


async def pre_tool_audit_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """工具调用前审计

    在每次工具调用前执行，用于：
    1. 记录工具调用日志
    2. 验证必要参数
    3. 发送状态事件
    4. 可选阻止无效调用

    Args:
        input_data: 包含 tool_name 和 tool_input 的字典
        tool_use_id: 工具调用的唯一标识
        context: Hook 上下文（SDK 提供）

    Returns:
        空字典表示允许调用；返回 hookSpecificOutput 可阻止调用
    """
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    tool_id = tool_use_id or tool_name

    # 记录开始时间
    _tool_timers[tool_id] = time.time()

    # 记录调用日志
    logger.debug(f"[PreToolUse] {tool_name} | args: {_truncate_dict(tool_input)}")

    # 发送状态事件
    event = tool_start_event(tool_name, tool_input, tool_id)
    await _status_callback.on_event(event)

    # 验证 reg_id 参数（如果存在）
    if "reg_id" in tool_input:
        reg_id = tool_input["reg_id"]
        if not reg_id or not isinstance(reg_id, str):
            logger.warning(f"[PreToolUse] {tool_name}: reg_id 参数无效")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "reg_id 参数不能为空",
                }
            }

    # 验证查询参数
    if tool_name == "smart_search" and "query" in tool_input:
        query = tool_input.get("query", "")
        if not query or len(query.strip()) < 2:
            logger.warning("[PreToolUse] smart_search: 查询词过短")
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "查询词至少需要 2 个字符",
                }
            }

    return {}


async def post_tool_audit_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """工具调用后审计

    在每次工具调用完成后执行，用于：
    1. 记录执行结果
    2. 监控错误情况
    3. 发送状态事件
    4. 统计调用次数

    Args:
        input_data: 包含 tool_name、tool_input、tool_result 的字典
        tool_use_id: 工具调用的唯一标识
        context: Hook 上下文

    Returns:
        空字典（PostToolUse 通常不修改结果）
    """
    tool_name = input_data.get("tool_name", "unknown")
    tool_result = input_data.get("tool_result", {})
    tool_input = input_data.get("tool_input", {})
    tool_id = tool_use_id or tool_name

    # 计算耗时
    start_time = _tool_timers.pop(tool_id, None)
    duration_ms = (time.time() - start_time) * 1000 if start_time else 0

    # 检查错误并发送事件
    error_msg = None
    if isinstance(tool_result, dict) and "error" in tool_result:
        error_msg = tool_result.get("error", "未知错误")
        logger.warning(f"[PostToolUse] {tool_name} 返回错误: {error_msg}")

        # 发送错误事件
        event = tool_error_event(tool_name, str(error_msg), tool_id)
        await _status_callback.on_event(event)
        return {}

    elif isinstance(tool_result, list) and tool_result and isinstance(tool_result[0], dict):
        if "error" in tool_result[0]:
            error_msg = tool_result[0].get("error")
            logger.warning(f"[PostToolUse] {tool_name} 返回错误: {error_msg}")

            event = tool_error_event(tool_name, str(error_msg), tool_id)
            await _status_callback.on_event(event)
            return {}

        logger.debug(f"[PostToolUse] {tool_name} 成功，返回 {len(tool_result)} 条结果")

        # 提取来源
        sources: list[str] = []
        for item in tool_result:
            _extract_sources_recursive(item, sources)

        # 发送完成事件
        event = tool_end_event(
            tool_name=tool_name,
            tool_id=tool_id,
            duration_ms=duration_ms,
            result_count=len(tool_result),
            sources=list(set(sources)),
            tool_input=tool_input,
        )
        await _status_callback.on_event(event)

    else:
        logger.debug(f"[PostToolUse] {tool_name} 执行完成")

        # 提取来源
        sources = []
        _extract_sources_recursive(tool_result, sources)

        # 发送完成事件
        event = tool_end_event(
            tool_name=tool_name,
            tool_id=tool_id,
            duration_ms=duration_ms,
            sources=list(set(sources)),
            tool_input=tool_input,
        )
        await _status_callback.on_event(event)

    return {}


async def source_extraction_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """来源提取钩子

    从工具结果中提取 source 字段，用于构建引用列表。

    注意：此钩子主要用于日志记录，实际的来源提取在 Agent 主循环中完成。

    Args:
        input_data: 包含 tool_result 的字典
        tool_use_id: 工具调用的唯一标识
        context: Hook 上下文

    Returns:
        空字典
    """
    tool_result = input_data.get("tool_result", {})
    sources: list[str] = []

    _extract_sources_recursive(tool_result, sources)

    if sources:
        unique_sources = list(set(sources))
        preview = unique_sources[:3]
        logger.debug(f"[SourceExtraction] 发现 {len(unique_sources)} 个来源: {preview}...")

    return {}


def _extract_sources_recursive(data: Any, sources: list[str]) -> None:
    """递归提取来源信息

    Args:
        data: 要提取的数据
        sources: 来源列表（会被修改）
    """
    if data is None:
        return

    if isinstance(data, dict):
        # 直接检查 source 字段
        if "source" in data and data["source"]:
            source_val = data["source"]
            if isinstance(source_val, str):
                sources.append(source_val)

        # 递归处理嵌套
        for key, value in data.items():
            if key != "source":  # 避免重复处理
                _extract_sources_recursive(value, sources)

    elif isinstance(data, list):
        for item in data:
            _extract_sources_recursive(item, sources)

    elif isinstance(data, str):
        # 尝试解析 JSON 字符串
        try:
            import json
            parsed = json.loads(data)
            _extract_sources_recursive(parsed, sources)
        except (json.JSONDecodeError, TypeError):
            pass


def _truncate_dict(d: dict, max_str_len: int = 100) -> dict:
    """截断字典中的长字符串，用于日志输出

    Args:
        d: 原始字典
        max_str_len: 字符串最大长度

    Returns:
        截断后的字典（新对象）
    """
    result = {}
    for key, value in d.items():
        if isinstance(value, str) and len(value) > max_str_len:
            result[key] = value[:max_str_len] + "..."
        elif isinstance(value, dict):
            result[key] = _truncate_dict(value, max_str_len)
        elif isinstance(value, list) and len(value) > 5:
            result[key] = f"[{len(value)} items]"
        else:
            result[key] = value
    return result


# 导出的 Hook 列表（按使用场景分组）
AUDIT_HOOKS = {
    "PreToolUse": [pre_tool_audit_hook],
    "PostToolUse": [post_tool_audit_hook, source_extraction_hook],
}
