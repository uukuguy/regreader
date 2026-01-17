"""MCP 工具适配器

封装 RegReaderMCPClient，提供与 RegReaderTools 相同的同步接口。
支持会话复用，避免重复初始化。
"""

import asyncio
import sys
import threading
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


class RegReaderMCPToolsAdapter:
    """MCP 工具适配器

    将异步的 MCP Client 调用包装为同步接口，
    与 RegReaderTools 提供相同的方法签名。

    支持两种传输方式：
    - stdio: 自动启动子进程（会话复用）
    - sse: 连接外部 MCP Server（会话复用）

    使用示例：
        # stdio 模式
        adapter = RegReaderMCPToolsAdapter(transport="stdio")

        # sse 模式
        adapter = RegReaderMCPToolsAdapter(
            transport="sse",
            server_url="http://localhost:8080/sse"
        )

        # 调用工具（同步接口）
        result = adapter.get_toc("angui_2024")

    性能优化：
        - 会话复用：首次调用时创建会话，后续调用复用同一会话
        - 避免重复加载嵌入模型
        - 自动清理资源
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

        # 会话管理（使用线程本地存储以支持多线程）
        import threading
        self._local = threading.local()
        self._session_lock = asyncio.Lock()

    def _run_async(self, coro):
        """在同步上下文中运行异步协程

        智能处理已有事件循环的情况：
        - SSE 模式：必须在同一个事件循环中运行（不能跨线程）
        - stdio 模式：可以跨线程运行
        """
        try:
            loop = asyncio.get_running_loop()
            # 当前正在运行的事件循环

            # SSE 模式不能跨线程，必须在当前事件循环中运行
            if self.transport == "sse":
                logger.info(
                    f"[MCP] SSE 模式：在当前事件循环中运行协程"
                )
                # 检查是否在主线程
                import threading
                if threading.current_thread() is threading.main_thread():
                    # 在主线程中，可以使用 asyncio.run_coroutine_threadsafe
                    import concurrent.futures

                    future = asyncio.run_coroutine_threadsafe(coro, loop)
                    return future.result(timeout=60)  # 60秒超时
                else:
                    # 在其他线程中，无法安全地运行 SSE 连接
                    raise RuntimeError(
                        "SSE 模式不能在非主线程的事件循环中使用"
                    )
            else:
                # stdio 模式：可以在新线程中运行
                import concurrent.futures

                def run_in_new_loop():
                    """在新的事件循环中运行协程"""
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(coro)
                        return result
                    finally:
                        # 关闭新事件循环，清理所有待处理的任务
                        new_loop.run_until_complete(new_loop.shutdown_asyncgens())
                        new_loop.close()
                        # 恢复旧的事件循环（如果需要）
                        asyncio.set_event_loop(None)

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(run_in_new_loop)
                    return future.result()

        except RuntimeError:
            # 没有运行中的事件循环，可以直接使用 asyncio.run()
            return asyncio.run(coro)

    async def _get_or_create_session(self) -> ClientSession:
        """获取或创建 MCP 客户端会话

        使用线程本地存储，每个线程有自己的会话。
        注意：会话不能跨线程共享，所以每个线程都创建新会话。

        Returns:
            已初始化的 ClientSession
        """
        # 获取或创建当前线程的会话
        if not hasattr(self._local, "session") or self._local.session is None:
            logger.info(f"[MCP] 创建新会话: {self.transport} 模式 (thread: {threading.get_ident()})")

            # stdio 模式：启动子进程
            if self.transport == "stdio":
                server_params = StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "regreader.cli", "serve", "--transport", "stdio"],
                    env=None,
                )
                stdio_transport = stdio_client(server_params)
                read, write = await stdio_transport.__aenter__()
                self._local.stdio_transport = stdio_transport
            else:
                # sse 模式：连接外部服务器
                logger.info(f"[MCP] 正在连接 SSE 服务器: {self.server_url}")
                sse_transport = sse_client(
                    self.server_url,
                    httpx_client_factory=_no_proxy_httpx_client_factory,
                )
                logger.info(f"[MCP] SSE 客户端创建成功，正在建立连接...")
                read, write = await sse_transport.__aenter__()
                logger.info(f"[MCP] SSE 连接建立成功")
                self._local.sse_transport = sse_transport

            # 创建会话
            logger.info(f"[MCP] 正在创建 ClientSession...")
            session = ClientSession(read, write)
            logger.info(f"[MCP] 正在初始化会话（30秒超时）...")
            try:
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                self._local.session = session
                logger.info(f"[MCP] 会话创建成功")
            except asyncio.TimeoutError:
                logger.error(f"[MCP] 会话初始化超时")
                raise TimeoutError(f"MCP 会话初始化超时（{self.transport} 模式）")

        return self._local.session

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> Any:
        """异步调用 MCP 工具（会话复用）"""
        logger.info(f"[MCP] _call_tool_async 开始: {name}({arguments})")
        session = await self._get_or_create_session()

        logger.debug(f"MCP call: {name}({arguments})")
        logger.info(f"[MCP] 正在调用工具: {name}...")
        result = await session.call_tool(name, arguments)
        logger.info(f"[MCP] 工具调用完成: {name}")

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
        """同步调用 MCP 工具（会话复用）"""
        return self._run_async(self._call_tool_async(name, arguments))

    def close(self):
        """关闭 MCP 会话并清理资源（同步方法）

        应在使用完毕后调用，释放子进程或网络连接。
        自动处理同步/异步上下文。
        """
        self._run_async(self._close_async())

    async def _close_async(self):
        """异步关闭 MCP 会话（关闭当前线程的会话）"""
        if hasattr(self._local, "session") and self._local.session is not None:
            logger.info(f"[MCP] 关闭会话: {self.transport} 模式")

            # 关闭会话
            await self._local.session.__aexit__(None, None, None)
            self._local.session = None

            # 关闭传输
            if hasattr(self._local, "stdio_transport") and self._local.stdio_transport:
                await self._local.stdio_transport.__aexit__(None, None, None)
                self._local.stdio_transport = None
            elif hasattr(self._local, "sse_transport") and self._local.sse_transport:
                await self._local.sse_transport.__aexit__(None, None, None)
                self._local.sse_transport = None

    def __del__(self):
        """析构函数：确保会话被关闭"""
        try:
            self.close()
        except Exception:
            # 析构时忽略错误
            pass

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self._close_async()

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
