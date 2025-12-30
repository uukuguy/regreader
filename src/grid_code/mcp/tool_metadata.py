"""MCP 工具元数据定义

定义工具分类、优先级、工具链关系等元数据，用于：
1. CLI 分类展示工具列表
2. MCP Server 添加结构化 meta 信息
3. 智能体理解工具使用方式
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolCategory(str, Enum):
    """工具分类"""

    BASE = "base"
    MULTI_HOP = "multi-hop"
    CONTEXT = "context"
    DISCOVERY = "discovery"
    NAVIGATION = "navigation"


# 分类中文名称映射
CATEGORY_NAMES: dict[ToolCategory, str] = {
    ToolCategory.BASE: "基础工具",
    ToolCategory.MULTI_HOP: "核心多跳",
    ToolCategory.CONTEXT: "上下文",
    ToolCategory.DISCOVERY: "发现",
    ToolCategory.NAVIGATION: "导航",
}

# 分类描述映射
CATEGORY_DESCRIPTIONS: dict[ToolCategory, str] = {
    ToolCategory.BASE: "核心查询和读取功能，通常作为起点使用",
    ToolCategory.MULTI_HOP: "处理注释、表格、引用等需要多步跳转的场景",
    ToolCategory.CONTEXT: "扩展搜索结果的上下文，获取更完整的信息",
    ToolCategory.DISCOVERY: "发现相关内容，进行比较分析",
    ToolCategory.NAVIGATION: "了解可用工具和使用方式",
}

# 分类显示顺序
CATEGORY_ORDER: list[ToolCategory] = [
    ToolCategory.BASE,
    ToolCategory.MULTI_HOP,
    ToolCategory.CONTEXT,
    ToolCategory.DISCOVERY,
    ToolCategory.NAVIGATION,
]

# 分类信息（用于 get_tool_guide）
CATEGORY_INFO: dict[str, dict[str, str]] = {
    "base": {
        "name": "基础工具",
        "description": "核心查询和读取功能，通常作为起点使用",
    },
    "multi-hop": {
        "name": "核心多跳",
        "description": "处理注释、表格、引用等需要多步跳转的场景",
    },
    "context": {
        "name": "上下文",
        "description": "扩展搜索结果的上下文，获取更完整的信息",
    },
    "discovery": {
        "name": "发现",
        "description": "发现相关内容，进行比较分析",
    },
    "navigation": {
        "name": "导航",
        "description": "了解可用工具和使用方式",
    },
}


@dataclass
class ToolMetadata:
    """MCP 工具元数据"""

    name: str
    """工具名称"""

    brief: str
    """简短描述（用于列表显示）"""

    category: ToolCategory
    """工具分类"""

    phase: int = 0
    """阶段: 0=基础, 1/2/3=对应 Phase"""

    priority: int = 2
    """优先级: 1=高, 2=中, 3=低（数值越小优先级越高）"""

    prerequisites: list[str] = field(default_factory=list)
    """前置工具列表"""

    next_tools: list[str] = field(default_factory=list)
    """后续推荐工具列表"""

    use_cases: list[str] = field(default_factory=list)
    """适用场景列表"""

    cli_command: str | None = None
    """对应的 CLI 命令"""

    expected_params: dict[str, str] = field(default_factory=dict)
    """期望的参数列表: {参数名: 类型}，用于服务验证"""

    @property
    def category_name(self) -> str:
        """获取分类中文名称"""
        return CATEGORY_NAMES.get(self.category, str(self.category.value))

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于 MCP meta 参数）"""
        return {
            "category": self.category.value,
            "category_name": self.category_name,
            "phase": self.phase,
            "priority": self.priority,
            "prerequisites": self.prerequisites,
            "next_tools": self.next_tools,
            "use_cases": self.use_cases,
            "cli_command": self.cli_command,
        }

    def format_description_suffix(self) -> str:
        """生成描述后缀（用于增强工具描述）"""
        lines = []

        if self.use_cases:
            lines.append(f"使用场景：{', '.join(self.use_cases)}。")

        if self.prerequisites:
            lines.append(f"前置工具：{', '.join(self.prerequisites)}。")

        if self.next_tools:
            lines.append(f"后续工具：{', '.join(self.next_tools)}。")

        return "\n".join(lines)


# ==================== 工具元数据注册表 ====================

TOOL_METADATA: dict[str, ToolMetadata] = {
    # === 基础工具 ===
    "get_toc": ToolMetadata(
        name="get_toc",
        brief="获取规程目录树",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=[],
        next_tools=["smart_search", "read_chapter_content"],
        use_cases=["了解规程结构", "确定搜索范围"],
        cli_command="toc",
        expected_params={"reg_id": "string"},
    ),
    "smart_search": ToolMetadata(
        name="smart_search",
        brief="混合检索",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=["get_toc"],
        next_tools=["read_page_range", "get_block_with_context"],
        use_cases=["查找相关内容", "混合检索"],
        cli_command="search",
        expected_params={
            "query": "string",
            "reg_id": "string",
            "chapter_scope": "string|null",
            "limit": "integer",
            "block_types": "array|null",
            "section_number": "string|null",
        },
    ),
    "read_page_range": ToolMetadata(
        name="read_page_range",
        brief="读取页面范围",
        category=ToolCategory.BASE,
        phase=0,
        priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["阅读完整页面", "查看跨页表格"],
        cli_command="read-pages",
        expected_params={
            "reg_id": "string",
            "start_page": "integer",
            "end_page": "integer",
        },
    ),
    "list_regulations": ToolMetadata(
        name="list_regulations",
        brief="列出已入库规程",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=[],
        next_tools=["get_toc"],
        use_cases=["了解可用规程"],
        cli_command="list",
        expected_params={},
    ),
    "get_chapter_structure": ToolMetadata(
        name="get_chapter_structure",
        brief="获取章节结构",
        category=ToolCategory.BASE,
        phase=0,
        priority=2,
        prerequisites=["get_toc"],
        next_tools=["read_chapter_content"],
        use_cases=["获取章节树"],
        cli_command="chapter-structure",
        expected_params={"reg_id": "string"},
    ),
    "get_page_chapter_info": ToolMetadata(
        name="get_page_chapter_info",
        brief="获取页面章节信息",
        category=ToolCategory.BASE,
        phase=0,
        priority=3,
        prerequisites=[],
        next_tools=[],
        use_cases=["了解页面所属章节"],
        cli_command="page-info",
        expected_params={"reg_id": "string", "page_num": "integer"},
    ),
    "read_chapter_content": ToolMetadata(
        name="read_chapter_content",
        brief="读取章节内容",
        category=ToolCategory.BASE,
        phase=0,
        priority=2,
        prerequisites=["get_chapter_structure"],
        next_tools=[],
        use_cases=["阅读完整章节"],
        cli_command="read-chapter",
        expected_params={
            "reg_id": "string",
            "section_number": "string",
            "include_children": "boolean",
        },
    ),
    # === 核心多跳 ===
    "lookup_annotation": ToolMetadata(
        name="lookup_annotation",
        brief="查找注释内容",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["查找注释内容", "理解表格脚注"],
        cli_command="lookup-annotation",
        expected_params={
            "reg_id": "string",
            "annotation_id": "string",
            "page_hint": "integer|null",
        },
    ),
    "search_tables": ToolMetadata(
        name="search_tables",
        brief="搜索表格",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["get_toc"],
        next_tools=["get_table_by_id"],
        use_cases=["查找特定表格", "表格内容搜索"],
        cli_command="search-tables",
        expected_params={
            "query": "string",
            "reg_id": "string",
            "chapter_scope": "string|null",
            "search_cells": "boolean",
            "limit": "integer",
        },
    ),
    "resolve_reference": ToolMetadata(
        name="resolve_reference",
        brief="解析交叉引用",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["smart_search"],
        next_tools=["read_page_range", "read_chapter_content"],
        use_cases=["解析交叉引用"],
        cli_command="resolve-reference",
        expected_params={"reg_id": "string", "reference_text": "string"},
    ),
    # === 上下文 ===
    "search_annotations": ToolMetadata(
        name="search_annotations",
        brief="搜索所有注释",
        category=ToolCategory.CONTEXT,
        phase=2,
        priority=3,
        prerequisites=[],
        next_tools=["lookup_annotation"],
        use_cases=["搜索所有注释"],
        cli_command="search-annotations",
        expected_params={
            "reg_id": "string",
            "pattern": "string|null",
            "annotation_type": "string|null",
        },
    ),
    "get_table_by_id": ToolMetadata(
        name="get_table_by_id",
        brief="获取完整表格",
        category=ToolCategory.CONTEXT,
        phase=2,
        priority=2,
        prerequisites=["search_tables"],
        next_tools=[],
        use_cases=["获取完整表格"],
        cli_command="get-table",
        expected_params={
            "reg_id": "string",
            "table_id": "string",
            "include_merged": "boolean",
        },
    ),
    "get_block_with_context": ToolMetadata(
        name="get_block_with_context",
        brief="获取内容块上下文",
        category=ToolCategory.CONTEXT,
        phase=2,
        priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["扩展上下文"],
        cli_command="get-block-context",
        expected_params={
            "reg_id": "string",
            "block_id": "string",
            "context_blocks": "integer",
        },
    ),
    # === 发现 ===
    "find_similar_content": ToolMetadata(
        name="find_similar_content",
        brief="查找相似内容",
        category=ToolCategory.DISCOVERY,
        phase=3,
        priority=3,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["查找相似内容"],
        cli_command="find-similar",
        expected_params={
            "reg_id": "string",
            "query_text": "string|null",
            "source_block_id": "string|null",
            "limit": "integer",
            "exclude_same_page": "boolean",
        },
    ),
    "compare_sections": ToolMetadata(
        name="compare_sections",
        brief="比较章节",
        category=ToolCategory.DISCOVERY,
        phase=3,
        priority=3,
        prerequisites=["get_chapter_structure"],
        next_tools=[],
        use_cases=["比较章节"],
        cli_command="compare-sections",
        expected_params={
            "reg_id": "string",
            "section_a": "string",
            "section_b": "string",
            "include_tables": "boolean",
        },
    ),
    # === 导航 ===
    "get_tool_guide": ToolMetadata(
        name="get_tool_guide",
        brief="获取工具使用指南",
        category=ToolCategory.NAVIGATION,
        phase=0,
        priority=1,
        prerequisites=[],
        next_tools=["get_toc", "list_regulations"],
        use_cases=["了解可用工具", "获取使用指南"],
        cli_command=None,
        expected_params={
            "category": "string|null",
            "include_workflows": "boolean",
        },
    ),
}


# ==================== 工作流定义 ====================

TOOL_WORKFLOWS: dict[str, list[str]] = {
    "查找表格内容": ["get_toc", "search_tables", "get_table_by_id"],
    "理解注释引用": ["smart_search", "lookup_annotation"],
    "阅读章节": ["get_chapter_structure", "read_chapter_content"],
    "解析交叉引用": ["smart_search", "resolve_reference", "read_page_range"],
    "扩展搜索上下文": ["smart_search", "get_block_with_context"],
    "查找相关规定": ["smart_search", "find_similar_content"],
}

# ==================== 使用建议 ====================

TOOL_TIPS: list[str] = [
    "先用 get_toc 或 list_regulations 了解规程结构",
    "搜索结果不完整时用 get_block_with_context 扩展上下文",
    "跨页表格需用 get_table_by_id 获取完整内容",
    "遇到「见注X」时用 lookup_annotation 获取注释",
    "遇到「见第X章」时用 resolve_reference 解析引用",
    "用 find_similar_content 发现相关条款",
]


# ==================== 辅助函数 ====================


def get_tools_by_category(category: ToolCategory | None = None) -> dict[ToolCategory, list[ToolMetadata]]:
    """按分类获取工具列表

    Args:
        category: 指定分类，None 表示所有分类

    Returns:
        分类到工具列表的映射
    """
    result: dict[ToolCategory, list[ToolMetadata]] = {}

    for cat in CATEGORY_ORDER:
        if category is not None and cat != category:
            continue
        tools = [meta for meta in TOOL_METADATA.values() if meta.category == cat]
        if tools:
            # 按优先级排序
            tools.sort(key=lambda t: (t.priority, t.name))
            result[cat] = tools

    return result


def get_tool_metadata(tool_name: str) -> ToolMetadata | None:
    """获取工具元数据

    Args:
        tool_name: 工具名称

    Returns:
        工具元数据，不存在返回 None
    """
    return TOOL_METADATA.get(tool_name)


def get_category_info() -> list[dict[str, Any]]:
    """获取分类信息列表

    Returns:
        分类信息列表，每个包含 id, name, description, count
    """
    tools_by_cat = get_tools_by_category()
    return [
        {
            "id": cat.value,
            "name": CATEGORY_NAMES[cat],
            "description": CATEGORY_DESCRIPTIONS[cat],
            "count": len(tools_by_cat.get(cat, [])),
        }
        for cat in CATEGORY_ORDER
        if cat in tools_by_cat
    ]
