"""MCP 连接统一管理

统一管理三个 Agent 框架的 MCP 连接配置和创建。
支持 stdio（子进程）和 SSE（共享服务）两种传输方式。

配置优先级：
1. 显式传入参数
2. 环境变量 GRIDCODE_MCP_*
3. RegReaderSettings 配置
4. 默认值

Usage:
    # 方式1：使用默认配置（从 settings 读取）
    manager = get_mcp_manager()
    claude_config = manager.get_claude_sdk_config()

    # 方式2：显式配置
    config = MCPConnectionConfig(transport="sse", server_url="http://localhost:8080/sse")
    manager = get_mcp_manager(config)

    # 方式3：全局配置
    configure_mcp(transport="sse", server_url="http://localhost:8080/sse")
    agent = ClaudeAgent(reg_id="angui_2024")  # 自动使用 SSE
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

if TYPE_CHECKING:
    from regreader.mcp.client import RegReaderMCPClient


# MCP Server 常量（与 mcp_config.py 保持一致）
MCP_SERVER_NAME = "gridcode"
MCP_SERVER_ARGS = ["-m", "regreader.cli", "serve", "--transport", "stdio"]


@dataclass
class MCPConnectionConfig:
    """MCP 连接配置

    统一配置源，支持从多种来源创建配置。

    Attributes:
        transport: 传输方式，"stdio"（子进程）或 "sse"（共享服务）
        server_url: SSE 服务器 URL（SSE 模式必需）
        server_name: MCP 服务器名称，用于工具命名前缀
        stdio_command: stdio 模式的可执行命令
        stdio_args: stdio 模式的命令参数
        auto_reconnect: 连接断开时是否自动重连
        connect_timeout: 连接超时时间（秒）
    """

    transport: Literal["stdio", "sse"] = "stdio"
    server_url: str | None = None
    server_name: str = MCP_SERVER_NAME
    stdio_command: str | None = None
    stdio_args: list[str] = field(default_factory=lambda: MCP_SERVER_ARGS.copy())
    auto_reconnect: bool = True
    connect_timeout: float = 30.0

    def __post_init__(self):
        """验证配置"""
        if self.transport == "sse" and not self.server_url:
            # SSE 模式需要 URL，尝试从 settings 获取默认值
            from regreader.config import get_settings

            settings = get_settings()
            if settings.mcp_server_url:
                self.server_url = settings.mcp_server_url
            else:
                self.server_url = f"http://{settings.mcp_host}:{settings.mcp_port}/sse"
            logger.debug(f"SSE 模式使用默认 URL: {self.server_url}")

    @classmethod
    def from_settings(cls) -> MCPConnectionConfig:
        """从全局配置创建

        读取 RegReaderSettings 中的 MCP 相关配置。

        Returns:
            MCPConnectionConfig 实例
        """
        from regreader.config import get_settings

        settings = get_settings()

        return cls(
            transport=settings.mcp_transport,  # type: ignore
            server_url=settings.mcp_server_url,
        )

    @classmethod
    def stdio(cls) -> MCPConnectionConfig:
        """创建 stdio 模式配置

        Returns:
            stdio 模式的 MCPConnectionConfig
        """
        return cls(transport="stdio")

    @classmethod
    def sse(cls, server_url: str | None = None) -> MCPConnectionConfig:
        """创建 SSE 模式配置

        Args:
            server_url: SSE 服务器 URL，如果不提供则使用默认值

        Returns:
            SSE 模式的 MCPConnectionConfig
        """
        return cls(transport="sse", server_url=server_url)

    def get_stdio_command(self) -> str:
        """获取 stdio 模式的可执行命令

        Returns:
            Python 解释器路径
        """
        return self.stdio_command or sys.executable


class MCPConnectionManager:
    """MCP 连接管理器

    为不同的 Agent 框架提供统一的 MCP 连接配置和创建方法。
    使用单例模式确保全局配置一致性。

    支持的框架：
    - Claude Agent SDK: get_claude_sdk_config()
    - Pydantic AI: get_pydantic_mcp_server()
    - LangGraph: get_langgraph_client()

    Usage:
        manager = get_mcp_manager()

        # Claude Agent SDK
        options = ClaudeAgentOptions(mcp_servers=manager.get_claude_sdk_config())

        # Pydantic AI
        agent = Agent(toolsets=[manager.get_pydantic_mcp_server()])

        # LangGraph
        client = manager.get_langgraph_client()
    """

    _instance: MCPConnectionManager | None = None

    def __init__(self, config: MCPConnectionConfig | None = None):
        """初始化连接管理器

        Args:
            config: MCP 连接配置，如果不提供则从 settings 读取
        """
        self.config = config or MCPConnectionConfig.from_settings()
        self._client: RegReaderMCPClient | None = None
        self._connected = False

        logger.debug(
            f"MCPConnectionManager 初始化: transport={self.config.transport}, "
            f"server_url={self.config.server_url}"
        )

    @classmethod
    def get_instance(
        cls, config: MCPConnectionConfig | None = None
    ) -> MCPConnectionManager:
        """获取单例实例

        Args:
            config: 可选的新配置。如果提供，会更新现有实例的配置。

        Returns:
            MCPConnectionManager 实例
        """
        if cls._instance is None:
            cls._instance = cls(config)
        elif config is not None:
            # 如果提供了新配置，更新现有实例
            cls._instance.config = config
            cls._instance._client = None
            cls._instance._connected = False
            logger.debug(f"MCPConnectionManager 配置已更新: {config.transport}")
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例

        主要用于测试或需要重新配置的场景。
        """
        if cls._instance is not None:
            cls._instance = None
            logger.debug("MCPConnectionManager 实例已重置")

    # ==================== Claude Agent SDK 适配 ====================

    def get_claude_sdk_config(self) -> dict[str, Any]:
        """获取 Claude Agent SDK 格式的 MCP 配置

        用于 ClaudeAgentOptions 的 mcp_servers 参数。

        支持两种传输模式：
        - stdio: 子进程模式，启动本地 MCP Server
        - sse: SSE 模式，连接远程 MCP Server

        Returns:
            MCP Server 配置字典

        Example:
            >>> manager = get_mcp_manager()
            >>> options = ClaudeAgentOptions(
            ...     mcp_servers=manager.get_claude_sdk_config(),
            ...     ...
            ... )
        """
        if self.config.transport == "sse":
            if not self.config.server_url:
                raise ValueError("SSE 模式需要 server_url")
            return {
                self.config.server_name: {
                    "type": "sse",
                    "url": self.config.server_url,
                }
            }

        # stdio 模式
        return {
            self.config.server_name: {
                "type": "stdio",
                "command": self.config.get_stdio_command(),
                "args": self.config.stdio_args,
            }
        }

    # ==================== Pydantic AI 适配 ====================

    def get_pydantic_mcp_server(self):
        """获取 Pydantic AI 的 MCP Server 对象

        返回 MCPServerStdio 或 MCPServerSSE。

        Returns:
            MCPServerStdio 或 MCPServerSSE 实例

        Example:
            >>> manager = get_mcp_manager()
            >>> agent = Agent(
            ...     model="anthropic:claude-sonnet-4-20250514",
            ...     toolsets=[manager.get_pydantic_mcp_server()],
            ... )
        """
        if self.config.transport == "stdio":
            return self._create_pydantic_stdio_server()

        # SSE 模式
        return self._create_pydantic_sse_server()

    def _create_pydantic_stdio_server(self):
        """创建 Pydantic AI 的 stdio MCP Server"""
        from pydantic_ai.mcp import MCPServerStdio

        return MCPServerStdio(
            self.config.get_stdio_command(),
            args=self.config.stdio_args,
            timeout=60.0,  # 增加初始化超时到 60 秒（用于加载嵌入模型）
            read_timeout=300.0,  # 5 分钟读取超时
        )

    def _create_pydantic_sse_server(self):
        """创建 Pydantic AI 的 SSE MCP Server

        使用 MCPServerSSE（而非已弃用的 MCPServerHTTP），
        并传入禁用代理的 httpx 客户端以避免网络问题。
        """
        import httpx
        from pydantic_ai.mcp import MCPServerSSE

        if not self.config.server_url:
            raise ValueError("SSE 模式需要 server_url")

        # 创建禁用代理的 httpx 客户端
        # 与 RegReaderMCPClient 保持一致，避免代理导致的 502 错误
        # 设置较长的超时时间，SSE 连接需要等待 LLM 响应
        http_client = httpx.AsyncClient(
            proxy=None,
            trust_env=False,
            timeout=httpx.Timeout(300.0, connect=30.0),  # 5分钟读取超时，30秒连接超时
        )

        return MCPServerSSE(
            url=self.config.server_url,
            http_client=http_client,
        )

    # ==================== LangGraph 适配 ====================

    def get_langgraph_client(self) -> RegReaderMCPClient:
        """获取 LangGraph 使用的 MCP 客户端

        LangGraph 需要手动管理连接生命周期，返回未连接的客户端。

        Returns:
            RegReaderMCPClient 实例（未连接）

        Example:
            >>> manager = get_mcp_manager()
            >>> client = manager.get_langgraph_client()
            >>> await client.connect()
            >>> tools = await client.list_tools()
        """
        from regreader.mcp.client import RegReaderMCPClient

        return RegReaderMCPClient(
            transport=self.config.transport,
            server_url=self.config.server_url,
        )

    # ==================== 通用客户端接口 ====================

    async def get_client(self) -> RegReaderMCPClient:
        """获取已连接的 MCP 客户端

        如果客户端未创建或未连接，会自动创建并连接。

        Returns:
            已连接的 RegReaderMCPClient 实例
        """
        from regreader.mcp.client import RegReaderMCPClient

        if self._client is None or not self._connected:
            self._client = RegReaderMCPClient(
                transport=self.config.transport,
                server_url=self.config.server_url,
            )
            await self._client.connect()
            self._connected = True

        return self._client

    async def close(self) -> None:
        """关闭连接"""
        if self._client is not None:
            await self._client.disconnect()
            self._client = None
            self._connected = False

    async def __aenter__(self) -> MCPConnectionManager:
        """异步上下文管理器入口"""
        await self.get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.close()


# ==================== 模块级便捷函数 ====================


def get_mcp_manager(
    config: MCPConnectionConfig | None = None,
) -> MCPConnectionManager:
    """获取全局 MCP 连接管理器

    Args:
        config: 可选的配置。如果提供，会更新全局配置。

    Returns:
        MCPConnectionManager 实例
    """
    return MCPConnectionManager.get_instance(config)


def configure_mcp(
    transport: Literal["stdio", "sse"] = "stdio",
    server_url: str | None = None,
) -> None:
    """配置全局 MCP 连接

    在程序启动时调用，影响所有后续创建的 Agent。

    Args:
        transport: 传输方式
        server_url: SSE 服务器 URL

    Example:
        # 配置 SSE 模式
        configure_mcp(transport="sse", server_url="http://localhost:8080/sse")

        # 之后创建的 Agent 都会使用 SSE 模式
        agent = ClaudeAgent(reg_id="angui_2024")
    """
    config = MCPConnectionConfig(
        transport=transport,
        server_url=server_url,
    )
    MCPConnectionManager.reset_instance()
    MCPConnectionManager.get_instance(config)
    logger.info(f"全局 MCP 配置已更新: transport={transport}, server_url={server_url}")


def reset_mcp_manager() -> None:
    """重置全局 MCP 连接管理器

    主要用于测试。
    """
    MCPConnectionManager.reset_instance()
