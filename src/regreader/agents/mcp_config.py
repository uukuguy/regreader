"""MCP Server 共享配置

统一管理三个 Agent 框架的 MCP Server 连接配置。

所有 Agent 都通过 stdio 模式连接到 RegReader MCP Server，
此模块提供共享的配置常量和工厂函数，避免重复定义。
"""

import sys

# MCP Server 名称（用于工具命名前缀：mcp__{SERVER_NAME}__<tool_name>）
MCP_SERVER_NAME = "gridcode"

# MCP Server 启动参数
MCP_SERVER_ARGS = ["-m", "regreader.cli", "serve", "--transport", "stdio"]


def get_mcp_command() -> str:
    """获取 Python 解释器路径

    Returns:
        当前 Python 解释器的完整路径
    """
    return sys.executable


def get_mcp_stdio_config() -> dict:
    """获取 Claude Agent SDK 格式的 MCP 配置

    用于 ClaudeAgentOptions 的 mcp_servers 参数。

    Returns:
        MCP Server 配置字典

    Example:
        >>> options = ClaudeAgentOptions(
        ...     mcp_servers=get_mcp_stdio_config(),
        ...     ...
        ... )
    """
    return {
        MCP_SERVER_NAME: {
            "type": "stdio",
            "command": get_mcp_command(),
            "args": MCP_SERVER_ARGS,
        }
    }


def get_tool_name(tool: str) -> str:
    """生成完整的 MCP 工具名称

    Args:
        tool: 工具短名称，如 "get_toc"

    Returns:
        完整工具名称，如 "mcp__gridcode__get_toc"

    Example:
        >>> get_tool_name("smart_search")
        'mcp__gridcode__smart_search'
    """
    return f"mcp__{MCP_SERVER_NAME}__{tool}"
