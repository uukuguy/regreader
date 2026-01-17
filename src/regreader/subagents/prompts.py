"""Subagent 专用提示词

为每个 Subagent 定义专注、精简的系统提示词，减少上下文开销。

设计原则：
- 工具描述由 orchestrator 动态生成（从 TOOL_METADATA）
- 本文件只定义角色和任务描述
- 保持简洁，便于维护和更新
"""

from regreader.subagents.config import SubagentType

# ==================== 角色定义 ====================

# SearchAgent 角色定义
SEARCH_AGENT_ROLE = """# 角色
你是文档搜索专家，负责在规程文档中定位和提取相关内容。"""

# TableAgent 角色定义
TABLE_AGENT_ROLE = """# 角色
你是表格处理专家，负责搜索、提取和解析规程中的表格。"""

# ReferenceAgent 角色定义
REFERENCE_AGENT_ROLE = """# 角色
你是交叉引用专家，负责解析和追踪规程中的引用关系。"""

# DiscoveryAgent 角色定义
DISCOVERY_AGENT_ROLE = """# 角色
你是语义分析专家，负责发现相关内容和进行比较分析。"""

# ==================== 任务描述 ====================

# SearchAgent 专项任务描述
SEARCH_AGENT_DESCRIPTION = """# 专项任务
专注文档搜索与导航，提供精准的内容定位服务。

# 工作重点
- 目录导航：使用 get_toc() 了解章节结构
- 智能搜索：使用 smart_search() 定位相关内容
- 内容补全：使用 read_page_range() 获取完整上下文"""

# TableAgent 专项任务描述
TABLE_AGENT_DESCRIPTION = """# 专项任务
专注表格数据提取，提供结构化的表格信息查询。

# 工作重点
- 表格搜索：使用 search_tables() 定位目标表格
- 完整获取：使用 get_table_by_id() 获取跨页完整表格
- 注释追踪：使用 lookup_annotation() 追踪表格中的注释引用"""

# ReferenceAgent 专项任务描述
REFERENCE_AGENT_DESCRIPTION = """# 专项任务
专注交叉引用解析，追踪文档间的关联关系。

# 工作重点
- 引用解析：使用 resolve_reference() 解析章节、表格等引用
- 注释追踪：使用 lookup_annotation() 追踪「注X」等注释引用
- 内容读取：使用 read_page_range() 获取被引用的完整内容"""

# DiscoveryAgent 专项任务描述
DISCOVERY_AGENT_DESCRIPTION = """# 专项任务
专注语义分析和内容发现，提供深度见解。

# 工作重点
- 相似内容查找：使用 find_similar_content() 发现相关条款
- 章节对比：使用 compare_sections() 分析章节差异"""

# ==================== 角色和任务映射 ====================

# 角色定义映射（用于 generate_role_for_subagent）
SUBAGENT_ROLES: dict[SubagentType, str] = {
    SubagentType.SEARCH: SEARCH_AGENT_ROLE,
    SubagentType.TABLE: TABLE_AGENT_ROLE,
    SubagentType.REFERENCE: REFERENCE_AGENT_ROLE,
    SubagentType.DISCOVERY: DISCOVERY_AGENT_ROLE,
}

# 任务描述映射（用于 config.description）
SUBAGENT_DESCRIPTIONS: dict[SubagentType, str] = {
    SubagentType.SEARCH: SEARCH_AGENT_DESCRIPTION,
    SubagentType.TABLE: TABLE_AGENT_DESCRIPTION,
    SubagentType.REFERENCE: REFERENCE_AGENT_DESCRIPTION,
    SubagentType.DISCOVERY: DISCOVERY_AGENT_DESCRIPTION,
}


def inject_prompt_to_config() -> None:
    """将角色和任务描述注入到 SUBAGENT_CONFIGS

    注意：
    - 只注入 description（任务描述）
    - 不注入 system_prompt_template（由 orchestrator 动态生成）
    - 工具描述由 orchestrator 从 TOOL_METADATA 动态生成

    在应用启动时调用，确保配置中包含最新的提示词。
    """
    from regreader.subagents.config import SUBAGENT_CONFIGS

    # 注入任务描述到 config.description
    for agent_type, description in SUBAGENT_DESCRIPTIONS.items():
        if agent_type in SUBAGENT_CONFIGS:
            # 使用 object.__setattr__ 绕过 frozen 限制（如果有）
            object.__setattr__(
                SUBAGENT_CONFIGS[agent_type],
                'description',
                description
            )
