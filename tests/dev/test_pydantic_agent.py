"""PydanticAIAgent 测试

验证 Pydantic AI v1.0+ 实现的正确性。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from regreader.agents.base import AgentResponse


class TestPydanticAIAgentInit:
    """测试 Agent 初始化"""

    def test_model_resolution_anthropic(self):
        """测试 Anthropic 模型名称解析"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    # 测试各种 Claude 模型名称
                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = None

                    assert agent._resolve_model("claude-sonnet-4-20250514") == "anthropic:claude-sonnet-4-20250514"
                    assert agent._resolve_model("claude-3-5-haiku") == "anthropic:claude-3-5-haiku"
                    assert agent._resolve_model("claude-opus-4") == "anthropic:claude-opus-4"

    def test_model_resolution_openai(self):
        """测试 OpenAI 模型名称解析"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = None

                    assert agent._resolve_model("gpt-4o") == "openai:gpt-4o"
                    assert agent._resolve_model("gpt-4-turbo") == "openai:gpt-4-turbo"
                    assert agent._resolve_model("o1-preview") == "openai:o1-preview"

    def test_model_resolution_google(self):
        """测试 Google 模型名称解析"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = None

                    assert agent._resolve_model("gemini-1.5-pro") == "google-gla:gemini-1.5-pro"
                    assert agent._resolve_model("gemini-2.0-flash") == "google-gla:gemini-2.0-flash"

    def test_model_resolution_with_provider(self):
        """测试已带 provider 前缀的模型名称"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = None

                    # 已经有 provider 前缀，应该直接返回
                    assert agent._resolve_model("anthropic:claude-3-5-sonnet") == "anthropic:claude-3-5-sonnet"
                    assert agent._resolve_model("openai:gpt-4o") == "openai:gpt-4o"


class TestPydanticAIAgentSystemPrompt:
    """测试系统提示词构建"""

    def test_system_prompt_without_reg_id(self):
        """测试不带 reg_id 的系统提示词"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent
                    from regreader.agents.prompts import SYSTEM_PROMPT

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = None

                    prompt = agent._build_system_prompt()
                    assert prompt == SYSTEM_PROMPT
                    assert "当前规程上下文" not in prompt

    def test_system_prompt_with_reg_id(self):
        """测试带 reg_id 的系统提示词"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent
                    from regreader.agents.prompts import SYSTEM_PROMPT

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent.reg_id = "angui_2024"

                    prompt = agent._build_system_prompt()
                    assert SYSTEM_PROMPT in prompt
                    assert "当前规程上下文" in prompt
                    assert "angui_2024" in prompt


class TestSourceExtraction:
    """测试来源信息提取"""

    def test_extract_sources_from_dict(self):
        """测试从字典中提取来源"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._sources = []

                    content = {"source": "angui_2024:p85", "text": "some content"}
                    agent._extract_sources_from_content(content)

                    assert "angui_2024:p85" in agent._sources

    def test_extract_sources_from_nested_dict(self):
        """测试从嵌套字典中提取来源"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._sources = []

                    content = {
                        "results": [
                            {"source": "angui_2024:p85", "text": "content 1"},
                            {"source": "angui_2024:p86", "text": "content 2"},
                        ]
                    }
                    agent._extract_sources_from_content(content)

                    assert "angui_2024:p85" in agent._sources
                    assert "angui_2024:p86" in agent._sources

    def test_extract_sources_from_json_string(self):
        """测试从 JSON 字符串中提取来源"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._sources = []

                    content = '{"source": "angui_2024:p90", "text": "json content"}'
                    agent._extract_sources_from_content(content)

                    assert "angui_2024:p90" in agent._sources


class TestMessageHistory:
    """测试消息历史管理"""

    def test_initial_message_count(self):
        """测试初始消息数量为 0"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._message_history = []

                    assert agent.get_message_count() == 0

    def test_get_message_history_returns_copy(self):
        """测试获取消息历史返回副本"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._message_history = ["msg1", "msg2"]

                    history = agent.get_message_history()
                    assert history == ["msg1", "msg2"]

                    # 修改返回的列表不应影响原始历史
                    history.append("msg3")
                    assert agent.get_message_count() == 2


class TestAgentProperties:
    """测试 Agent 属性"""

    def test_name_property(self):
        """测试 name 属性"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    assert agent.name == "PydanticAIAgent"

    def test_model_property(self):
        """测试 model 属性"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._model_name = "anthropic:claude-3-5-sonnet"
                    assert agent.model == "anthropic:claude-3-5-sonnet"


@pytest.mark.asyncio
class TestAgentReset:
    """测试 Agent 重置功能"""

    async def test_reset_clears_history(self):
        """测试重置清空历史"""
        with patch("grid_code.agents.pydantic_agent.HAS_PYDANTIC_AI", True):
            with patch("grid_code.agents.pydantic_agent.MCPServerStdio"):
                with patch("grid_code.agents.pydantic_agent.Agent"):
                    from regreader.agents.pydantic_agent import PydanticAIAgent

                    agent = PydanticAIAgent.__new__(PydanticAIAgent)
                    agent._message_history = ["msg1", "msg2"]
                    agent._tool_calls = [{"name": "test"}]
                    agent._sources = ["source1"]

                    await agent.reset()

                    assert agent._message_history == []
                    assert agent._tool_calls == []
                    assert agent._sources == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
