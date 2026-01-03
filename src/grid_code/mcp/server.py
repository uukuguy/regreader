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
        """[分类:基础工具] 列出所有已入库的规程。

        返回所有可查询的规程信息，包括标识、标题、页数等。

        使用场景：了解可用规程、确定规程范围。
        后续工具：get_toc。

        Returns:
            规程信息列表，包含 reg_id, title, total_pages, indexed_at。
        """
        return tools.list_regulations()

    @mcp.tool(meta=TOOL_METADATA["get_toc"].to_dict())
    def get_toc(reg_id: str) -> dict:
        """[分类:基础工具] 获取安规的章节目录树及页码范围。

        在开始搜索前，应先调用此工具了解规程的整体结构，
        以便确定搜索的章节范围。

        使用场景：了解规程结构、确定搜索范围。
        后续工具：smart_search, read_chapter_content。

        Args:
            reg_id: 规程标识，如 'angui_2024'

        Returns:
            章节树结构，包含各章节的标题和页码范围。
        """
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
        """[分类:基础工具] 在安规中执行混合检索（关键词+语义）。

        结合全文检索和语义向量检索，返回最相关的内容片段。

        使用场景：查找相关内容、混合检索。
        前置工具：建议先用 get_toc 确定章节范围。
        后续工具：read_page_range, get_block_with_context。

        Args:
            query: 搜索查询，如 "母线失压处理"
            reg_id: 规程标识，如 'angui_2024'
            chapter_scope: 限定章节范围（可选），如 "第六章" 或 "事故处理"
            limit: 返回结果数量限制，默认 10
            block_types: 限定块类型列表（可选），如 ["text", "table"]
            section_number: 精确匹配章节号（可选），如 "2.1.4.1.6"

        Returns:
            搜索结果列表，包含 page_num, snippet, score, source, block_id 等。
        """
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
        """[分类:基础工具] 读取连续页面的完整 Markdown 内容。

        自动处理跨页表格的拼接。单次最多读取 10 页。

        使用场景：阅读完整页面、查看跨页表格。
        前置工具：通常在 smart_search 后使用。

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            页面内容，包含 content_markdown, source, has_merged_tables 等。
        """
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
        """[分类:多跳推理] 搜索表格（按标题或单元格内容）。

        在规程中查找表格，支持按表格标题（如"表6-2"）或
        单元格内容（如"母线失压"）进行搜索。

        使用场景：查找特定表格、表格内容搜索。
        前置工具：通常先用 get_toc 了解章节范围。
        后续工具：找到表格后用 get_table_by_id 获取完整内容。

        Args:
            query: 搜索查询，如 "母线失压" 或 "表6-2"
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选），如 "第六章"
            search_mode: 搜索模式，keyword/semantic/hybrid（默认hybrid）
            limit: 返回结果数量限制，默认10

        Returns:
            匹配的表格列表，每个包含:
            - table_id: 表格标识
            - caption: 表格标题
            - page_num: 所在页码
            - row_count: 行数
            - col_count: 列数
            - col_headers: 列标题
            - is_truncated: 是否跨页（需要读取后续页面获取完整表格）
            - match_type: 匹配类型（'caption', 'cell', 'both'）
            - matched_cells: 匹配的单元格信息
            - chapter_path: 所属章节路径
            - source: 来源引用
        """
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
        """[分类:多跳推理] 查找并返回指定注释的完整内容。

        处理表格单元格中常见的 "见注1"、"方案A" 等引用。
        支持多种注释标识变体：注1/注①/注一、方案A/方案甲 等。

        使用场景：查找注释内容、理解表格脚注、追踪「见注X」。
        前置工具：smart_search 或 search_tables（先找到包含注释引用的内容）。

        Args:
            reg_id: 规程标识，如 'angui_2024'
            annotation_id: 注释标识，如 '注1', '注①', '方案A', '方案甲'
            page_hint: 页码提示（可选），如果知道注释大概在哪一页，
                      提供此参数可加速搜索

        Returns:
            注释信息，包含:
            - annotation_id: 注释标识
            - content: 注释完整内容
            - page_num: 所在页码
            - related_blocks: 关联的内容块ID列表
            - source: 来源引用
        """
        try:
            return tools.lookup_annotation(reg_id, annotation_id, page_hint)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool(meta=TOOL_METADATA["resolve_reference"].to_dict())
    def resolve_reference(
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """[分类:多跳推理] 解析并解决交叉引用。

        当在规程内容中遇到交叉引用时（如"见第六章"、"参见表6-2"、
        "详见2.1.4"），使用此工具解析引用并获取目标位置和内容预览。

        使用场景：解析「见第X章」、「参见表Y」等交叉引用。
        前置工具：smart_search（先搜索找到包含引用的内容）。
        后续工具：read_page_range（跳转阅读目标内容）。

        支持多种引用格式:
        - 章节引用: "见第六章", "参见2.1.4", "详见第三节"
        - 表格引用: "见表6-2", "参见附表1"
        - 条款引用: "见第X条", "按本规程第Y条执行"
        - 注释引用: "见注1", "参见方案A"
        - 附录引用: "见附录A", "详见附录三"

        Args:
            reg_id: 规程标识
            reference_text: 引用文本，如 "见第六章" 或 "详见表6-2"

        Returns:
            解析结果，包含:
            - reference_type: 引用类型（chapter/section/table/annotation/appendix/article）
            - parsed_target: 解析出的目标
            - resolved: 是否成功解析
            - target_location: 目标位置信息（页码、章节编号等）
            - preview: 目标内容预览（前300字符）
            - source: 完整来源引用
            - error: 错误信息（如未找到）
        """
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
        """[分类:上下文扩展] 获取完整表格内容（含跨页合并）。

        根据表格ID获取表格的完整信息，包括所有单元格数据。
        如果表格跨页，自动合并后续页面的内容。

        使用场景：获取完整表格、跨页表格合并。
        前置工具：search_tables（先搜索找到目标表格）。
        后续工具：lookup_annotation（追踪表格中的注释引用）。

        Args:
            reg_id: 规程标识
            table_id: 表格标识（从 search_tables 结果获取）
            include_merged: 如果表格跨页，是否自动合并（默认True）

        Returns:
            表格完整信息，包含:
            - table_id: 表格标识
            - caption: 表格标题
            - page_num: 起始页码
            - page_range: [起始页, 结束页]
            - row_count: 行数
            - col_count: 列数
            - col_headers: 列标题
            - row_headers: 行标题
            - cells: 完整单元格数据
            - markdown: 表格Markdown格式
            - chapter_path: 所属章节路径
            - annotations: 相关注释列表
            - source: 来源引用
        """
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
            """[分类:高级分析] 查找语义相似的内容。

            发现与给定文本或内容块语义相似的其他内容。

            使用场景：查找相似内容、发现相关条款。
            前置工具：smart_search（获取初始内容后查找相似）。

            可以提供文本查询，或者提供已有内容块的ID来查找相似内容。

            Args:
                reg_id: 规程标识
                query_text: 查询文本（与 source_block_id 二选一）
                source_block_id: 源内容块ID（与 query_text 二选一）
                limit: 返回结果数量限制，默认5
                exclude_same_page: 是否排除同页内容（默认True）

            Returns:
                相似内容列表，每个包含:
                - block_id: 内容块标识
                - page_num: 页码
                - chapter_path: 章节路径
                - snippet: 内容片段
                - similarity_score: 相似度分数 (0-1)
                - source: 来源引用
            """
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
            """[分类:高级分析] 比较两个章节的内容。

            并排比较两个章节的结构和内容，帮助理解它们的异同。

            使用场景：比较章节、差异分析。
            前置工具：get_toc（了解章节编号）。

            Args:
                reg_id: 规程标识
                section_a: 第一个章节编号，如 "2.1.4"
                section_b: 第二个章节编号，如 "2.1.5"
                include_tables: 是否包含表格内容，默认True

            Returns:
                比较结果，包含:
                - section_a_info: 第一个章节的信息（标题、页码范围、块数量、表格数等）
                - section_b_info: 第二个章节的信息
                - common_keywords: 共同关键词列表
                - structural_comparison: 结构差异（块数差、子章节差、表格差等）
                - source: 来源引用
            """
            try:
                return tools.compare_sections(reg_id, section_a, section_b, include_tables)
            except GridCodeError as e:
                return {"error": str(e)}

    return mcp
