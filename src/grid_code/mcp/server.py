"""FastMCP 服务实现

使用 FastMCP 框架实现 MCP Server。

工具集设计：
- 核心工具（8个）：始终启用，智能体检索安规必备
- 高级分析工具（2个）：默认禁用，通过配置开关启用
"""

from mcp.server.fastmcp import FastMCP

from grid_code.config import get_settings
from grid_code.exceptions import GridCodeError
from grid_code.mcp.tool_metadata import TOOL_METADATA, get_enabled_tools
from grid_code.mcp.tools import GridCodeTools


def create_mcp_server(
    name: str = "gridcode",
    host: str = "127.0.0.1",
    port: int = 8000,
    enable_advanced_tools: bool | None = None,
) -> FastMCP:
    """
    创建 MCP Server 实例

    Args:
        name: 服务名称
        host: 监听地址（SSE 模式）
        port: 监听端口（SSE 模式）
        enable_advanced_tools: 是否启用高级分析工具，None 表示从配置读取

    Returns:
        FastMCP 实例
    """
    # 确定是否启用高级工具
    if enable_advanced_tools is None:
        settings = get_settings()
        enable_advanced_tools = settings.enable_advanced_tools

    # 获取启用的工具列表
    enabled_tools = get_enabled_tools(include_advanced=enable_advanced_tools)

    mcp = FastMCP(name, host=host, port=port)
    tools = GridCodeTools()

    # ==================== 基础工具（4个，始终启用） ====================

    @mcp.tool(meta=TOOL_METADATA["list_regulations"].to_dict())
    def list_regulations() -> list[dict]:
        """列出所有已入库的规程。"""
        return tools.list_regulations()

    @mcp.tool(meta=TOOL_METADATA["get_toc"].to_dict())
    def get_toc(reg_id: str) -> dict:
        """获取规程目录树。"""
        try:
            return tools.get_toc(reg_id)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool(meta=TOOL_METADATA["smart_search"].to_dict())
    def smart_search(
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """混合检索（关键词+语义）。"""
        try:
            return tools.smart_search(
                query, reg_id, chapter_scope, limit, block_types, section_number
            )
        except GridCodeError as e:
            return [{"error": str(e)}]

    @mcp.tool(meta=TOOL_METADATA["read_page_range"].to_dict())
    def read_page_range(
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """读取连续页面内容。"""
        try:
            return tools.read_page_range(reg_id, start_page, end_page)
        except GridCodeError as e:
            return {"error": str(e)}

    # ==================== 多跳推理工具（3个，始终启用） ====================

    @mcp.tool(meta=TOOL_METADATA["search_tables"].to_dict())
    def search_tables(
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_mode: str = "hybrid",
        limit: int = 10,
    ) -> list[dict]:
        """搜索表格。"""
        try:
            return tools.search_tables(query, reg_id, chapter_scope, search_mode, limit)
        except GridCodeError as e:
            return [{"error": str(e)}]

    @mcp.tool(meta=TOOL_METADATA["lookup_annotation"].to_dict())
    def lookup_annotation(
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """查找注释内容。"""
        try:
            return tools.lookup_annotation(reg_id, annotation_id, page_hint)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool(meta=TOOL_METADATA["resolve_reference"].to_dict())
    def resolve_reference(
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """解析交叉引用。"""
        try:
            return tools.resolve_reference(reg_id, reference_text)
        except GridCodeError as e:
            return {"error": str(e)}

    # ==================== 上下文扩展工具（1个，始终启用） ====================

    @mcp.tool(meta=TOOL_METADATA["get_table_by_id"].to_dict())
    def get_table_by_id(
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """获取完整表格内容。"""
        try:
            return tools.get_table_by_id(reg_id, table_id, include_merged)
        except GridCodeError as e:
            return {"error": str(e)}

    # ==================== 高级分析工具（可选，配置开关控制） ====================

    if enable_advanced_tools:
        @mcp.tool(meta=TOOL_METADATA["find_similar_content"].to_dict())
        def find_similar_content(
            reg_id: str,
            query_text: str | None = None,
            source_block_id: str | None = None,
            limit: int = 5,
            exclude_same_page: bool = True,
        ) -> list[dict]:
            """查找语义相似的内容。"""
            try:
                return tools.find_similar_content(
                    reg_id, query_text, source_block_id, limit, exclude_same_page
                )
            except GridCodeError as e:
                return [{"error": str(e)}]

        @mcp.tool(meta=TOOL_METADATA["compare_sections"].to_dict())
        def compare_sections(
            reg_id: str,
            section_a: str,
            section_b: str,
            include_tables: bool = True,
        ) -> dict:
            """比较两个章节的内容。"""
            try:
                return tools.compare_sections(reg_id, section_a, section_b, include_tables)
            except GridCodeError as e:
                return {"error": str(e)}

    return mcp
