"""MCP 工具适配器

封装 GridCodeMCPClient，提供与 GridCodeTools 相同的同步接口。
使用 asyncio.run() 在同步上下文中执行异步 MCP 调用。
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from loguru import logger

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


def _no_proxy_httpx_client_factory(**kwargs) -> httpx.AsyncClient:
    """创建不使用环境代理的 httpx AsyncClient

    httpx 默认 trust_env=True 会读取 HTTP_PROXY/HTTPS_PROXY 环境变量，
    导致 SSE 请求经过代理后返回 502 Bad Gateway。
    通过设置 trust_env=False 禁用代理。
    """
    return httpx.AsyncClient(trust_env=False, **kwargs)


class GridCodeMCPToolsAdapter:
    """MCP 工具适配器

    将异步的 MCP Client 调用包装为同步接口，
    与 GridCodeTools 提供相同的方法签名。

    支持两种传输方式：
    - stdio: 自动启动子进程（每次调用启动新进程）
    - sse: 连接外部 MCP Server

    使用示例：
        # stdio 模式
        adapter = GridCodeMCPToolsAdapter(transport="stdio")

        # sse 模式
        adapter = GridCodeMCPToolsAdapter(
            transport="sse",
            server_url="http://localhost:8080/sse"
        )

        # 调用工具（同步接口）
        result = adapter.get_toc("angui_2024")
    """

    def __init__(
        self,
        transport: Literal["stdio", "sse"] = "stdio",
        server_url: str | None = None,
    ):
        """初始化 MCP 工具适配器

        Args:
            transport: 传输方式，"stdio" 或 "sse"
            server_url: SSE 模式时的服务器 URL，如 "http://localhost:8080/sse"

        Raises:
            ValueError: SSE 模式需要提供 server_url
        """
        if transport == "sse" and not server_url:
            raise ValueError("SSE 模式需要提供 server_url")

        self.transport = transport
        self.server_url = server_url

    def _run_async(self, coro):
        """在同步上下文中运行异步协程"""
        return asyncio.run(coro)

    @asynccontextmanager
    async def _create_session(self):
        """创建 MCP 客户端会话

        根据传输类型创建相应的连接。
        """
        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            if self.transport == "stdio":
                # stdio 模式：启动子进程
                server_params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "grid_code.cli", "serve", "--transport", "stdio"],
                    env=None,
                )
                transport = await stack.enter_async_context(stdio_client(server_params))
            else:
                # sse 模式：连接外部服务器
                # 使用自定义 httpx 工厂禁用代理，避免 502 Bad Gateway
                transport = await stack.enter_async_context(
                    sse_client(
                        self.server_url,
                        httpx_client_factory=_no_proxy_httpx_client_factory,
                    )
                )

            read, write = transport
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            yield session

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        """异步调用 MCP 工具"""
        async with self._create_session() as session:
            logger.debug(f"MCP call: {name}({arguments})")
            result = await session.call_tool(name, arguments)

            # 解析结果
            if result.content:
                import json

                contents = []
                for content in result.content:
                    if hasattr(content, "text"):
                        contents.append(content.text)
                    elif hasattr(content, "data"):
                        contents.append(content.data)

                if len(contents) == 1:
                    try:
                        return json.loads(contents[0])
                    except (json.JSONDecodeError, TypeError):
                        return contents[0]
                return contents
            return None

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """同步调用 MCP 工具"""
        return self._run_async(self._call_tool_async(name, arguments))

    def _ensure_list(self, result: Any) -> list[dict]:
        """确保结果是列表（MCP 可能将单元素列表解包为 dict）"""
        if result is None:
            return []
        if isinstance(result, dict):
            return [result]
        return result

    # ==================== 基础工具 ====================

    def get_toc(self, reg_id: str) -> dict:
        """获取规程目录树"""
        return self._call_tool("get_toc", {"reg_id": reg_id})

    def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """智能混合检索"""
        args: dict[str, Any] = {
            "query": query,
            "reg_id": reg_id,
            "limit": limit,
        }
        if chapter_scope:
            args["chapter_scope"] = chapter_scope
        if block_types:
            args["block_types"] = block_types
        if section_number:
            args["section_number"] = section_number
        return self._ensure_list(self._call_tool("smart_search", args))

    def read_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """读取页面范围"""
        return self._call_tool(
            "read_page_range",
            {
                "reg_id": reg_id,
                "start_page": start_page,
                "end_page": end_page,
            },
        )

    def list_regulations(self) -> list[dict]:
        """列出所有规程"""
        return self._ensure_list(self._call_tool("list_regulations", {}))

    def get_chapter_structure(self, reg_id: str) -> dict:
        """获取章节结构"""
        return self._call_tool("get_chapter_structure", {"reg_id": reg_id})

    def get_page_chapter_info(self, reg_id: str, page_num: int) -> dict:
        """获取页面章节信息"""
        return self._call_tool(
            "get_page_chapter_info",
            {
                "reg_id": reg_id,
                "page_num": page_num,
            },
        )

    def read_chapter_content(
        self,
        reg_id: str,
        section_number: str,
        include_children: bool = True,
    ) -> dict:
        """读取章节内容"""
        return self._call_tool(
            "read_chapter_content",
            {
                "reg_id": reg_id,
                "section_number": section_number,
                "include_children": include_children,
            },
        )

    # ==================== Phase 1: 核心多跳工具 ====================

    def lookup_annotation(
        self,
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """查找注释"""
        args: dict[str, Any] = {"reg_id": reg_id, "annotation_id": annotation_id}
        if page_hint is not None:
            args["page_hint"] = page_hint
        return self._call_tool("lookup_annotation", args)

    def search_tables(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
        limit: int = 10,
    ) -> list[dict]:
        """搜索表格"""
        args: dict[str, Any] = {
            "query": query,
            "reg_id": reg_id,
            "search_mode": search_mode,
            "limit": limit,
        }
        if chapter_scope:
            args["chapter_scope"] = chapter_scope
        return self._ensure_list(self._call_tool("search_tables", args))

    def resolve_reference(self, reg_id: str, reference_text: str) -> dict:
        """解析交叉引用"""
        return self._call_tool(
            "resolve_reference",
            {
                "reg_id": reg_id,
                "reference_text": reference_text,
            },
        )

    # ==================== Phase 2: 上下文工具 ====================

    def search_annotations(
        self,
        reg_id: str,
        pattern: str | None = None,
        annotation_type: str | None = None,
    ) -> list[dict]:
        """搜索注释"""
        args: dict[str, Any] = {"reg_id": reg_id}
        if pattern:
            args["pattern"] = pattern
        if annotation_type:
            args["annotation_type"] = annotation_type
        return self._ensure_list(self._call_tool("search_annotations", args))

    def get_table_by_id(
        self,
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """获取表格内容"""
        return self._call_tool(
            "get_table_by_id",
            {
                "reg_id": reg_id,
                "table_id": table_id,
                "include_merged": include_merged,
            },
        )

    def get_block_with_context(
        self,
        reg_id: str,
        block_id: str,
        context_blocks: int = 2,
    ) -> dict:
        """获取内容块及上下文"""
        return self._call_tool(
            "get_block_with_context",
            {
                "reg_id": reg_id,
                "block_id": block_id,
                "context_blocks": context_blocks,
            },
        )

    # ==================== Phase 3: 发现工具 ====================

    def find_similar_content(
        self,
        reg_id: str,
        query_text: str | None = None,
        source_block_id: str | None = None,
        limit: int = 5,
        exclude_same_page: bool = True,
    ) -> list[dict]:
        """查找相似内容"""
        args: dict[str, Any] = {
            "reg_id": reg_id,
            "limit": limit,
            "exclude_same_page": exclude_same_page,
        }
        if query_text:
            args["query_text"] = query_text
        if source_block_id:
            args["source_block_id"] = source_block_id
        return self._ensure_list(self._call_tool("find_similar_content", args))

    def compare_sections(
        self,
        reg_id: str,
        section_a: str,
        section_b: str,
        include_tables: bool = True,
    ) -> dict:
        """比较两个章节"""
        return self._call_tool(
            "compare_sections",
            {
                "reg_id": reg_id,
                "section_a": section_a,
                "section_b": section_b,
                "include_tables": include_tables,
            },
        )
