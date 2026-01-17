"""工具结果解析器

解析不同 MCP 工具的返回结果，提取摘要信息用于详细模式显示。
"""

import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ToolResultSummary:
    """工具结果摘要

    用于详细模式下显示工具调用的结果信息。

    Attributes:
        result_count: 结果数量
        result_type: 结果类型（如 chapters, search_results, pages）
        chapter_count: 涉及章节数
        page_sources: 来源页码列表
        content_preview: 内容预览（截断后的关键内容）
        chapter_names: 章节名称列表（用于 get_toc）
        table_info: 表格信息（用于 get_table_by_id）
    """

    result_count: int | None = None
    result_type: str | None = None
    chapter_count: int | None = None
    page_sources: list[int] = field(default_factory=list)
    content_preview: str | None = None
    chapter_names: list[str] = field(default_factory=list)
    table_info: str | None = None


def parse_tool_result(tool_name: str, result: Any) -> ToolResultSummary:
    """根据工具类型解析结果，提取摘要信息

    Args:
        tool_name: 工具名称（支持完整 MCP 名称如 mcp__gridcode__smart_search）
        result: 工具返回的原始结果

    Returns:
        ToolResultSummary 包含解析后的摘要信息
    """
    # 去除 MCP 前缀（mcp__gridcode__smart_search -> smart_search）
    simple_name = tool_name
    if "__" in tool_name:
        parts = tool_name.split("__")
        simple_name = parts[-1] if len(parts) > 1 else tool_name

    # DEBUG: 记录原始输入
    logger.debug(f"[parse_tool_result] tool={simple_name}, input_type={type(result).__name__}")
    logger.debug(f"[parse_tool_result] input_repr={repr(result)[:300]}")

    # 尝试解析 JSON 字符串
    if isinstance(result, str):
        try:
            result = json.loads(result)
            logger.debug(f"[parse_tool_result] parsed JSON string to {type(result).__name__}")
        except (json.JSONDecodeError, TypeError):
            # 非 JSON 字符串，返回基本摘要
            return ToolResultSummary(
                content_preview=_truncate_text(result, 100)
            )

    # 处理 Claude SDK TextContent 格式: [{"type": "text", "text": "..."}]
    original_result = result
    result = _unwrap_text_content(result)
    if result is not original_result:
        logger.debug(f"[parse_tool_result] unwrapped TextContent to {type(result).__name__}")
        logger.debug(f"[parse_tool_result] unwrapped_repr={repr(result)[:300]}")

    # 根据工具名称分发到对应的解析器
    parsers = {
        "smart_search": _parse_smart_search,
        "get_toc": _parse_get_toc,
        "read_page_range": _parse_read_page_range,
        "get_table_by_id": _parse_get_table_by_id,
        "read_page": _parse_read_page,
        "search_keyword": _parse_search_keyword,
        "search_vector": _parse_search_vector,
    }

    parser = parsers.get(simple_name)
    if parser:
        try:
            return parser(result)
        except Exception as e:
            logger.debug(f"Failed to parse {simple_name} result: {e}")

    # 默认解析器
    return _parse_generic(result)


def format_result_summary(summary: ToolResultSummary, sources: list[str]) -> str:
    """格式化工具结果摘要为人类可读的字符串

    Args:
        summary: 工具结果摘要对象
        sources: 来源列表

    Returns:
        格式化的摘要字符串
    """
    # 优先使用详细信息，而不是仅显示数量

    # get_toc: 显示章节数量和章节名称预览
    if summary.result_type == "chapters" and summary.result_count is not None:
        if summary.chapter_names:
            # 提取章节编号（取第一个词）
            chapter_nums = [name.split()[0] for name in summary.chapter_names[:3]]
            preview = ", ".join(chapter_nums)
            if summary.result_count > 3:
                preview += "..."
            return f"✓ 返回 {summary.result_count} 个章节 ({preview})"
        return f"✓ 返回 {summary.result_count} 个章节"

    # smart_search: 显示搜索结果数量、页码和内容预览
    if summary.result_type == "search_results" and summary.result_count is not None:
        parts = [f"✓ 找到 {summary.result_count} 个结果"]

        # 添加页码信息
        if summary.page_sources:
            page_str = format_page_sources(summary.page_sources, max_display=3)
            parts.append(f"({page_str})")

        # 添加内容预览
        if summary.content_preview:
            preview = summary.content_preview[:60] + "..." if len(summary.content_preview) > 60 else summary.content_preview
            parts.append(f": {preview}")

        return " ".join(parts)

    # read_page_range: 显示页码范围和内容统计
    if summary.result_type == "pages" and summary.result_count is not None:
        parts = [f"✓ 读取 {summary.result_count} 页内容"]

        # 添加页码范围
        if summary.page_sources:
            if len(summary.page_sources) == 1:
                parts.append(f"(P{summary.page_sources[0]})")
            else:
                start = summary.page_sources[0]
                end = summary.page_sources[-1]
                parts.append(f"(P{start}-P{end})")

        # 添加内容统计
        if summary.content_preview:
            parts.append(f": {summary.content_preview}")

        return " ".join(parts)

    # 其他结果类型：使用通用格式
    if summary.result_count is not None and summary.result_count > 0:
        return f"✓ 返回 {summary.result_count} 项结果"

    # 如果有章节信息
    if summary.chapter_count and summary.chapter_count > 0:
        return f"✓ 涉及 {summary.chapter_count} 个章节"

    # 如果有来源信息
    if sources:
        return f"✓ 来源: {', '.join(sources[:3])}" + (f" 等 {len(sources)} 个" if len(sources) > 3 else "")

    # 如果有内容预览
    if summary.content_preview:
        preview = summary.content_preview[:80] + "..." if len(summary.content_preview) > 80 else summary.content_preview
        return f"✓ {preview}"

    # 如果有表格信息
    if summary.table_info:
        return f"✓ {summary.table_info}"

    # 默认返回
    return "✓ 完成"


def _parse_smart_search(result: Any) -> ToolResultSummary:
    """解析 smart_search 结果

    smart_search 返回格式:
    {
        "results": [
            {
                "content": "...",
                "page_num": 85,
                "chapter_id": "3.1",
                "score": 0.85,
                ...
            },
            ...
        ]
    }
    """
    summary = ToolResultSummary(result_type="search_results")

    if isinstance(result, dict):
        # 兼容 "result"（MCP 格式）和 "results"（旧格式）
        results = result.get("result") or result.get("results", [])
    elif isinstance(result, list):
        results = result
    else:
        return summary

    summary.result_count = len(results)

    # 提取页码和章节
    pages = set()
    chapters = set()
    contents = []

    for item in results:
        if isinstance(item, dict):
            # 页码
            page = item.get("page_num") or item.get("page")
            if page:
                pages.add(int(page))

            # 章节
            chapter = item.get("chapter_id") or item.get("chapter")
            if chapter:
                chapters.add(str(chapter))

            # 内容预览
            content = item.get("content") or item.get("text") or item.get("snippet")
            if content and len(contents) < 3:
                contents.append(_truncate_text(str(content), 50))

    summary.page_sources = sorted(pages)
    summary.chapter_count = len(chapters)
    summary.content_preview = " | ".join(contents) if contents else None

    return summary


def _parse_get_toc(result: Any) -> ToolResultSummary:
    """解析 get_toc 结果

    get_toc 返回格式 (TocTree):
    {
        "reg_id": "angui_2024",
        "title": "...",
        "total_pages": 150,
        "items": [
            {"title": "1. 总则", "level": 1, "page_start": 4, ...},
            ...
        ]
    }
    """
    summary = ToolResultSummary(result_type="chapters")

    if isinstance(result, dict):
        # TocTree 使用 items 字段，兼容旧格式 chapters
        chapters = result.get("items", []) or result.get("chapters", [])
    elif isinstance(result, list):
        chapters = result
    else:
        return summary

    summary.result_count = len(chapters)

    # 提取章节名称（仅取前几个）
    names = []
    for ch in chapters[:5]:
        if isinstance(ch, dict):
            title = ch.get("title") or ch.get("name") or ch.get("id")
            if title:
                names.append(str(title))
        elif isinstance(ch, str):
            names.append(ch)

    summary.chapter_names = names

    # 生成预览
    if names:
        preview = ", ".join(names)
        if len(chapters) > 5:
            preview += f"... (共{len(chapters)}章)"
        summary.content_preview = preview

    return summary


def _parse_read_page_range(result: Any) -> ToolResultSummary:
    """解析 read_page_range 结果

    read_page_range 返回格式:
    {
        "content_markdown": "...",
        "source": "angui_2024 P150",
        "start_page": 150,
        "end_page": 150,
        "page_count": 1,
        "has_merged_tables": false
    }
    """
    summary = ToolResultSummary(result_type="pages")

    if not isinstance(result, dict):
        return summary

    # 提取页码信息
    start_page = result.get("start_page")
    end_page = result.get("end_page")
    page_count = result.get("page_count", 0)

    # 设置结果数量
    summary.result_count = page_count if page_count else 1

    # 构建页码列表
    if start_page and end_page:
        summary.page_sources = list(range(int(start_page), int(end_page) + 1))
    elif start_page:
        summary.page_sources = [int(start_page)]

    # 统计内容字符数
    content = result.get("content_markdown") or result.get("content")
    if content:
        total_chars = len(str(content))
        summary.content_preview = f"共 {total_chars} 字符"

    return summary


def _parse_read_page(result: Any) -> ToolResultSummary:
    """解析 read_page 结果（单页读取）"""
    summary = ToolResultSummary(result_type="page")

    if isinstance(result, dict):
        page_num = result.get("page_num") or result.get("page")
        if page_num:
            summary.page_sources = [int(page_num)]
            summary.result_count = 1

        content = result.get("content") or result.get("text")
        if content:
            summary.content_preview = f"共 {len(str(content))} 字符"

    return summary


def _parse_get_table_by_id(result: Any) -> ToolResultSummary:
    """解析 get_table_by_id 结果

    get_table_by_id 返回格式:
    {
        "table_id": "T1",
        "title": "安全距离表",
        "rows": [...],
        "page_num": 92,
        ...
    }
    """
    summary = ToolResultSummary(result_type="table")

    if not isinstance(result, dict):
        return summary

    summary.result_count = 1

    # 表格信息
    title = result.get("title") or result.get("caption")
    rows = result.get("rows", [])
    cols = result.get("columns", [])

    info_parts = []
    if title:
        info_parts.append(f"「{title}」")
    if rows:
        info_parts.append(f"{len(rows)}行")
    if cols:
        info_parts.append(f"{len(cols)}列")

    summary.table_info = " ".join(info_parts) if info_parts else None
    summary.content_preview = summary.table_info

    # 页码
    page_num = result.get("page_num") or result.get("page")
    if page_num:
        summary.page_sources = [int(page_num)]

    return summary


def _parse_search_keyword(result: Any) -> ToolResultSummary:
    """解析关键词搜索结果"""
    return _parse_smart_search(result)  # 格式类似


def _parse_search_vector(result: Any) -> ToolResultSummary:
    """解析向量搜索结果"""
    return _parse_smart_search(result)  # 格式类似


def _parse_generic(result: Any) -> ToolResultSummary:
    """通用解析器

    尝试从结果中提取通用字段
    """
    summary = ToolResultSummary()

    if isinstance(result, dict):
        # 尝试识别结果类型
        if "results" in result:
            summary.result_type = "results"
            summary.result_count = len(result["results"])
        elif "chapters" in result:
            summary.result_type = "chapters"
            summary.result_count = len(result["chapters"])
        elif "pages" in result:
            summary.result_type = "pages"
            summary.result_count = len(result["pages"])
        elif "items" in result:
            summary.result_type = "items"
            summary.result_count = len(result["items"])

        # 提取页码
        pages = set()
        _extract_pages_recursive(result, pages)
        if pages:
            summary.page_sources = sorted(pages)

    elif isinstance(result, list):
        summary.result_count = len(result)

        # 提取页码
        pages = set()
        for item in result:
            _extract_pages_recursive(item, pages)
        if pages:
            summary.page_sources = sorted(pages)

    return summary


def _extract_pages_recursive(data: Any, pages: set[int]) -> None:
    """递归提取页码"""
    if isinstance(data, dict):
        for key in ("page_num", "page", "page_number"):
            if key in data and data[key] is not None:
                try:
                    pages.add(int(data[key]))
                except (ValueError, TypeError):
                    pass

        for value in data.values():
            _extract_pages_recursive(value, pages)

    elif isinstance(data, list):
        for item in data:
            _extract_pages_recursive(item, pages)


def _truncate_text(text: str, max_length: int = 50) -> str:
    """截断文本

    Args:
        text: 原始文本
        max_length: 最大长度

    Returns:
        截断后的文本，超长时添加省略号
    """
    text = text.strip()
    # 移除换行符
    text = " ".join(text.split())

    if len(text) <= max_length:
        return text

    return text[:max_length] + "..."


def _unwrap_text_content(result: Any) -> Any:
    """解包 Claude SDK TextContent 格式

    Claude Agent SDK 的 MCP 工具响应可能被包装在 TextContent 格式中:
    [{"type": "text", "text": '{"key": "value"}'}]

    此函数递归解包并解析内部 JSON。

    Args:
        result: 可能被包装的结果

    Returns:
        解包后的结果
    """
    if not isinstance(result, list):
        return result

    # 检查是否为 TextContent 格式
    if len(result) == 1 and isinstance(result[0], dict):
        item = result[0]
        if item.get("type") == "text" and "text" in item:
            text_content = item["text"]
            # 尝试解析 text 字段中的 JSON
            if isinstance(text_content, str):
                try:
                    return json.loads(text_content)
                except (json.JSONDecodeError, TypeError):
                    return text_content
            return text_content

    # 检查多个 TextContent 项（合并文本后解析）
    if all(isinstance(item, dict) and item.get("type") == "text" for item in result):
        combined_text = "".join(
            item.get("text", "") for item in result if isinstance(item, dict)
        )
        if combined_text:
            try:
                return json.loads(combined_text)
            except (json.JSONDecodeError, TypeError):
                return combined_text

    return result


def format_page_sources(pages: list[int], max_display: int = 5) -> str:
    """格式化页码列表

    Args:
        pages: 页码列表
        max_display: 最多显示数量

    Returns:
        格式化后的字符串，如 "P85, P86, P92"

    Examples:
        >>> format_page_sources([85, 86, 92])
        'P85, P86, P92'
        >>> format_page_sources([1, 2, 3, 4, 5, 6, 7])
        'P1, P2, P3, P4, P5... (共7页)'
    """
    if not pages:
        return ""

    pages = sorted(set(pages))

    if len(pages) <= max_display:
        return ", ".join(f"P{p}" for p in pages)

    displayed = ", ".join(f"P{p}" for p in pages[:max_display])
    return f"{displayed}... (共{len(pages)}页)"
