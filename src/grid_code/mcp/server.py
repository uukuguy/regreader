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
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """在安规中执行混合检索（关键词+语义）。

        结合全文检索和语义向量检索，返回最相关的内容片段。
        建议先通过 get_toc 确定章节范围，再进行精准搜索。

        Args:
            query: 搜索查询，如 "母线失压处理"
            reg_id: 规程标识，如 'angui_2024'
            chapter_scope: 限定章节范围（可选），如 "第六章" 或 "事故处理"
            limit: 返回结果数量限制，默认 10
            block_types: 限定块类型列表（可选），如 ["text", "table", "section_content"]
            section_number: 精确匹配章节号（可选），如 "2.1.4.1.6"

        Returns:
            搜索结果列表，每个结果包含:
            - page_num: 页码
            - chapter_path: 章节路径
            - snippet: 匹配内容片段
            - score: 相关性分数
            - source: 来源引用（如 "angui_2024 P85"）
            - block_id: 块标识
        """
        try:
            return tools.smart_search(
                query, reg_id, chapter_scope, limit, block_types, section_number
            )
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

    @mcp.tool()
    def get_chapter_structure(reg_id: str) -> dict:
        """获取规程的完整章节结构。

        返回文档的全局章节结构树，包括各级章节编号、标题、页码等信息。
        适用于需要精确定位到某个章节的场景。

        Args:
            reg_id: 规程标识，如 'angui_2024'

        Returns:
            章节结构信息，包含:
            - reg_id: 规程标识
            - total_chapters: 章节总数
            - root_nodes: 顶级章节列表，每个节点包含:
                - node_id: 节点ID
                - section_number: 章节编号（如 "2.1.4.1.6"）
                - title: 章节标题
                - level: 层级
                - page_num: 首页页码
                - children_count: 子章节数量
                - has_direct_content: 是否有直接内容
        """
        try:
            return tools.get_chapter_structure(reg_id)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool()
    def get_page_chapter_info(reg_id: str, page_num: int) -> dict:
        """获取指定页面的章节信息。

        返回该页面的所有活跃章节，包括从上页延续的章节和本页首次出现的章节。
        适用于需要了解某页章节上下文的场景。

        Args:
            reg_id: 规程标识，如 'angui_2024'
            page_num: 页码

        Returns:
            页面章节信息，包含:
            - reg_id: 规程标识
            - page_num: 页码
            - active_chapters: 活跃章节列表，每个章节包含:
                - node_id: 节点ID
                - section_number: 章节编号
                - title: 章节标题
                - level: 层级
                - page_num: 首次出现的页码
                - inherited: 是否为延续的章节（从上页继承）
                - has_direct_content: 是否有直接内容
                - full_title: 完整标题（编号+标题）
            - total_chapters: 总章节数
            - new_chapters_count: 本页首次出现的章节数
            - inherited_chapters_count: 从上页延续的章节数
        """
        try:
            return tools.get_page_chapter_info(reg_id, page_num)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool()
    def read_chapter_content(
        reg_id: str,
        section_number: str,
        include_children: bool = True,
    ) -> dict:
        """读取指定章节的完整内容。

        获取某个章节编号下的所有内容，自动处理跨页情况。
        适用于需要阅读整个章节而非搜索片段的场景。

        先通过 get_chapter_structure 或 get_toc 获取章节编号，
        再使用此工具读取章节完整内容。

        Args:
            reg_id: 规程标识，如 'angui_2024'
            section_number: 章节编号，如 "2.1.4.1.6"
            include_children: 是否包含子章节内容，默认 True

        Returns:
            章节内容，包含:
            - section_number: 章节编号
            - title: 章节标题
            - full_path: 完整章节路径
            - content_markdown: 该章节的完整 Markdown 内容
            - page_range: [起始页, 结束页]
            - block_count: 内容块数量
            - children: 子章节列表
            - children_included: 是否包含了子章节内容
            - source: 来源引用
        """
        try:
            return tools.read_chapter_content(reg_id, section_number, include_children)
        except GridCodeError as e:
            return {"error": str(e)}

    return mcp


# 全局 MCP 实例（用于 CLI 启动）
mcp_server = create_mcp_server()
