"""ClaudeAgent 测试

验证 Claude Agent SDK 实现的正确性。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from regreader.agents.base import AgentResponse


class TestClaudeAgentInit:
    """测试 Agent 初始化"""

    def test_init_with_defaults(self):
        """测试默认初始化"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent()

                    assert agent._model == "claude-sonnet-4-20250514"
                    assert agent._enable_hooks is True
                    assert agent.reg_id is None

    def test_init_with_reg_id(self):
        """测试带 reg_id 的初始化"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent(reg_id="angui_2024")

                    assert agent.reg_id == "angui_2024"

    def test_init_without_api_key(self):
        """测试缺少 API Key 时抛出异常"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key=None,
                )

                from regreader.agents.claude_agent import ClaudeAgent

                with pytest.raises(ValueError, match="未配置 Anthropic API Key"):
                    ClaudeAgent()

    def test_init_with_custom_model(self):
        """测试自定义模型"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent(model="claude-opus-4-20250514")

                    assert agent._model == "claude-opus-4-20250514"


class TestClaudeAgentSystemPrompt:
    """测试系统提示词构建"""

    def test_system_prompt_without_reg_id(self):
        """测试不带 reg_id 的系统提示词"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.prompts import SYSTEM_PROMPT

                    agent = ClaudeAgent()

                    prompt = agent._build_system_prompt()
                    assert prompt == SYSTEM_PROMPT
                    assert "当前规程上下文" not in prompt

    def test_system_prompt_with_reg_id(self):
        """测试带 reg_id 的系统提示词"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.prompts import SYSTEM_PROMPT

                    agent = ClaudeAgent(reg_id="angui_2024")

                    prompt = agent._build_system_prompt()
                    assert SYSTEM_PROMPT in prompt
                    assert "当前规程上下文" in prompt
                    assert "angui_2024" in prompt


class TestMCPConfiguration:
    """测试 MCP 配置"""

    def test_mcp_config_structure(self):
        """测试 MCP 配置结构"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent()

                    config = agent._get_mcp_config()

                    assert "gridcode" in config
                    assert config["gridcode"]["type"] == "stdio"
                    assert "-m" in config["gridcode"]["args"]
                    assert "grid_code.cli" in config["gridcode"]["args"]

    def test_allowed_tools_format(self):
        """测试允许的工具列表格式"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent()

                    tools = agent._get_allowed_tools()

                    # 所有工具应该以 mcp__gridcode__ 开头
                    for tool in tools:
                        assert tool.startswith("mcp__gridcode__")


class TestHooksConfiguration:
    """测试 Hooks 配置"""

    def test_hooks_when_enabled(self):
        """测试启用 Hooks"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    with patch("grid_code.agents.claude_agent.HookMatcher") as mock_matcher:
                        mock_matcher.return_value = MagicMock()

                        from regreader.agents.claude_agent import ClaudeAgent

                        agent = ClaudeAgent(enable_hooks=True)

                        hooks = agent._build_hooks()

                        assert hooks is not None
                        assert "PreToolUse" in hooks
                        assert "PostToolUse" in hooks

    def test_hooks_when_disabled(self):
        """测试禁用 Hooks"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent(enable_hooks=False)

                    hooks = agent._build_hooks()

                    assert hooks is None


class TestSourceExtraction:
    """测试来源信息提取"""

    def test_extract_sources_from_dict(self):
        """测试从字典中提取来源"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    result = {"source": "angui_2024:p85", "text": "content"}
                    agent._extract_sources(result, session)

                    assert "angui_2024:p85" in session.sources

    def test_extract_sources_from_nested(self):
        """测试从嵌套结构中提取来源"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    result = {
                        "results": [
                            {"source": "angui_2024:p85"},
                            {"source": "angui_2024:p86"},
                        ]
                    }
                    agent._extract_sources(result, session)

                    assert "angui_2024:p85" in session.sources
                    assert "angui_2024:p86" in session.sources

    def test_extract_sources_from_json_string(self):
        """测试从 JSON 字符串中提取来源"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime
                    import json

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    result = json.dumps({"source": "angui_2024:p100"})
                    agent._extract_sources(result, session)

                    assert "angui_2024:p100" in session.sources


class TestAgentProperties:
    """测试 Agent 属性"""

    def test_name_property(self):
        """测试 name 属性"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent()
                    assert agent.name == "ClaudeAgent"

    def test_model_property(self):
        """测试 model 属性"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent

                    agent = ClaudeAgent()
                    assert agent.model == "claude-sonnet-4-20250514"


class TestSessionManagement:
    """测试会话管理"""

    def test_get_sessions(self):
        """测试获取会话列表"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from regreader.agents.claude_agent import ClaudeAgent

                agent = ClaudeAgent()

                # 初始状态无会话
                sessions = agent.get_sessions()
                assert sessions == []

    def test_get_session_info_not_found(self):
        """测试获取不存在的会话信息"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from regreader.agents.claude_agent import ClaudeAgent

                agent = ClaudeAgent()

                info = agent.get_session_info("non-existent")
                assert info is None


@pytest.mark.asyncio
class TestAgentReset:
    """测试 Agent 重置功能"""

    async def test_reset_default_session(self):
        """测试重置默认会话"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from regreader.agents.claude_agent import ClaudeAgent

                agent = ClaudeAgent()

                # 创建会话
                session = agent._session_manager.get_or_create()
                session.add_source("test-source")

                # 重置
                await agent.reset()

                # 验证会话被重置
                sessions = agent.get_sessions()
                assert len(sessions) == 0

    async def test_reset_all_sessions(self):
        """测试重置所有会话"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )

                from regreader.agents.claude_agent import ClaudeAgent

                agent = ClaudeAgent()

                # 创建多个会话
                agent._session_manager.get_or_create("session-1")
                agent._session_manager.get_or_create("session-2")

                assert len(agent.get_sessions()) == 2

                # 重置所有
                await agent.reset_all()

                assert len(agent.get_sessions()) == 0


class TestAssembledText:
    """测试文本组装"""

    def test_get_assembled_text_empty(self):
        """测试空工具调用时的文本组装"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    result = agent._get_assembled_text(session)
                    assert result == ""

    def test_get_assembled_text_with_output(self):
        """测试有工具输出时的文本组装"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    # 添加工具调用
                    session.add_tool_call(
                        name="read_page",
                        input_data={"page": 1},
                        output={"content_markdown": "# Page Content"}
                    )

                    result = agent._get_assembled_text(session)
                    assert result == "# Page Content"

    def test_get_assembled_text_string_output(self):
        """测试字符串输出的文本组装"""
        with patch("grid_code.agents.claude_agent.HAS_CLAUDE_SDK", True):
            with patch("grid_code.agents.claude_agent.get_settings") as mock_settings:
                mock_settings.return_value = MagicMock(
                    default_model="claude-sonnet-4-20250514",
                    anthropic_api_key="test-key",
                )
                with patch("grid_code.agents.claude_agent.SessionManager"):
                    from regreader.agents.claude_agent import ClaudeAgent
                    from regreader.agents.session import SessionState
                    from datetime import datetime

                    agent = ClaudeAgent()
                    session = SessionState(
                        session_id="test",
                        created_at=datetime.now(),
                        last_active=datetime.now(),
                    )

                    session.add_tool_call(
                        name="smart_search",
                        input_data={"query": "test"},
                        output="Search results here"
                    )

                    result = agent._get_assembled_text(session)
                    assert result == "Search results here"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
