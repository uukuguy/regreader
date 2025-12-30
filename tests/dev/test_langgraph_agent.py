"""LangGraphAgent 测试

验证 LangGraph StateGraph 实现的正确性。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from grid_code.agents.base import AgentResponse


class TestLangGraphAgentInit:
    """测试 Agent 初始化"""

    def test_thread_id_generation(self):
        """测试会话 ID 生成"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()

                # 验证 thread_id 格式
                assert agent.thread_id.startswith("gridcode-")
                assert len(agent.thread_id) == len("gridcode-") + 8

    def test_new_session(self):
        """测试创建新会话"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                old_thread_id = agent.thread_id

                new_thread_id = agent.new_session()

                assert new_thread_id != old_thread_id
                assert agent.thread_id == new_thread_id

    def test_switch_session(self):
        """测试切换会话"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                target_thread_id = "gridcode-test1234"

                agent.switch_session(target_thread_id)

                assert agent.thread_id == target_thread_id


class TestLangGraphAgentSystemPrompt:
    """测试系统提示词构建"""

    def test_system_prompt_without_reg_id(self):
        """测试不带 reg_id 的系统提示词"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent
                from grid_code.agents.prompts import SYSTEM_PROMPT

                agent = LangGraphAgent()

                prompt = agent._build_system_prompt()
                assert prompt == SYSTEM_PROMPT
                assert "当前规程上下文" not in prompt

    def test_system_prompt_with_reg_id(self):
        """测试带 reg_id 的系统提示词"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent
                from grid_code.agents.prompts import SYSTEM_PROMPT

                agent = LangGraphAgent(reg_id="angui_2024")

                prompt = agent._build_system_prompt()
                assert SYSTEM_PROMPT in prompt
                assert "当前规程上下文" in prompt
                assert "angui_2024" in prompt


class TestSourceExtraction:
    """测试来源信息提取"""

    def test_extract_sources_from_dict(self):
        """测试从字典中提取来源"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                agent._sources = []

                result = {"source": "angui_2024:p85", "text": "content"}
                agent._extract_sources(result)

                assert "angui_2024:p85" in agent._sources

    def test_extract_sources_from_nested(self):
        """测试从嵌套结构中提取来源"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                agent._sources = []

                result = {
                    "results": [
                        {"source": "angui_2024:p85"},
                        {"source": "angui_2024:p86"},
                    ]
                }
                agent._extract_sources(result)

                assert "angui_2024:p85" in agent._sources
                assert "angui_2024:p86" in agent._sources


class TestArgsSchemaCreation:
    """测试参数模型创建"""

    def test_create_args_schema_required_fields(self):
        """测试必填字段"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()

                schema = {
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Result limit"},
                    },
                    "required": ["query"],
                }

                model = agent._create_args_schema("search", schema)

                # 验证模型名称
                assert model.__name__ == "SearchArgs"

                # 验证字段
                assert "query" in model.model_fields
                assert "limit" in model.model_fields

    def test_create_args_schema_type_mapping(self):
        """测试类型映射"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()

                schema = {
                    "properties": {
                        "name": {"type": "string"},
                        "count": {"type": "integer"},
                        "score": {"type": "number"},
                        "active": {"type": "boolean"},
                    },
                    "required": ["name"],
                }

                model = agent._create_args_schema("test_tool", schema)

                # 验证类型映射
                annotations = model.__annotations__
                assert annotations["name"] == str


class TestAgentProperties:
    """测试 Agent 属性"""

    def test_name_property(self):
        """测试 name 属性"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                assert agent.name == "LangGraphAgent"

    def test_model_property(self):
        """测试 model 属性"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                assert agent.model == "claude-sonnet-4-20250514"


@pytest.mark.asyncio
class TestAgentReset:
    """测试 Agent 重置功能"""

    async def test_reset_generates_new_thread_id(self):
        """测试重置生成新会话 ID"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                old_thread_id = agent.thread_id

                await agent.reset()

                assert agent.thread_id != old_thread_id
                assert agent._tool_calls == []
                assert agent._sources == []


@pytest.mark.asyncio
class TestGetSessionHistory:
    """测试获取会话历史"""

    async def test_empty_history_when_no_graph(self):
        """测试无图时返回空历史"""
        with patch("grid_code.agents.langgraph_agent.ChatAnthropic"):
            with patch("grid_code.agents.langgraph_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from grid_code.agents.langgraph_agent import LangGraphAgent

                agent = LangGraphAgent()
                agent._graph = None

                history = await agent.get_session_history()
                assert history == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
