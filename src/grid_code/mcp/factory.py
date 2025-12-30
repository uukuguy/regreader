"""工具工厂模块

根据配置创建适当的工具实现（本地直接访问或 MCP 远程调用）。
"""

import os
from typing import TYPE_CHECKING, Literal

from loguru import logger

from grid_code.config import get_settings

if TYPE_CHECKING:
    from grid_code.mcp.protocol import GridCodeToolsProtocol


def create_tools(
    use_mcp: bool | None = None,
    transport: Literal["stdio", "sse"] | None = None,
    server_url: str | None = None,
) -> "GridCodeToolsProtocol":
    """创建 GridCode 工具实例

    根据配置决定使用本地直接访问还是 MCP 远程调用。

    配置优先级：
    1. 函数参数（显式指定）
    2. 环境变量 GRIDCODE_USE_MCP / GRIDCODE_MCP_TRANSPORT / GRIDCODE_MCP_SERVER_URL
    3. 配置文件设置
    4. 默认值（use_mcp=False）

    Args:
        use_mcp: 是否使用 MCP 模式。None 表示使用配置/环境变量
        transport: MCP 传输方式 ("stdio" 或 "sse")
        server_url: SSE 模式的服务器 URL

    Returns:
        工具实例（本地 GridCodeTools 或 MCP 适配器）

    Example:
        # 使用默认配置
        tools = create_tools()

        # 强制使用 MCP stdio 模式
        tools = create_tools(use_mcp=True, transport="stdio")

        # 连接外部 MCP 服务器
        tools = create_tools(
            use_mcp=True,
            transport="sse",
            server_url="http://localhost:8080/sse"
        )
    """
    settings = get_settings()

    # 确定是否使用 MCP 模式
    if use_mcp is None:
        # 检查环境变量（pydantic settings 会自动读取 GRIDCODE_USE_MCP_MODE）
        env_use_mcp = os.environ.get("GRIDCODE_USE_MCP", "").lower()
        if env_use_mcp in ("true", "1", "yes"):
            use_mcp = True
        elif env_use_mcp in ("false", "0", "no"):
            use_mcp = False
        else:
            # 使用配置文件设置
            use_mcp = settings.use_mcp_mode

    if not use_mcp:
        logger.debug("使用本地直接访问模式")
        from grid_code.mcp.tools import GridCodeTools

        return GridCodeTools()

    # 确定传输方式
    if transport is None:
        env_transport = os.environ.get("GRIDCODE_MCP_TRANSPORT", "").lower()
        if env_transport in ("stdio", "sse"):
            transport = env_transport  # type: ignore
        else:
            transport = settings.mcp_transport  # type: ignore

    # 确定服务器 URL（SSE 模式）
    if transport == "sse" and server_url is None:
        server_url = os.environ.get("GRIDCODE_MCP_SERVER_URL")
        if not server_url:
            server_url = settings.mcp_server_url
        if not server_url:
            # 使用默认地址
            server_url = f"http://{settings.mcp_host}:{settings.mcp_port}/sse"

    logger.info(f"使用 MCP 模式: transport={transport}, url={server_url or '(stdio)'}")

    # 创建 MCP 适配器
    from grid_code.mcp.adapter import GridCodeMCPToolsAdapter

    return GridCodeMCPToolsAdapter(transport=transport, server_url=server_url)


class ToolsContext:
    """工具上下文管理器

    提供便捷的上下文管理，自动处理资源清理。

    Example:
        with ToolsContext(use_mcp=True) as tools:
            result = tools.get_toc("angui_2024")
    """

    def __init__(
        self,
        use_mcp: bool | None = None,
        transport: Literal["stdio", "sse"] | None = None,
        server_url: str | None = None,
    ):
        """初始化工具上下文

        Args:
            use_mcp: 是否使用 MCP 模式
            transport: MCP 传输方式
            server_url: SSE 模式的服务器 URL
        """
        self.use_mcp = use_mcp
        self.transport = transport
        self.server_url = server_url
        self._tools: "GridCodeToolsProtocol | None" = None

    def __enter__(self) -> "GridCodeToolsProtocol":
        self._tools = create_tools(
            use_mcp=self.use_mcp,
            transport=self.transport,
            server_url=self.server_url,
        )
        return self._tools

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 清理资源（如果需要）
        self._tools = None
        return False
