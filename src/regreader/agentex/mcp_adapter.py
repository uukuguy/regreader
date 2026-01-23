"""MCP 工具适配器

将 MCP Server 工具包装为 AgentEx Tool，实现统一的工具接口。
"""

from __future__ import annotations

from typing import Any

from .tools import Tool, ToolRegistry
from .types import ToolResult, Context


class MCPToolAdapter(Tool):
    """MCP 工具适配器

    将 MCP Server 的工具包装为 AgentEx Tool 接口。
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_parameters: dict[str, Any],
        mcp_client: Any,  # MCPClient 实例
    ):
        """初始化 MCP 工具适配器

        Args:
            tool_name: 工具名称
            tool_description: 工具描述
            tool_parameters: 工具参数 schema
            mcp_client: MCP 客户端实例
        """
        self._name = tool_name
        self._description = tool_description
        self._parameters = tool_parameters
        self._mcp_client = mcp_client

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def _run(self, context: Context, **kwargs: Any) -> Any:
        """调用 MCP 工具

        Args:
            context: Agent 上下文
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        result = await self._mcp_client.call_tool(self._name, kwargs)
        return result


class MCPToolRegistry:
    """MCP 工具注册表

    从 MCP Server 自动发现并注册工具到 AgentEx ToolRegistry。
    """

    def __init__(self, mcp_client: Any):
        """初始化 MCP 工具注册表

        Args:
            mcp_client: MCP 客户端实例
        """
        self._mcp_client = mcp_client
        self._registry = ToolRegistry()
        self._initialized = False

    async def initialize(self) -> "MCPToolRegistry":
        """从 MCP Server 发现并注册所有工具

        Returns:
            self（支持链式调用）
        """
        if self._initialized:
            return self

        # 获取 MCP Server 的工具列表
        tools = await self._mcp_client.list_tools()

        for tool_info in tools:
            adapter = MCPToolAdapter(
                tool_name=tool_info.get("name"),
                tool_description=tool_info.get("description", ""),
                tool_parameters=tool_info.get("inputSchema", {}),
                mcp_client=self._mcp_client,
            )
            self._registry.register(adapter)

        self._initialized = True
        return self

    @property
    def registry(self) -> ToolRegistry:
        """获取底层 ToolRegistry"""
        return self._registry

    def get_tool(self, name: str) -> Tool | None:
        """获取工具"""
        return self._registry.get(name)

    def list_tools(self) -> list[Tool]:
        """列出所有工具"""
        return self._registry.list_tools()

    def generate_schema(self) -> list[dict[str, Any]]:
        """生成工具 schema"""
        return self._registry.generate_schema()


async def create_mcp_tool_registry(mcp_client: Any) -> MCPToolRegistry:
    """便捷函数：创建并初始化 MCP 工具注册表

    Args:
        mcp_client: MCP 客户端实例

    Returns:
        初始化完成的 MCPToolRegistry
    """
    registry = MCPToolRegistry(mcp_client)
    await registry.initialize()
    return registry
