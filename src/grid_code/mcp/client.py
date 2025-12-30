"""MCP 客户端

提供连接 GridCode MCP Server 的客户端功能。
支持 stdio（子进程）和 SSE（HTTP）两种传输方式。
支持 LangGraph 和 Pydantic AI 等框架使用。
"""

import sys
from contextlib import AsyncExitStack
from typing import Any, Literal

from loguru import logger

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class GridCodeMCPClient:
    """GridCode MCP 客户端

    支持两种传输方式连接到 GridCode MCP Server：
    - stdio: 自动启动子进程（适合本地开发和测试）
    - sse: 连接外部 HTTP 服务（适合生产环境和验证 SSE 功能）

    使用方式:
        # stdio 模式（默认）
        async with GridCodeMCPClient() as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_toc", {"reg_id": "angui_2024"})

        # SSE 模式
        async with GridCodeMCPClient(
            transport="sse",
            server_url="http://localhost:8080/sse"
        ) as client:
            result = await client.call_tool("smart_search", {"query": "母线失压", "reg_id": "angui_2024"})
    """

    def __init__(
        self,
        transport: Literal["stdio", "sse"] = "stdio",
        server_url: str | None = None,
    ):
        """初始化 MCP 客户端

        Args:
            transport: 传输方式
                - "stdio": 自动启动 MCP Server 子进程
                - "sse": 连接外部 MCP Server（需提供 server_url）
            server_url: SSE 模式时的服务器 URL，如 "http://localhost:8080/sse"

        Raises:
            ValueError: SSE 模式未提供 server_url
        """
        if transport == "sse" and not server_url:
            raise ValueError("SSE 模式需要提供 server_url 参数")

        self.transport = transport
        self.server_url = server_url
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self._tools_cache: list[dict] | None = None

    async def connect(self) -> None:
        """连接到 GridCode MCP Server

        根据 transport 设置选择连接方式：
        - stdio: 启动 MCP Server 子进程
        - sse: 连接外部 HTTP SSE 服务
        """
        if self.transport == "stdio":
            await self._connect_stdio()
        else:
            await self._connect_sse()

        # 获取可用工具
        response = await self.session.list_tools()
        self._tools_cache = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]

        logger.debug(
            f"Connected to MCP server ({self.transport}) with tools: "
            f"{[t['name'] for t in self._tools_cache]}"
        )

    async def _connect_stdio(self) -> None:
        """通过 stdio 传输连接（启动子进程）"""
        # GridCode MCP Server 启动参数
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "grid_code.cli", "serve", "--transport", "stdio"],
            env=None,
        )

        # 创建 stdio 传输
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        stdio_read, stdio_write = stdio_transport

        # 创建会话
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(stdio_read, stdio_write)
        )

        # 初始化会话
        await self.session.initialize()

    async def _connect_sse(self) -> None:
        """通过 SSE 传输连接（HTTP 长连接）"""
        import httpx

        # 创建自定义 httpx 客户端工厂，禁用系统代理
        # 避免系统代理（如 ClashX）导致 SSE 连接失败
        def create_no_proxy_client(**kwargs) -> httpx.AsyncClient:
            # 保留 MCP SDK 传入的参数，但禁用代理
            return httpx.AsyncClient(proxy=None, trust_env=False, **kwargs)

        # 创建 SSE 传输
        sse_transport = await self.exit_stack.enter_async_context(
            sse_client(self.server_url, httpx_client_factory=create_no_proxy_client)
        )
        sse_read, sse_write = sse_transport

        # 创建会话
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(sse_read, sse_write)
        )

        # 初始化会话
        await self.session.initialize()

    async def disconnect(self) -> None:
        """断开连接"""
        await self.exit_stack.aclose()
        self.session = None
        self._tools_cache = None

    async def __aenter__(self) -> "GridCodeMCPClient":
        """异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.disconnect()

    async def list_tools(self) -> list[dict]:
        """获取可用工具列表

        Returns:
            工具定义列表，每个工具包含 name, description, input_schema
        """
        if self._tools_cache is not None:
            return self._tools_cache

        if self.session is None:
            raise RuntimeError("MCP client not connected")

        response = await self.session.list_tools()
        self._tools_cache = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]
        return self._tools_cache

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用 MCP 工具

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if self.session is None:
            raise RuntimeError("MCP client not connected")

        logger.debug(f"Calling MCP tool: {name} with args: {arguments}")

        result = await self.session.call_tool(name, arguments)

        # 解析结果内容
        if result.content:
            # MCP 工具结果可能包含多个内容块
            contents = []
            for content in result.content:
                if hasattr(content, "text"):
                    contents.append(content.text)
                elif hasattr(content, "data"):
                    contents.append(content.data)

            # 如果只有一个内容块，尝试解析为 JSON
            if len(contents) == 1:
                import json
                try:
                    return json.loads(contents[0])
                except (json.JSONDecodeError, TypeError):
                    return contents[0]

            return contents

        return None

    def get_tools_for_anthropic(self) -> list[dict]:
        """获取 Anthropic API 格式的工具定义

        Returns:
            Anthropic tool 格式的工具列表
        """
        if self._tools_cache is None:
            raise RuntimeError("MCP client not connected or tools not loaded")

        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in self._tools_cache
        ]

    def get_tools_for_langchain(self) -> list[dict]:
        """获取 LangChain 格式的工具定义

        LangChain 使用的格式与 Anthropic 类似。

        Returns:
            LangChain tool 格式的工具列表
        """
        return self.get_tools_for_anthropic()
