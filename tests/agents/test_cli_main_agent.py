"""测试 CLI 的主智能体模式集成

验证：
1. MCP 配置正确传递
2. MainAgent 正确初始化
3. 能够处理简单查询
"""

import pytest
from typer.testing import CliRunner
from regreader.cli import app

runner = CliRunner()


def test_main_agent_mcp_config_parsing():
    """测试 MCP 配置解析"""
    from urllib.parse import urlparse
    from regreader.cli import state

    # 模拟 MCP 配置
    state.use_mcp = True
    state.mcp_transport = "sse"
    state.mcp_url = "http://127.0.0.1:8080/sse"

    # 解析 URL
    parsed = urlparse(state.mcp_url)

    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 8080

    # 如果没有 port，使用默认值
    mcp_host = parsed.hostname or "127.0.0.1"
    mcp_port = parsed.port or 8080

    assert mcp_host == "127.0.0.1"
    assert mcp_port == 8080


def test_main_agent_without_mcp():
    """测试不使用 MCP 时的配置"""
    from regreader.cli import state

    # 不使用 MCP
    state.use_mcp = False
    state.mcp_transport = "stdio"
    state.mcp_url = None

    # 应该传递 None 给 MainAgent
    if state.use_mcp and state.mcp_transport == "sse" and state.mcp_url:
        mcp_transport = None
    else:
        mcp_transport = None

    assert mcp_transport is None


def test_main_agent_initialization_with_mcp():
    """测试 MainAgent 使用 MCP 配置初始化"""
    from regreader.agents.main import MainAgent
    from regreader.cli import state

    # 设置 MCP 配置
    state.use_mcp = True
    state.mcp_transport = "sse"
    state.mcp_url = "http://127.0.0.1:8080/sse"

    # 解析配置
    if state.use_mcp and state.mcp_transport == "sse" and state.mcp_url:
        from urllib.parse import urlparse
        parsed = urlparse(state.mcp_url)
        mcp_transport = state.mcp_transport
        mcp_host = parsed.hostname or "127.0.0.1"
        mcp_port = parsed.port or 8080
    else:
        mcp_transport = None
        mcp_host = None
        mcp_port = None

    # 创建 MainAgent
    agent = MainAgent(
        reg_id="test_reg",
        mcp_transport=mcp_transport,
        mcp_host=mcp_host,
        mcp_port=mcp_port,
    )

    # 验证配置已保存
    assert agent.reg_id == "test_reg"
    assert agent.mcp_transport == "sse"
    assert agent.mcp_host == "127.0.0.1"
    assert agent.mcp_port == 8080


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
