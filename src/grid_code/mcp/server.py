"""FastMCP 服务实现

使用 FastMCP 框架实现 MCP Server。
"""

from mcp.server.fastmcp import FastMCP

from grid_code.exceptions import GridCodeError
from grid_code.mcp.tool_metadata import TOOL_METADATA
from grid_code.mcp.tools import GridCodeTools


def create_mcp_server(
    name: str = "gridcode",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """
    创建 MCP Server 实例

    Args:
        name: 服务名称
        host: 监听地址（SSE 模式）
        port: 监听端口（SSE 模式）

    Returns:
        FastMCP 实例
    """
    mcp = FastMCP(name, host=host, port=port)
    tools = GridCodeTools()

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

    @mcp.tool(meta=TOOL_METADATA["list_regulations"].to_dict())
    def list_regulations() -> list[dict]:
        """[分类:基础工具] 列出所有已入库的规程。

        返回所有可查询的规程信息，包括标识、标题、页数等。

        使用场景：了解可用规程。
        后续工具：get_toc。

        Returns:
            规程信息列表，包含 reg_id, title, total_pages, indexed_at。
        """
        return tools.list_regulations()

    @mcp.tool(meta=TOOL_METADATA["get_chapter_structure"].to_dict())
    def get_chapter_structure(reg_id: str) -> dict:
        """[分类:基础工具] 获取规程的完整章节结构。

        返回文档的全局章节结构树，包括各级章节编号、标题、页码等信息。

        使用场景：获取章节树。
        前置工具：get_toc。
        后续工具：read_chapter_content。

        Args:
            reg_id: 规程标识，如 'angui_2024'

        Returns:
            章节结构信息，包含 reg_id, total_chapters, root_nodes 等。
        """
        try:
            return tools.get_chapter_structure(reg_id)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool(meta=TOOL_METADATA["get_page_chapter_info"].to_dict())
    def get_page_chapter_info(reg_id: str, page_num: int) -> dict:
        """[分类:基础工具] 获取指定页面的章节信息。

        返回该页面的所有活跃章节，包括从上页延续的章节和本页首次出现的章节。

        使用场景：了解页面所属章节。

        Args:
            reg_id: 规程标识，如 'angui_2024'
            page_num: 页码

        Returns:
            页面章节信息，包含 active_chapters, total_chapters 等。
        """
        try:
            return tools.get_page_chapter_info(reg_id, page_num)
        except GridCodeError as e:
            return {"error": str(e)}

    @mcp.tool(meta=TOOL_METADATA["read_chapter_content"].to_dict())
    def read_chapter_content(
        reg_id: str,
        section_number: str,
        include_children: bool = True,
    ) -> dict:
        """[分类:基础工具] 读取指定章节的完整内容。

        获取某个章节编号下的所有内容，自动处理跨页情况。
        适用于需要阅读整个章节而非搜索片段的场景。

        使用场景：阅读完整章节。
        前置工具：get_chapter_structure。

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

    # ==================== Phase 1: 核心多跳工具 ====================

    @mcp.tool(meta=TOOL_METADATA["lookup_annotation"].to_dict())
    def lookup_annotation(
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """[分类:核心多跳] 查找并返回指定注释的完整内容。

        处理表格单元格中常见的 "见注1"、"方案A" 等引用。
        支持多种注释标识变体：注1/注①/注一、方案A/方案甲 等。

        使用场景：查找注释内容、理解表格脚注。
        前置工具：smart_search（先搜索找到包含注释引用的内容）。

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

    @mcp.tool(meta=TOOL_METADATA["search_tables"].to_dict())
    def search_tables(
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_cells: bool = True,
        limit: int = 10,
    ) -> list[dict]:
        """[分类:核心多跳] 搜索表格（按标题或单元格内容）。

        在规程中查找表格，支持按表格标题（如"表6-2"）或
        单元格内容（如"母线失压"）进行搜索。

        使用场景：查找特定表格、表格内容搜索。
        前置工具：通常先用 get_toc 了解章节范围。
        后续工具：找到表格后用 get_table_by_id 获取完整内容。

        Args:
            query: 搜索查询，如 "母线失压" 或 "表6-2"
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选），如 "第六章"
            search_cells: 是否搜索单元格内容（默认True）
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
            return tools.search_tables(query, reg_id, chapter_scope, search_cells, limit)
        except GridCodeError as e:
            return [{"error": str(e)}]

    @mcp.tool(meta=TOOL_METADATA["resolve_reference"].to_dict())
    def resolve_reference(
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """[分类:核心多跳] 解析并解决交叉引用。

        当在规程内容中遇到交叉引用时（如"见第六章"、"参见表6-2"、
        "详见2.1.4"），使用此工具解析引用并获取目标位置和内容预览。

        使用场景：解析交叉引用。
        前置工具：smart_search（先搜索找到包含引用的内容）。
        后续工具：read_page_range, read_chapter_content（跳转阅读）。

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

    # ==================== Phase 2: 上下文工具 ====================

    @mcp.tool(meta=TOOL_METADATA["search_annotations"].to_dict())
    def search_annotations(
        reg_id: str,
        pattern: str | None = None,
        annotation_type: str | None = None,
    ) -> list[dict]:
        """[分类:上下文] 搜索规程中的所有注释。

        查找规程中的所有注释，支持按内容模式和类型过滤。

        使用场景：搜索所有注释。
        后续工具：lookup_annotation（获取具体注释详情）。

        Args:
            reg_id: 规程标识
            pattern: 内容匹配模式（可选），支持简单文本匹配
            annotation_type: 注释类型过滤（可选）
                - 'note': 注释类（注1, 注①等）
                - 'plan': 方案类（方案A, 方案甲等）
                - None: 不过滤，返回所有注释

        Returns:
            匹配的注释列表，每个包含:
            - annotation_id: 注释标识
            - content: 注释完整内容（截取前200字符）
            - page_num: 所在页码
            - source: 来源引用
        """
        try:
            return tools.search_annotations(reg_id, pattern, annotation_type)
        except GridCodeError as e:
            return [{"error": str(e)}]

    @mcp.tool(meta=TOOL_METADATA["get_table_by_id"].to_dict())
    def get_table_by_id(
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """[分类:上下文] 获取完整表格内容（按表格ID）。

        根据表格ID获取表格的完整信息，包括所有单元格数据。
        如果表格跨页，自动合并后续页面的内容。

        使用场景：获取完整表格。
        前置工具：search_tables（先搜索找到目标表格）。

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

    @mcp.tool(meta=TOOL_METADATA["get_block_with_context"].to_dict())
    def get_block_with_context(
        reg_id: str,
        block_id: str,
        context_blocks: int = 2,
    ) -> dict:
        """[分类:上下文] 读取指定内容块及其上下文。

        当搜索结果的片段不够完整时，使用此工具获取更多上下文。
        返回目标块及其前后的内容块，帮助理解完整语境。

        使用场景：扩展上下文。
        前置工具：smart_search（先搜索获取 block_id）。

        Args:
            reg_id: 规程标识
            block_id: 内容块标识（从搜索结果的 block_id 字段获取）
            context_blocks: 上下文块数量（前后各N个块），默认2

        Returns:
            内容块及上下文，包含:
            - target_block: 目标块完整信息（block_id, block_type, content_markdown, chapter_path）
            - page_num: 所在页码
            - before_blocks: 前序块列表
            - after_blocks: 后续块列表
            - page_annotations: 页面注释列表
            - active_chapters: 活跃章节信息
            - source: 来源引用
        """
        try:
            return tools.get_block_with_context(reg_id, block_id, context_blocks)
        except GridCodeError as e:
            return {"error": str(e)}

    # ==================== Phase 3: 发现工具 ====================

    @mcp.tool(meta=TOOL_METADATA["find_similar_content"].to_dict())
    def find_similar_content(
        reg_id: str,
        query_text: str | None = None,
        source_block_id: str | None = None,
        limit: int = 5,
        exclude_same_page: bool = True,
    ) -> list[dict]:
        """[分类:发现] 查找语义相似的内容。

        发现与给定文本或内容块语义相似的其他内容。

        使用场景：查找相似内容。
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
        """[分类:发现] 比较两个章节的内容。

        并排比较两个章节的结构和内容，帮助理解它们的异同。

        使用场景：比较章节。
        前置工具：get_chapter_structure（了解章节编号）。

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

    # ==================== 导航工具 ====================

    @mcp.tool(meta=TOOL_METADATA["get_tool_guide"].to_dict())
    def get_tool_guide(
        category: str | None = None,
        include_workflows: bool = True,
    ) -> dict:
        """[分类:导航] 获取 MCP 工具使用指南。

        返回工具分类信息、推荐使用流程和使用提示，帮助理解和选择正确的工具。

        使用场景：了解可用工具、获取使用指南。
        后续工具：get_toc, list_regulations。

        Args:
            category: 过滤特定分类（可选）
                - 'base': 基础工具
                - 'multi-hop': 核心多跳
                - 'context': 上下文
                - 'discovery': 发现
                - 'navigation': 导航
            include_workflows: 是否包含工作流建议，默认 True

        Returns:
            工具指南信息，包含:
            - categories: 分类列表及统计
            - tools_by_category: 按分类组织的工具列表
            - workflows: 常见工作流（可选）
            - tips: 使用提示
        """
        return tools.get_tool_guide(category, include_workflows)

    return mcp
