"""MCP 连接管理器测试

测试 MCPConnectionConfig 和 MCPConnectionManager 的功能。
"""

import pytest

from regreader.agents.shared.mcp_connection import (
    MCPConnectionConfig,
    MCPConnectionManager,
    configure_mcp,
    get_mcp_manager,
)


class TestMCPConnectionConfig:
    """MCPConnectionConfig 测试"""

    def test_default_config(self):
        """默认配置应为 stdio 模式"""
        config = MCPConnectionConfig()
        assert config.transport == "stdio"
        assert config.server_url is None
        assert config.server_name == "gridcode"

    def test_stdio_factory(self):
        """stdio 工厂方法"""
        config = MCPConnectionConfig.stdio()
        assert config.transport == "stdio"
        assert config.server_url is None

    def test_sse_factory(self):
        """sse 工厂方法"""
        url = "http://localhost:8080/sse"
        config = MCPConnectionConfig.sse(url)
        assert config.transport == "sse"
        assert config.server_url == url

    def test_sse_factory_default_url(self):
        """sse 工厂方法默认 URL"""
        config = MCPConnectionConfig.sse()
        assert config.transport == "sse"
        assert config.server_url == "http://127.0.0.1:8080/sse"

    def test_from_settings(self):
        """从全局配置创建"""
        config = MCPConnectionConfig.from_settings()
        # 默认设置应该是 stdio
        assert config.transport in ("stdio", "sse")


class TestMCPConnectionManager:
    """MCPConnectionManager 测试"""

    def test_singleton_pattern(self):
        """单例模式测试"""
        # 重置单例
        MCPConnectionManager._instance = None

        manager1 = get_mcp_manager()
        manager2 = get_mcp_manager()
        assert manager1 is manager2

    def test_config_override(self):
        """配置覆盖测试"""
        # 重置单例
        MCPConnectionManager._instance = None

        config1 = MCPConnectionConfig.stdio()
        manager1 = get_mcp_manager(config1)
        assert manager1.config.transport == "stdio"

        # 再次获取时传入新配置应该更新
        config2 = MCPConnectionConfig.sse("http://localhost:9090/sse")
        manager2 = get_mcp_manager(config2)
        assert manager2.config.transport == "sse"
        assert manager2.config.server_url == "http://localhost:9090/sse"

    def test_get_claude_sdk_config_stdio(self):
        """获取 Claude SDK 配置 - stdio 模式"""
        MCPConnectionManager._instance = None

        config = MCPConnectionConfig.stdio()
        manager = get_mcp_manager(config)
        sdk_config = manager.get_claude_sdk_config()

        assert "gridcode" in sdk_config
        assert sdk_config["gridcode"]["type"] == "stdio"
        assert "command" in sdk_config["gridcode"]
        assert "args" in sdk_config["gridcode"]

    def test_get_claude_sdk_config_sse(self):
        """获取 Claude SDK 配置 - sse 模式（应回退到 stdio）"""
        MCPConnectionManager._instance = None

        config = MCPConnectionConfig.sse("http://localhost:8080/sse")
        manager = get_mcp_manager(config)
        sdk_config = manager.get_claude_sdk_config()

        # Claude SDK 不支持 SSE，应回退到 stdio
        assert "gridcode" in sdk_config
        assert sdk_config["gridcode"]["type"] == "stdio"

    def test_get_langgraph_client_stdio(self):
        """获取 LangGraph 客户端 - stdio 模式"""
        MCPConnectionManager._instance = None

        config = MCPConnectionConfig.stdio()
        manager = get_mcp_manager(config)
        client = manager.get_langgraph_client()

        assert client.transport == "stdio"

    def test_get_langgraph_client_sse(self):
        """获取 LangGraph 客户端 - sse 模式"""
        MCPConnectionManager._instance = None

        url = "http://localhost:8080/sse"
        config = MCPConnectionConfig.sse(url)
        manager = get_mcp_manager(config)
        client = manager.get_langgraph_client()

        assert client.transport == "sse"
        assert client.server_url == url


class TestConfigureMCP:
    """configure_mcp 便捷函数测试"""

    def test_configure_stdio(self):
        """配置 stdio 模式"""
        MCPConnectionManager._instance = None

        configure_mcp(transport="stdio")
        manager = get_mcp_manager()
        assert manager.config.transport == "stdio"

    def test_configure_sse(self):
        """配置 sse 模式"""
        MCPConnectionManager._instance = None

        url = "http://localhost:9090/sse"
        configure_mcp(transport="sse", server_url=url)
        manager = get_mcp_manager()
        assert manager.config.transport == "sse"
        assert manager.config.server_url == url


# 清理测试后的单例状态
@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试后重置单例"""
    yield
    MCPConnectionManager._instance = None
