"""Subagent 配置定义

定义 SubagentType、SubagentConfig 及各 Subagent 的预定义配置。
"""

from dataclasses import dataclass, field
from enum import Enum


class SubagentType(str, Enum):
    """Subagent 类型枚举"""

    SEARCH = "search"
    """搜索代理：文档搜索与导航"""

    TABLE = "table"
    """表格代理：表格搜索与提取"""

    REFERENCE = "reference"
    """引用代理：交叉引用解析"""

    DISCOVERY = "discovery"
    """发现代理：高级语义分析（可选）"""


@dataclass
class SubagentConfig:
    """Subagent 配置

    定义单个 Subagent 的工具、提示词和行为参数。
    此配置在三个框架实现间共享。

    Attributes:
        agent_type: Subagent 类型
        name: 显示名称
        description: 描述说明
        tools: MCP 工具名列表
        system_prompt: 系统提示词
        capabilities: 能力列表（用于路由匹配）
        keywords: 触发关键词（用于意图识别）
        priority: 优先级（1=高，2=中，3=低）
        enabled: 是否启用
        max_iterations: 最大工具调用迭代
    """

    agent_type: SubagentType
    """Subagent 类型"""

    name: str
    """显示名称（如「搜索专家」）"""

    description: str
    """描述说明"""

    tools: list[str]
    """MCP 工具名列表"""

    system_prompt: str = ""
    """系统提示词（由 prompts 模块生成）"""

    capabilities: list[str] = field(default_factory=list)
    """能力列表

    用于 QueryAnalyzer 判断 Subagent 是否适合处理某查询。
    如：['regulation_discovery', 'chapter_navigation', 'content_search']
    """

    keywords: list[str] = field(default_factory=list)
    """触发关键词

    用于快速意图识别。支持正则表达式。
    如：['查找', '搜索', '哪里', '什么是']
    """

    priority: int = 2
    """优先级（1=高，2=中，3=低）

    当多个 Subagent 匹配时，优先调用高优先级的。
    """

    enabled: bool = True
    """是否启用"""

    max_iterations: int = 5
    """最大工具调用迭代次数"""

    def __post_init__(self):
        """验证配置"""
        if not self.tools:
            raise ValueError(f"Subagent {self.name} must have at least one tool")
        if self.priority not in (1, 2, 3):
            raise ValueError(f"Priority must be 1, 2, or 3, got {self.priority}")


# ==================== 预定义配置 ====================

SEARCH_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.SEARCH,
    name="SearchAgent",
    description="文档搜索与导航专家，负责规程发现、目录导航和内容搜索",
    tools=[
        "list_regulations",
        "get_toc",
        "smart_search",
        "read_page_range",
    ],
    capabilities=[
        "regulation_discovery",
        "chapter_navigation",
        "content_search",
        "page_retrieval",
    ],
    keywords=[
        "查找",
        "搜索",
        "哪里",
        "什么是",
        "规定",
        "要求",
        "如何",
        "怎么",
        "处理",
        "措施",
    ],
    priority=1,  # 高优先级，作为默认回退
    enabled=True,
    max_iterations=5,
)

TABLE_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.TABLE,
    name="TableAgent",
    description="表格处理专家，负责表格搜索、跨页合并和注释追踪",
    tools=[
        "search_tables",
        "get_table_by_id",
        "lookup_annotation",
    ],
    capabilities=[
        "table_search",
        "table_extraction",
        "annotation_lookup",
        "cross_page_merge",
    ],
    keywords=[
        "表格",
        "表",
        r"表\d+",
        r"表\s*\d+[-]\d+",
        "清单",
        "列表",
        "注释",
        "备注",
        "注[0-9一二三四五六七八九十]",
    ],
    priority=2,
    enabled=True,
    max_iterations=5,
)

REFERENCE_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.REFERENCE,
    name="ReferenceAgent",
    description="引用追踪专家，负责交叉引用解析和引用内容提取",
    tools=[
        "resolve_reference",
        "lookup_annotation",
        "read_page_range",
    ],
    capabilities=[
        "reference_resolution",
        "annotation_tracking",
        "cross_link_follow",
    ],
    keywords=[
        "见",
        "参见",
        "参照",
        r"第[一二三四五六七八九十\d]+章",
        r"见第.+章",
        r"见表.+",
        "附录",
        r"第[一二三四五六七八九十\d]+条",
    ],
    priority=2,
    enabled=True,
    max_iterations=5,
)

DISCOVERY_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.DISCOVERY,
    name="DiscoveryAgent",
    description="语义分析专家，负责相似内容发现和章节比较",
    tools=[
        "find_similar_content",
        "compare_sections",
    ],
    capabilities=[
        "similarity_search",
        "section_comparison",
        "semantic_analysis",
    ],
    keywords=[
        "相似",
        "类似",
        "比较",
        "区别",
        "差异",
        "对比",
        "相关",
    ],
    priority=3,  # 低优先级
    enabled=False,  # 默认禁用
    max_iterations=3,
)


# 配置注册表
SUBAGENT_CONFIGS: dict[SubagentType, SubagentConfig] = {
    SubagentType.SEARCH: SEARCH_AGENT_CONFIG,
    SubagentType.TABLE: TABLE_AGENT_CONFIG,
    SubagentType.REFERENCE: REFERENCE_AGENT_CONFIG,
    SubagentType.DISCOVERY: DISCOVERY_AGENT_CONFIG,
}


def get_enabled_configs() -> list[SubagentConfig]:
    """获取所有启用的 Subagent 配置

    Returns:
        启用的配置列表，按优先级排序
    """
    configs = [c for c in SUBAGENT_CONFIGS.values() if c.enabled]
    return sorted(configs, key=lambda c: c.priority)


def get_config(agent_type: SubagentType) -> SubagentConfig:
    """获取指定类型的配置

    Args:
        agent_type: Subagent 类型

    Returns:
        对应的配置

    Raises:
        KeyError: 类型不存在
    """
    return SUBAGENT_CONFIGS[agent_type]


def get_all_tools() -> list[str]:
    """获取所有 Subagent 使用的工具（去重）

    Returns:
        工具名列表
    """
    tools = set()
    for config in SUBAGENT_CONFIGS.values():
        if config.enabled:
            tools.update(config.tools)
    return list(tools)
