"""Subagent 配置定义

定义 SubagentType、SubagentConfig 及各 Subagent 的预定义配置。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SubagentType(str, Enum):
    """Subagent 类型枚举"""

    # 领域子代理（Domain Subagents）
    REGSEARCH = "regsearch"
    """规程检索代理：整合搜索、表格、引用、发现功能的领域子代理"""

    # 内部组件子代理（作为 REGSEARCH 的内部组件）
    SEARCH = "search"
    """搜索代理：文档搜索与导航"""

    TABLE = "table"
    """表格代理：表格搜索与提取"""

    REFERENCE = "reference"
    """引用代理：交叉引用解析"""

    DISCOVERY = "discovery"
    """发现代理：高级语义分析（可选）"""

    # 支撑子代理（Support Subagents，预留）
    EXEC = "exec"
    """执行代理：脚本执行（预留）"""

    VALIDATOR = "validator"
    """验证代理：结果验证（预留）"""


@dataclass
class SubagentConfig:
    """Subagent 配置（纯数据配置，无执行逻辑）

    定义单个 Subagent 的工具、提示词和行为参数。
    此配置在三个框架实现间共享。

    关键变更：
    - description 字段成为核心，用于 LLM 理解子智能体的能力和适用场景
    - 移除 capabilities 和 keywords（不再使用硬编码路由）
    - 移除 Bash+FS 相关字段（work_dir、readable_dirs 等）

    Attributes:
        agent_type: Subagent 类型
        name: 显示名称
        description: 详细功能描述（用于 LLM 理解，至少 50 字符）
        tools: MCP 工具白名单
        system_prompt_template: 系统提示词模板
        priority: 优先级（1=高，2=中，3=低）
        enabled: 是否启用
        max_iterations: 最大工具调用迭代
    """

    agent_type: SubagentType
    """Subagent 类型"""

    name: str
    """显示名称（如「搜索专家」）"""

    description: str
    """详细功能描述（关键字段！）

    用于 LLM 理解子智能体的能力和适用场景。
    应包含：
    - 擅长处理的查询类型
    - 典型使用场景（示例查询）
    - 不适用场景（避免误用）
    - 可用工具列表

    最少 50 字符，建议 200-500 字符。
    """

    tools: list[str]
    """MCP 工具白名单

    子智能体只能访问此列表中的工具（安全控制）。
    """

    system_prompt_template: str = ""
    """系统提示词模板

    定义子智能体的行为、工作流程和输出格式。
    可包含占位符（如 {reg_id}、{chapter_scope}）。
    """

    priority: int = 2
    """优先级（1=高，2=中，3=低）

    用于框架需要时的回退顺序（如 LangGraph 的条件边）。
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
        if not self.description or len(self.description) < 50:
            raise ValueError(
                f"Subagent {self.name} must have a detailed description (at least 50 chars), "
                f"got {len(self.description)} chars"
            )


# ==================== 预定义配置 ====================

# 领域子代理配置
REGSEARCH_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.REGSEARCH,
    name="RegSearchAgent",
    description="""规程文档检索领域专家，整合搜索、表格、引用、发现功能的综合代理。

**擅长处理**：
- 规程发现与目录导航（"有哪些规程？"、"第六章讲了什么？"）
- 关键词搜索与内容检索（"母线失压如何处理？"、"查找故障处理措施"）
- 表格搜索与提取（"表6-2的内容"、"查找所有故障类型表格"）
- 注释追踪（"注1的内容"、"查找所有注释"）
- 交叉引用解析（"见第六章"、"参照附录A"）
- 语义相似内容发现（"查找类似的处理方法"）
- 章节结构分析与比较（"比较2.1.4和2.1.5的区别"）

**典型场景**：
- "母线失压如何处理？" → 搜索相关章节内容
- "表6-2中注1的内容是什么？" → 表格查找 + 注释追踪
- "见第六章的具体内容" → 引用解析 + 内容提取
- "查找所有关于故障处理的表格" → 表格语义搜索

**可用工具**（16个）：
- 基础工具：list_regulations, get_toc, smart_search, read_page_range
- 多跳工具：lookup_annotation, search_tables, resolve_reference
- 上下文工具：search_annotations, get_table_by_id, get_block_with_context
- 发现工具：find_similar_content, compare_sections
- 导航工具：get_tool_guide, get_chapter_structure, read_chapter_content

**注意**：这是一个综合领域代理，适合处理复杂的多步骤查询。对于简单查询，框架会自动选择更专注的内部组件代理（SearchAgent/TableAgent/ReferenceAgent）。""",
    tools=[
        # BASE 工具
        "list_regulations",
        "get_toc",
        "smart_search",
        "read_page_range",
        # MULTI_HOP 工具
        "lookup_annotation",
        "search_tables",
        "resolve_reference",
        # CONTEXT 工具
        "search_annotations",
        "get_table_by_id",
        "get_block_with_context",
        # DISCOVERY 工具
        "find_similar_content",
        "compare_sections",
        # NAVIGATION 工具
        "get_tool_guide",
        "get_chapter_structure",
        "read_chapter_content",
    ],
    priority=1,
    enabled=True,
    max_iterations=10,
)

# 内部组件子代理配置
SEARCH_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.SEARCH,
    name="SearchAgent",
    description="""文档搜索与导航专家，专注于规程发现、目录浏览和内容检索。

**擅长处理**：
- 规程列表查询（"有哪些规程？"、"列出所有可用的规程文档"）
- 目录结构导航（"第六章有哪些小节？"、"显示目录"）
- 关键词内容搜索（"母线失压如何处理？"、"查找故障处理措施"）
- 页面范围读取（"读取第10-15页"、"查看第三章内容"）
- 章节内容提取（"第2.1.4节的内容"）

**典型场景**：
- "母线失压如何处理？" → 使用 smart_search 搜索相关内容
- "第六章讲了什么？" → 使用 get_toc 获取目录，然后 read_chapter_content 读取内容
- "有哪些规程文档？" → 使用 list_regulations 列出所有规程
- "读取第10-15页" → 使用 read_page_range 读取指定页面

**不适用场景**：
- 表格提取 → 使用 TableAgent
- 注释追踪 → 使用 TableAgent 的 lookup_annotation
- 交叉引用解析 → 使用 ReferenceAgent
- 语义相似搜索 → 使用 DiscoveryAgent

**可用工具**（4个）：
- list_regulations: 列出所有规程
- get_toc: 获取目录结构
- smart_search: 智能搜索（支持章节范围、块类型过滤）
- read_page_range: 读取页面范围""",
    tools=[
        "list_regulations",
        "get_toc",
        "smart_search",
        "read_page_range",
    ],
    priority=1,  # 高优先级，作为默认回退
    enabled=True,
    max_iterations=5,
)

TABLE_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.TABLE,
    name="TableAgent",
    description="""表格处理专家，专注于表格搜索、提取和注释追踪。

**擅长处理**：
- 表格内容查询（"表6-2的内容"、"查找表3-1"）
- 表格语义搜索（"查找所有故障类型表格"、"搜索包含母线失压的表格"）
- 跨页表格合并（自动处理跨页表格的完整提取）
- 注释内容查询（"注1的内容"、"查找注释3"）
- 表格注释关联（"表6-2中注1的内容"）

**典型场景**：
- "表6-2的内容是什么？" → 使用 search_tables 查找表格，然后 get_table_by_id 提取完整内容
- "表6-2中注1的内容" → 先获取表格，再使用 lookup_annotation 查找注释
- "查找所有关于故障处理的表格" → 使用 search_tables 进行语义搜索
- "注3的具体说明" → 使用 lookup_annotation 查找注释内容

**不适用场景**：
- 普通文本搜索 → 使用 SearchAgent
- 交叉引用解析（"见第六章"）→ 使用 ReferenceAgent
- 章节内容提取 → 使用 SearchAgent

**可用工具**（3个）：
- search_tables: 表格搜索（支持关键词和语义搜索）
- get_table_by_id: 通过ID获取完整表格（自动处理跨页合并）
- lookup_annotation: 查找注释内容（支持页面提示）""",
    tools=[
        "search_tables",
        "get_table_by_id",
        "lookup_annotation",
    ],
    priority=2,
    enabled=True,
    max_iterations=5,
)

REFERENCE_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.REFERENCE,
    name="ReferenceAgent",
    description="""引用追踪专家，专注于交叉引用解析和引用内容提取。

**擅长处理**：
- 章节引用解析（"见第六章"、"参照第2.1.4节"）
- 表格引用解析（"见表6-2"、"参见表3-1"）
- 附录引用解析（"见附录A"、"参照附录B"）
- 条款引用解析（"第三条的内容"、"见第十五条"）
- 引用内容提取（解析引用后自动提取目标内容）

**典型场景**：
- "见第六章的具体内容" → 使用 resolve_reference 解析引用，然后 read_page_range 提取内容
- "参照表6-2的说明" → 解析引用到表格，然后获取表格内容
- "第三条规定了什么？" → 解析条款引用，提取对应内容
- "附录A的详细信息" → 解析附录引用，读取附录内容

**不适用场景**：
- 普通关键词搜索 → 使用 SearchAgent
- 表格内容查询（无引用文本）→ 使用 TableAgent
- 注释查询 → 使用 TableAgent

**可用工具**（3个）：
- resolve_reference: 解析交叉引用（支持章节、表格、附录、条款等）
- lookup_annotation: 查找注释（部分引用可能指向注释）
- read_page_range: 读取引用目标的页面内容""",
    tools=[
        "resolve_reference",
        "lookup_annotation",
        "read_page_range",
    ],
    priority=2,
    enabled=True,
    max_iterations=5,
)

DISCOVERY_AGENT_CONFIG = SubagentConfig(
    agent_type=SubagentType.DISCOVERY,
    name="DiscoveryAgent",
    description="""语义分析专家，专注于相似内容发现和章节比较分析。

**擅长处理**：
- 相似内容发现（"查找类似的处理方法"、"还有哪些相关的规定？"）
- 章节内容比较（"比较2.1.4和2.1.5的区别"、"对比两个章节"）
- 语义关联分析（"查找与母线失压相关的所有内容"）
- 主题聚类查询（"总结所有故障处理措施的共同点"）

**典型场景**：
- "查找类似的故障处理方法" → 使用 find_similar_content 进行语义搜索
- "比较2.1.4和2.1.5节的异同" → 使用 compare_sections 进行章节对比
- "还有哪些与母线相关的规定？" → 使用 find_similar_content 发现相关内容
- "总结不同章节中关于应急处理的差异" → 结合 compare_sections 进行对比分析

**不适用场景**：
- 精确关键词搜索 → 使用 SearchAgent
- 表格内容查询 → 使用 TableAgent
- 交叉引用解析 → 使用 ReferenceAgent
- 特定页面读取 → 使用 SearchAgent

**可用工具**（2个）：
- find_similar_content: 基于语义的相似内容发现
- compare_sections: 章节内容对比分析

**注意**：此代理默认禁用，适用于需要深度语义分析的场景。对于普通查询，使用 SearchAgent 即可。""",
    tools=[
        "find_similar_content",
        "compare_sections",
    ],
    priority=3,  # 低优先级
    enabled=False,  # 默认禁用
    max_iterations=3,
)


# 配置注册表
SUBAGENT_CONFIGS: dict[SubagentType, SubagentConfig] = {
    # 领域子代理
    SubagentType.REGSEARCH: REGSEARCH_AGENT_CONFIG,
    # 内部组件子代理
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
