"""MCP Connection Pool Manager

Provides shared MCP connections for subagents to avoid repeated initialization.
"""

import asyncio
from typing import Any

from loguru import logger

from regreader.mcp.client import MCPClient


class MCPConnectionPool:
    """MCP 连接池管理器

    管理共享的 MCP 连接，避免每个子智能体都创建新连接。
    """

    def __init__(self):
        self._connections: dict[str, MCPClient] = {}
        self._lock = asyncio.Lock()

    async def get_connection(
        self,
        connection_id: str = "default",
        **kwargs: Any
    ) -> MCPClient:
        """获取或创建 MCP 连接

        Args:
            connection_id: 连接标识符
            **kwargs: 传递给 MCPClient 的参数

        Returns:
            MCPClient 实例
        """
        async with self._lock:
            if connection_id not in self._connections:
                logger.info(f"创建新的 MCP 连接: {connection_id}")
                self._connections[connection_id] = await self._create_connection(**kwargs)
            return self._connections[connection_id]

    async def _create_connection(self, **kwargs: Any) -> MCPClient:
        """创建新的 MCP 连接

        Args:
            **kwargs: 传递给 MCPClient 的参数

        Returns:
            已初始化的 MCPClient 实例
        """
        client = MCPClient(**kwargs)
        await client.connect()
        return client

    async def close_all(self):
        """关闭所有连接"""
        async with self._lock:
            for connection_id, client in self._connections.items():
                logger.info(f"关闭 MCP 连接: {connection_id}")
                await client.close()
            self._connections.clear()
