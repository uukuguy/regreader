"""从 ToolMetadata 动态生成系统提示词工具段落

单一数据源设计：所有工具描述信息均来自 tool_metadata.py，
本模块负责将其转换为系统提示词格式。

支持三种详细程度：
- full: 完整版，包含详细参数说明和使用场景
- optimized: 优化版，精简但保留关键信息（推荐）
- simple: 最简版，仅工具名和简述
"""

from grid_code.mcp.tool_metadata import (
    CATEGORY_INFO,
    CATEGORY_ORDER,
    TOOL_METADATA,
    TOOL_TIPS,
    TOOL_WORKFLOWS,
    ToolCategory,
    get_enabled_tool_metadata,
    get_tools_by_category,
)


def generate_tool_section(
    mode: str = "optimized",
    include_advanced: bool = False,
) -> str:
    """生成工具文档段落

    Args:
        mode: 详细程度 - "full", "optimized", "simple"
        include_advanced: 是否包含高级分析工具

    Returns:
        格式化的工具文档字符串
    """
    if mode == "simple":
        return _generate_simple_tool_list(include_advanced)
    elif mode == "full":
        return _generate_full_tool_docs(include_advanced)
    else:  # optimized
        return _generate_optimized_tool_docs(include_advanced)


def _generate_simple_tool_list(include_advanced: bool = False) -> str:
    """生成最简工具列表"""
    tools = get_enabled_tool_metadata(include_advanced)
    lines = ["# 可用工具"]
    for i, (name, meta) in enumerate(tools.items(), 1):
        lines.append(f"{i}. {name}() - {meta.brief}")
    return "\n".join(lines)


def _generate_optimized_tool_docs(include_advanced: bool = False) -> str:
    """生成优化版工具文档"""
    tools = get_enabled_tool_metadata(include_advanced)
    count = len(tools)

    lines = [f"# 可用工具（{count}个）"]

    for i, (name, meta) in enumerate(tools.items(), 1):
        # 构建参数列表
        if meta.params_doc:
            params = ", ".join(
                f"{p}?" if meta.expected_params.get(p, "").endswith("|null") else p
                for p in meta.params_doc.keys()
            )
            lines.append(f"{i}. {name}({params}) - {meta.brief}")
        else:
            lines.append(f"{i}. {name}() - {meta.brief}")

    return "\n".join(lines)


def _generate_full_tool_docs(include_advanced: bool = False) -> str:
    """生成完整版工具文档"""
    tools_by_cat = get_tools_by_category()
    enabled_tools = get_enabled_tool_metadata(include_advanced)
    count = len(enabled_tools)

    lines = [f"# 可用工具（{count}个核心工具）"]

    for cat in CATEGORY_ORDER:
        if cat not in tools_by_cat:
            continue

        cat_tools = [t for t in tools_by_cat[cat] if t.name in enabled_tools]
        if not cat_tools:
            continue

        cat_info = CATEGORY_INFO.get(cat.value, {})
        cat_name = cat_info.get("name", cat.value)
        lines.append(f"\n## {cat_name}（{len(cat_tools)}个）\n")

        for meta in cat_tools:
            # 工具签名
            if meta.params_doc:
                params = ", ".join(
                    f"{p}?" if meta.expected_params.get(p, "").endswith("|null") else p
                    for p in meta.params_doc.keys()
                )
                lines.append(f"**{meta.name}({params})** - {meta.brief}")
            else:
                lines.append(f"**{meta.name}()** - {meta.brief}")

            # 完整描述
            if meta.description and meta.description != meta.brief:
                lines.append(f"   - {meta.description}")

            # 参数说明
            if meta.params_doc:
                for param, desc in meta.params_doc.items():
                    optional = "（可选）" if meta.expected_params.get(param, "").endswith("|null") else ""
                    lines.append(f"   - {param}{optional}: {desc}")

            # 工具链信息
            if meta.prerequisites:
                lines.append(f"   - 前置: {', '.join(meta.prerequisites)}")
            if meta.next_tools:
                lines.append(f"   - 后续: {', '.join(meta.next_tools)}")

            lines.append("")  # 空行分隔

    return "\n".join(lines)


def generate_workflow_section() -> str:
    """从 TOOL_WORKFLOWS 生成工作流文档"""
    lines = ["## 标准工作流"]

    for name, tools in TOOL_WORKFLOWS.items():
        flow = " → ".join(tools)
        lines.append(f"### {name}")
        lines.append(f"```\n{flow}\n```")
        lines.append("")

    return "\n".join(lines)


def generate_tips_section() -> str:
    """从 TOOL_TIPS 生成使用提示"""
    lines = ["# 使用提示"]
    for tip in TOOL_TIPS:
        lines.append(f"- {tip}")
    return "\n".join(lines)


def generate_multihop_triggers() -> str:
    """生成多跳触发条件说明"""
    return """# 多跳触发条件
- 「见注X」「方案A」→ lookup_annotation(annotation_id, page_hint)
- 「见第X章」「参见表Y」→ resolve_reference(reference_text)
- 表格 is_truncated=true → get_table_by_id(table_id)"""
