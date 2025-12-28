"""FastMCP 服务实现

使用 FastMCP 框架实现 MCP Server。
"""

from mcp.server.fastmcp import FastMCP

from grid_code.exceptions import GridCodeError
from grid_code.mcp.tools import GridCodeTools


def create_mcp_server(name: str = "gridcode") -> FastMCP:
    """
    创建 MCP Server 实例

    Args:
        name: 服务名称

    Returns:
        FastMCP 实例
    """
    mcp = FastMCP(name)
    tools = GridCodeTools()

    @mcp.tool()
    def get_toc(reg_id: str) -> dict:
        """获取安规的章节目录树及页码范围。

        在开始搜索前，应先调用此工具了解规程的整体结构，
        以便确定搜索的章节范围。

        Args:
            reg_id: 规程标识，如 'angui_2024'

        Returns:
            章节树结构，包含各章节的标题和页码范围。
            格式: {
                "reg_id": "规程标识",
                "title": "规程标题",
                "total_pages": 总页数,
                "items": [
                    {
                        "title": "章节标题",
                        "level": 层级,
                        "page_start": 起始页,
                        "page_end": 结束页,
                        "children": [子章节...]
                    }
                ]
            }
        """
        try:
            return tools.get_toc(reg_id)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool()
    def smart_search(
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """在安规中执行混合检索（关键词+语义）。

        结合全文检索和语义向量检索，返回最相关的内容片段。
        建议先通过 get_toc 确定章节范围，再进行精准搜索。

        Args:
            query: 搜索查询，如 "母线失压处理"
            reg_id: 规程标识，如 'angui_2024'
            chapter_scope: 限定章节范围（可选），如 "第六章" 或 "事故处理"
            limit: 返回结果数量限制，默认 10

        Returns:
            搜索结果列表，每个结果包含:
            - page_num: 页码
            - chapter_path: 章节路径
            - snippet: 匹配内容片段
            - score: 相关性分数
            - source: 来源引用（如 "angui_2024 P85"）
        """
        try:
            return tools.smart_search(query, reg_id, chapter_scope, limit)
        except GridCodeError as e:
            return [{"error": str(e)}]

    @mcp.tool()
    def read_page_range(
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """读取连续页面的完整 Markdown 内容。

        自动处理跨页表格的拼接。当搜索结果显示表格可能跨页时，
        应读取相邻页面以获取完整信息。

        单次最多读取 10 页。

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            页面内容，包含:
            - content_markdown: 合并后的完整 Markdown 内容
            - source: 来源引用
            - has_merged_tables: 是否包含合并的跨页表格
            - page_count: 实际读取的页数
        """
        try:
            return tools.read_page_range(reg_id, start_page, end_page)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool()
    def list_regulations() -> list[dict]:
        """列出所有已入库的规程。

        返回所有可查询的规程信息，包括标识、标题、页数等。

        Returns:
            规程信息列表，每个规程包含:
            - reg_id: 规程标识
            - title: 规程标题
            - total_pages: 总页数
            - indexed_at: 入库时间
        """
        return tools.list_regulations()

    return mcp


# 全局 MCP 实例（用于 CLI 启动）
mcp_server = create_mcp_server()
