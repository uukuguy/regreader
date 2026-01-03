"""MCP Server 模块

提供 MCP Server 创建、客户端连接、工具适配器、提示词生成等功能。
"""

from .adapter import GridCodeMCPToolsAdapter
from .client import GridCodeMCPClient
from .factory import ToolsContext, create_tools
from .prompt_generator import (
    generate_multihop_triggers,
    generate_tips_section,
    generate_tool_section,
    generate_workflow_section,
)
from .protocol import GridCodeToolsProtocol
from .server import create_mcp_server
from .tool_metadata import (
    CATEGORY_INFO,
    CATEGORY_NAMES,
    CATEGORY_ORDER,
    TOOL_METADATA,
    TOOL_TIPS,
    TOOL_WORKFLOWS,
    ToolCategory,
    ToolMetadata,
    get_category_info,
    get_tool_metadata,
    get_tools_by_category,
)
from .tools import GridCodeTools

__all__ = [
    # Server
    "create_mcp_server",
    # Client
    "GridCodeMCPClient",
    # Tools
    "GridCodeTools",
    "GridCodeToolsProtocol",
    "GridCodeMCPToolsAdapter",
    "create_tools",
    "ToolsContext",
    # Metadata
    "ToolCategory",
    "ToolMetadata",
    "TOOL_METADATA",
    "TOOL_WORKFLOWS",
    "TOOL_TIPS",
    "CATEGORY_INFO",
    "CATEGORY_NAMES",
    "CATEGORY_ORDER",
    "get_tools_by_category",
    "get_tool_metadata",
    "get_category_info",
    # Prompt Generator
    "generate_tool_section",
    "generate_workflow_section",
    "generate_tips_section",
    "generate_multihop_triggers",
]
