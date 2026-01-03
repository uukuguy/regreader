"""MCP 工具元数据定义

定义工具分类、优先级、工具链关系等元数据，用于：
1. CLI 分类展示工具列表
2. MCP Server 添加结构化 meta 信息
3. 智能体理解工具使用方式

工具集设计原则：
- 核心工具（8个）：智能体检索安规必备，始终启用
- 可选工具（2个）：高级分析功能，默认禁用，配置开关启用
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


# ==================== 工具集定义 ====================

# 核心工具（8个，始终启用）
CORE_TOOLS: list[str] = [
    # 基础工具（4个）
    "list_regulations",  # 入口：列出可用规程
    "get_toc",  # 导航：获取目录结构
    "smart_search",  # 检索：混合搜索
    "read_page_range",  # 阅读：获取页面内容
    # 多跳工具（3个）
    "search_tables",  # 表格：搜索表格
    "lookup_annotation",  # 多跳：追踪注释
    "resolve_reference",  # 多跳：解析引用
    # 扩展工具（1个）
    "get_table_by_id",  # 表格：获取完整跨页表格
]

# 高级分析工具（默认禁用，配置开关启用）
ADVANCED_TOOLS: list[str] = [
    "find_similar_content",  # 高级：查找相似内容
    "compare_sections",  # 高级：比较章节
]


# 分类中文名称映射
CATEGORY_NAMES: dict[ToolCategory, str] = {
    ToolCategory.BASE: "基础工具",
    ToolCategory.MULTI_HOP: "多跳推理",
    ToolCategory.CONTEXT: "上下文扩展",
    ToolCategory.DISCOVERY: "高级分析",
}

# 分类描述映射
CATEGORY_DESCRIPTIONS: dict[ToolCategory, str] = {
    ToolCategory.BASE: "核心查询和读取功能，通常作为检索起点",
    ToolCategory.MULTI_HOP: "处理注释、表格、引用等需要多步跳转的场景",
    ToolCategory.CONTEXT: "获取完整表格内容",
    ToolCategory.DISCOVERY: "发现相关内容，进行比较分析（可选）",
}

# 分类显示顺序
CATEGORY_ORDER: list[ToolCategory] = [
    ToolCategory.BASE,
    ToolCategory.MULTI_HOP,
    ToolCategory.CONTEXT,
    ToolCategory.DISCOVERY,
]

# 分类信息（用于系统提示词）
CATEGORY_INFO: dict[str, dict[str, str]] = {
    "base": {
        "name": "基础工具",
        "description": "核心查询和读取功能，通常作为检索起点",
    },
    "multi-hop": {
        "name": "多跳推理",
        "description": "处理注释、表格、引用等需要多步跳转的场景",
    },
    "context": {
        "name": "上下文扩展",
        "description": "获取完整表格内容",
    },
    "discovery": {
        "name": "高级分析",
        "description": "发现相关内容，进行比较分析（可选）",
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
    # === 基础工具（4个） ===
    "list_regulations": ToolMetadata(
        name="list_regulations",
        brief="列出已入库规程",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=[],
        next_tools=["get_toc"],
        use_cases=["了解可用规程", "确定规程范围"],
        cli_command="list",
        expected_params={},
    ),
    "get_toc": ToolMetadata(
        name="get_toc",
        brief="获取规程目录树",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=[],
        next_tools=["smart_search", "search_tables"],
        use_cases=["了解规程结构", "确定搜索范围"],
        cli_command="toc",
        expected_params={"reg_id": "string"},
    ),
    "smart_search": ToolMetadata(
        name="smart_search",
        brief="混合检索（关键词+语义）",
        category=ToolCategory.BASE,
        phase=0,
        priority=1,
        prerequisites=["get_toc"],
        next_tools=["read_page_range", "lookup_annotation", "resolve_reference"],
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
        next_tools=["lookup_annotation", "resolve_reference"],
        use_cases=["阅读完整页面", "获取完整上下文"],
        cli_command="read-pages",
        expected_params={
            "reg_id": "string",
            "start_page": "integer",
            "end_page": "integer",
        },
    ),
    # === 多跳推理工具（3个） ===
    "search_tables": ToolMetadata(
        name="search_tables",
        brief="搜索表格",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["get_toc"],
        next_tools=["get_table_by_id", "lookup_annotation"],
        use_cases=["查找特定表格", "表格内容搜索"],
        cli_command="search-tables",
        expected_params={
            "query": "string",
            "reg_id": "string",
            "chapter_scope": "string|null",
            "search_mode": "string",
            "limit": "integer",
        },
    ),
    "lookup_annotation": ToolMetadata(
        name="lookup_annotation",
        brief="追踪注释内容",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["smart_search", "search_tables"],
        next_tools=[],
        use_cases=["查找注释内容", "理解表格脚注", "追踪「见注X」"],
        cli_command="lookup-annotation",
        expected_params={
            "reg_id": "string",
            "annotation_id": "string",
            "page_hint": "integer|null",
        },
    ),
    "resolve_reference": ToolMetadata(
        name="resolve_reference",
        brief="解析交叉引用",
        category=ToolCategory.MULTI_HOP,
        phase=1,
        priority=2,
        prerequisites=["smart_search"],
        next_tools=["read_page_range"],
        use_cases=["解析「见第X章」", "解析「参见表Y」"],
        cli_command="resolve-reference",
        expected_params={"reg_id": "string", "reference_text": "string"},
    ),
    # === 上下文扩展工具（1个） ===
    "get_table_by_id": ToolMetadata(
        name="get_table_by_id",
        brief="获取完整表格（含跨页合并）",
        category=ToolCategory.CONTEXT,
        phase=2,
        priority=2,
        prerequisites=["search_tables"],
        next_tools=["lookup_annotation"],
        use_cases=["获取完整表格", "跨页表格合并"],
        cli_command="get-table",
        expected_params={
            "reg_id": "string",
            "table_id": "string",
            "include_merged": "boolean",
        },
    ),
    # === 高级分析工具（2个，可选） ===
    "find_similar_content": ToolMetadata(
        name="find_similar_content",
        brief="查找相似内容",
        category=ToolCategory.DISCOVERY,
        phase=3,
        priority=3,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["查找相似内容", "发现相关条款"],
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
        prerequisites=["get_toc"],
        next_tools=[],
        use_cases=["比较章节", "差异分析"],
        cli_command="compare-sections",
        expected_params={
            "reg_id": "string",
            "section_a": "string",
            "section_b": "string",
            "include_tables": "boolean",
        },
    ),
}


# ==================== 工作流定义 ====================

TOOL_WORKFLOWS: dict[str, list[str]] = {
    "简单查询": ["get_toc", "smart_search", "read_page_range"],
    "表格查询": ["get_toc", "search_tables", "get_table_by_id", "lookup_annotation"],
    "引用追踪": ["get_toc", "smart_search", "resolve_reference", "read_page_range"],
    "深度探索": [
        "get_toc",
        "smart_search",
        "read_page_range",
        "lookup_annotation",
        "resolve_reference",
    ],
}

# ==================== 使用建议 ====================

TOOL_TIPS: list[str] = [
    "先用 get_toc 了解规程结构，确定搜索范围",
    "smart_search 时务必指定 chapter_scope 参数缩小范围",
    "搜索结果不完整时用 read_page_range 获取完整上下文",
    "遇到「见注X」时用 lookup_annotation 追踪注释",
    "遇到「见第X章」时用 resolve_reference 解析引用",
    "跨页表格需用 get_table_by_id 获取完整内容",
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


def get_enabled_tools(include_advanced: bool = False) -> list[str]:
    """获取启用的工具列表

    Args:
        include_advanced: 是否包含高级分析工具，默认 False

    Returns:
        启用的工具名称列表
    """
    tools = CORE_TOOLS.copy()
    if include_advanced:
        tools.extend(ADVANCED_TOOLS)
    return tools


def get_enabled_tool_metadata(include_advanced: bool = False) -> dict[str, ToolMetadata]:
    """获取启用的工具元数据

    Args:
        include_advanced: 是否包含高级分析工具，默认 False

    Returns:
        工具名称到元数据的映射（仅包含启用的工具）
    """
    enabled = get_enabled_tools(include_advanced)
    return {name: meta for name, meta in TOOL_METADATA.items() if name in enabled}
