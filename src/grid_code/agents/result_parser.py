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
        tool_name: 工具名称
        result: 工具返回的原始结果

    Returns:
        ToolResultSummary 包含解析后的摘要信息
    """
    # 尝试解析 JSON 字符串
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            # 非 JSON 字符串，返回基本摘要
            return ToolResultSummary(
                content_preview=_truncate_text(result, 100)
            )

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

    parser = parsers.get(tool_name)
    if parser:
        try:
            return parser(result)
        except Exception as e:
            logger.debug(f"Failed to parse {tool_name} result: {e}")

    # 默认解析器
    return _parse_generic(result)


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
        results = result.get("results", [])
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

    get_toc 返回格式:
    {
        "chapters": [
            {"id": "1", "title": "总则", "level": 1, ...},
            ...
        ]
    }
    或直接返回列表
    """
    summary = ToolResultSummary(result_type="chapters")

    if isinstance(result, dict):
        chapters = result.get("chapters", [])
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
        "pages": [
            {"page_num": 85, "content": "...", ...},
            ...
        ]
    }
    """
    summary = ToolResultSummary(result_type="pages")

    if isinstance(result, dict):
        pages = result.get("pages", [])
    elif isinstance(result, list):
        pages = result
    else:
        return summary

    summary.result_count = len(pages)

    # 提取页码
    page_nums = []
    total_chars = 0

    for page in pages:
        if isinstance(page, dict):
            page_num = page.get("page_num") or page.get("page")
            if page_num:
                page_nums.append(int(page_num))

            # 统计字符数
            content = page.get("content") or page.get("text")
            if content:
                total_chars += len(str(content))

    summary.page_sources = sorted(page_nums)

    # 生成预览
    if page_nums:
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
