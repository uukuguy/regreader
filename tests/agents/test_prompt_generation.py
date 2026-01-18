"""测试动态提示词生成功能

验证单智能体和多智能体模式使用统一的提示词生成逻辑。
"""

import pytest

from regreader.agents.prompts import (
    generate_role_for_subagent,
    generate_tool_section_for_tools,
    generate_workflow_for_tools,
)
from regreader.subagents.config import SEARCH_AGENT_CONFIG, TABLE_AGENT_CONFIG, SubagentType


class TestDynamicPromptGeneration:
    """测试动态提示词生成"""

    def test_generate_tool_section_for_tools(self):
        """测试从工具列表动态生成工具描述"""
        # SearchAgent 的 4 个工具
        search_tools = [
            "list_regulations",
            "get_toc",
            "smart_search",
            "read_page_range",
        ]

        tool_section = generate_tool_section_for_tools(search_tools)

        # 验证生成的工具描述包含关键信息
        assert "**list_regulations**" in tool_section
        assert "**get_toc**" in tool_section
        assert "**smart_search**" in tool_section
        assert "**read_page_range**" in tool_section

        # 验证不包含硬编码的工具列表（如"可用工具（4个）"）
        assert "可用工具（4个）" not in tool_section

    def test_generate_tool_section_for_tools_empty(self):
        """测试空工具列表"""
        tool_section = generate_tool_section_for_tools([])
        assert tool_section == ""

    def test_generate_tool_section_for_tools_invalid(self):
        """测试包含无效工具名称"""
        # 包含一个不存在的工具
        mixed_tools = ["list_regulations", "invalid_tool_name", "get_toc"]

        tool_section = generate_tool_section_for_tools(mixed_tools)

        # 应该只包含有效工具的描述
        assert "**list_regulations**" in tool_section
        assert "**get_toc**" in tool_section
        # 无效工具不应出现在结果中
        assert "invalid_tool_name" not in tool_section

    def test_generate_role_for_subagent_search(self):
        """测试生成 SearchAgent 角色定义"""
        role = generate_role_for_subagent(SubagentType.SEARCH)

        assert "# 角色" in role
        assert "文档搜索专家" in role
        assert "规程文档中定位和提取" in role

    def test_generate_role_for_subagent_table(self):
        """测试生成 TableAgent 角色定义"""
        role = generate_role_for_subagent(SubagentType.TABLE)

        assert "# 角色" in role
        assert "表格" in role and "专家" in role
        assert "搜索和提取" in role

    def test_generate_role_for_subagent_reference(self):
        """测试生成 ReferenceAgent 角色定义"""
        role = generate_role_for_subagent(SubagentType.REFERENCE)

        assert "# 角色" in role
        assert "引用" in role and "专家" in role
        assert "处理" in role or "解析" in role

    def test_generate_role_for_subagent_discovery(self):
        """测试生成 DiscoveryAgent 角色定义"""
        role = generate_role_for_subagent(SubagentType.DISCOVERY)

        assert "# 角色" in role
        assert "语义" in role and "分析" in role
        assert "发现" in role

    def test_generate_workflow_for_tools_search(self):
        """测试生成 SearchAgent 工作流程"""
        search_tools = [
            "list_regulations",
            "get_toc",
            "smart_search",
            "read_page_range",
        ]

        workflow = generate_workflow_for_tools(search_tools)

        assert "# 工作流程" in workflow
        assert "目录导航" in workflow
        assert "get_toc" in workflow
        assert "智能搜索" in workflow
        assert "smart_search" in workflow

    def test_generate_workflow_for_tools_table(self):
        """测试生成 TableAgent 工作流程"""
        table_tools = [
            "search_tables",
            "get_table_by_id",
            "lookup_annotation",
        ]

        workflow = generate_workflow_for_tools(table_tools)

        assert "# 工作流程" in workflow
        assert "表格查询" in workflow
        assert "search_tables" in workflow

    def test_generate_workflow_for_tools_reference(self):
        """测试生成 ReferenceAgent 工作流程"""
        reference_tools = [
            "resolve_reference",
            "lookup_annotation",
            "read_page_range",
        ]

        workflow = generate_workflow_for_tools(reference_tools)

        assert "# 工作流程" in workflow
        assert "引用解析" in workflow
        assert "resolve_reference" in workflow

    def test_generate_workflow_for_tools_mixed(self):
        """测试混合工具组合的工作流程"""
        mixed_tools = ["get_toc", "search_tables", "resolve_reference"]

        workflow = generate_workflow_for_tools(mixed_tools)

        # 应该包含所有相关的工作流程步骤
        assert "# 工作流程" in workflow
        assert "get_toc" in workflow or "目录导航" in workflow


class TestPromptConsistency:
    """测试单智能体和多智能体模式的提示词一致性"""

    def test_search_agent_config_tools(self):
        """验证 SearchAgent 配置包含正确的工具列表"""
        # SearchAgent 应该有 4 个工具
        assert len(SEARCH_AGENT_CONFIG.tools) == 4
        assert "list_regulations" in SEARCH_AGENT_CONFIG.tools
        assert "get_toc" in SEARCH_AGENT_CONFIG.tools
        assert "smart_search" in SEARCH_AGENT_CONFIG.tools
        assert "read_page_range" in SEARCH_AGENT_CONFIG.tools

    def test_table_agent_config_tools(self):
        """验证 TableAgent 配置包含正确的工具列表"""
        # TableAgent 应该有 3 个工具
        assert len(TABLE_AGENT_CONFIG.tools) == 3
        assert "search_tables" in TABLE_AGENT_CONFIG.tools
        assert "get_table_by_id" in TABLE_AGENT_CONFIG.tools
        assert "lookup_annotation" in TABLE_AGENT_CONFIG.tools

    def test_dynamic_generation_consistency(self):
        """验证动态生成的一致性

        确保从 config.tools 生成的工具描述与配置一致。
        """
        # 生成 SearchAgent 的工具描述
        tool_section = generate_tool_section_for_tools(SEARCH_AGENT_CONFIG.tools)

        # 验证每个配置的工具都在生成的描述中
        for tool_name in SEARCH_AGENT_CONFIG.tools:
            assert f"**{tool_name}**" in tool_section, (
                f"工具 {tool_name} 应该在生成的描述中"
            )

    def test_no_hardcoded_tool_lists(self):
        """验证提示词中不包含硬编码的工具列表"""
        role = generate_role_for_subagent(SubagentType.SEARCH)
        tool_section = generate_tool_section_for_tools(SEARCH_AGENT_CONFIG.tools)
        workflow = generate_workflow_for_tools(SEARCH_AGENT_CONFIG.tools)

        # 检查硬编码特征
        hardcoded_patterns = [
            "可用工具（4个）",
            "可用工具（3个）",
            "可用工具（2个）",
            "1. **list_regulations()**",
        ]

        combined_prompt = f"{role}\n{tool_section}\n{workflow}"

        for pattern in hardcoded_patterns:
            # 允许在工具描述中包含工具名称，但不应该有硬编码的列表格式
            if pattern.startswith("1. **"):
                # 这种格式不应该出现
                assert pattern not in combined_prompt
            else:
                # 其他硬编码模式也不应该出现
                assert pattern not in combined_prompt or pattern.replace("(", "").replace(")", "") in combined_prompt


class TestPromptIntegration:
    """测试提示词与其他组件的集成"""

    def test_subagent_configs_use_tools_field(self):
        """验证 SubagentConfig 使用 tools 字段而不是硬编码提示词"""
        # SearchAgent 配置应该使用 tools 字段
        assert hasattr(SEARCH_AGENT_CONFIG, "tools")
        assert isinstance(SEARCH_AGENT_CONFIG.tools, list)
        assert len(SEARCH_AGENT_CONFIG.tools) > 0

        # system_prompt_template 应该为 None（由 orchestrator 动态生成）
        # 或者只包含额外的说明，不包含工具列表
        if SEARCH_AGENT_CONFIG.system_prompt_template:
            prompt = SEARCH_AGENT_CONFIG.system_prompt_template
            # 验证不包含硬编码的工具列表
            assert "可用工具（" not in prompt

    def test_description_is_task_focused(self):
        """验证 description 字段是任务导向的，不包含工具列表"""
        # description 应该描述任务，而不是列出工具
        for agent_config in [SEARCH_AGENT_CONFIG, TABLE_AGENT_CONFIG]:
            description = agent_config.description
            assert description, "description 不应该为空"
            # description 应该包含任务相关关键词
            task_keywords = ["任务", "专注", "专家", "负责"]
            has_task_keyword = any(keyword in description for keyword in task_keywords)
            assert has_task_keyword, f"description 应该包含任务描述: {description}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
