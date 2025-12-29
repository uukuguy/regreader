"""GridCode 核心数据模型

定义页面存储、内容块、表格等核心数据结构。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class TableCell(BaseModel):
    """表格单元格"""

    row: int = Field(description="行索引（从0开始）")
    col: int = Field(description="列索引（从0开始）")
    content: str = Field(description="单元格内容")
    row_span: int = Field(default=1, description="跨行数")
    col_span: int = Field(default=1, description="跨列数")


class TableMeta(BaseModel):
    """表格元数据"""

    table_id: str = Field(description="表格唯一标识")
    caption: str | None = Field(default=None, description="表格标题（如 '表6-2 母线故障处置'）")
    is_truncated: bool = Field(default=False, description="是否被截断（跨页）")
    row_headers: list[str] = Field(default_factory=list, description="行标题列表")
    col_headers: list[str] = Field(default_factory=list, description="列标题列表")
    row_count: int = Field(description="行数")
    col_count: int = Field(description="列数")
    cells: list[TableCell] = Field(default_factory=list, description="单元格数据")


class Annotation(BaseModel):
    """页面注释（页脚注等）"""

    annotation_id: str = Field(description="注释标识（如 '注1', '方案A'）")
    content: str = Field(description="注释内容")
    related_blocks: list[str] = Field(default_factory=list, description="关联的 block_id 列表")


class ChapterNode(BaseModel):
    """章节节点（文档结构树）

    用于表示文档的章节层级结构，支持父子关系和内容块关联。
    """

    node_id: str = Field(description="节点唯一标识")
    section_number: str = Field(description="章节编号，如 '2.1.4.1.6'")
    title: str = Field(description="章节标题（纯文本，不含编号）")
    level: int = Field(description="章节层级 1-6")
    page_num: int = Field(description="章节首次出现的页码")

    # 层级关系
    parent_id: str | None = Field(default=None, description="父节点ID")
    children_ids: list[str] = Field(default_factory=list, description="子节点ID列表")

    # 内容关联
    content_block_ids: list[str] = Field(
        default_factory=list, description="属于此章节的内容块ID列表（跨页）"
    )

    # 元数据
    has_direct_content: bool = Field(
        default=False, description="章节号后是否有直接内容（如长段落）"
    )
    direct_content: str | None = Field(
        default=None, description="章节号后的直接内容（如有）"
    )

    @property
    def full_title(self) -> str:
        """返回完整标题（编号 + 标题）"""
        return f"{self.section_number} {self.title}" if self.title else self.section_number


class ActiveChapter(BaseModel):
    """活跃章节（本页相关的章节）

    包含本页首次出现的章节和从上页延续的章节。
    """

    node_id: str = Field(description="节点唯一标识")
    section_number: str = Field(description="章节编号，如 '2.1.4.1.6'")
    title: str = Field(description="章节标题（纯文本，不含编号）")
    level: int = Field(description="章节层级 1-6")
    page_num: int = Field(description="章节首次出现的页码")
    inherited: bool = Field(
        default=False, description="是否为延续的章节（从上页继承）"
    )
    has_direct_content: bool = Field(
        default=False, description="章节号后是否有直接内容"
    )

    @property
    def full_title(self) -> str:
        """返回完整标题（编号 + 标题）"""
        return f"{self.section_number} {self.title}" if self.title else self.section_number


class ContentBlock(BaseModel):
    """页面内的内容块（文本、表格、标题、列表、章节内容）

    块类型说明：
    - "text": 普通段落文本
    - "table": 表格
    - "heading": 纯章节标题（无直接内容）
    - "list": 列表
    - "section_content": 章节号后直接跟随的内容
      （如 "2.1.1.1.1 复奉-宾金...这些内容"，编号存在 ChapterNode，内容存在此块）
    """

    block_id: str = Field(description="内容块唯一标识")
    block_type: Literal["text", "table", "heading", "list", "section_content"] = Field(
        description="内容块类型"
    )
    order_in_page: int = Field(description="在页面中的顺序（从0开始）")
    content_markdown: str = Field(description="Markdown 格式内容")

    # 块级章节信息
    chapter_path: list[str] = Field(
        default_factory=list, description="块级章节路径（完整路径）"
    )
    chapter_node_id: str | None = Field(default=None, description="所属章节节点ID")

    # 原有字段
    table_meta: TableMeta | None = Field(
        default=None, description="表格元数据（仅 block_type='table' 时有效）"
    )
    heading_level: int | None = Field(
        default=None, description="标题级别（1-6，仅 block_type='heading' 时有效）"
    )


class PageDocument(BaseModel):
    """单页文档模型 - 核心存储单位"""

    reg_id: str = Field(description="规程标识（如 'angui_2024'）")
    page_num: int = Field(description="页码（从1开始）")

    # 本页活跃的章节（包括首次出现和延续的章节）
    active_chapters: list[ActiveChapter] = Field(
        default_factory=list, description="本页活跃的章节（首次出现 + 延续）"
    )

    # 内容块列表
    content_blocks: list[ContentBlock] = Field(
        default_factory=list, description="按阅读顺序排列的内容块"
    )

    # 页面级 Markdown（完整页面内容，供 LLM 阅读）
    content_markdown: str = Field(default="", description="页面完整 Markdown 内容")

    # 跨页标记
    continues_from_prev: bool = Field(default=False, description="是否从上一页延续（如跨页表格）")
    continues_to_next: bool = Field(default=False, description="是否延续到下一页")

    # 页面级注释
    annotations: list[Annotation] = Field(default_factory=list, description="页脚注释列表")

    @property
    def source(self) -> str:
        """返回来源引用字符串"""
        return f"{self.reg_id} P{self.page_num}"

    @property
    def chapter_path(self) -> list[str]:
        """从活跃章节生成章节路径（用于索引层兼容）"""
        return [ch.full_title for ch in self.active_chapters]

    def get_tables(self) -> list[ContentBlock]:
        """获取页面中的所有表格"""
        return [block for block in self.content_blocks if block.block_type == "table"]

    def get_headings(self) -> list[ContentBlock]:
        """获取页面中的所有标题"""
        return [block for block in self.content_blocks if block.block_type == "heading"]


class DocumentStructure(BaseModel):
    """文档章节结构（全局）

    存储文档的完整章节树结构，支持快速导航和章节查询。
    """

    reg_id: str = Field(description="规程标识")
    all_nodes: dict[str, ChapterNode] = Field(
        default_factory=dict, description="所有章节节点映射 {node_id: ChapterNode}"
    )
    root_node_ids: list[str] = Field(default_factory=list, description="顶级章节节点ID列表")

    def get_chapter_path(self, node_id: str) -> list[str]:
        """获取章节完整路径

        Args:
            node_id: 章节节点ID

        Returns:
            章节路径列表，如 ['2 安全稳定控制装置', '2.1 分区概述', '2.1.4 西南分区']
        """
        path = []
        node = self.all_nodes.get(node_id)
        while node:
            path.insert(0, node.full_title)
            node = self.all_nodes.get(node.parent_id) if node.parent_id else None
        return path

    def get_node_by_section_number(self, section_number: str) -> ChapterNode | None:
        """根据章节编号查找节点

        Args:
            section_number: 章节编号，如 '2.1.4.1.6'

        Returns:
            匹配的章节节点，如果不存在则返回 None
        """
        for node in self.all_nodes.values():
            if node.section_number == section_number:
                return node
        return None

    def get_chapter_tree(self) -> list[TocItem]:
        """转换为目录树格式（用于 MCP get_toc() 工具）

        Returns:
            TocItem 列表，表示顶级目录项及其子项
        """

        def build_toc_item(node_id: str) -> TocItem:
            node = self.all_nodes[node_id]
            children = [build_toc_item(child_id) for child_id in node.children_ids]
            return TocItem(
                title=node.full_title,
                level=node.level,
                page_start=node.page_num,
                page_end=None,  # 后续可计算
                children=children,
            )

        return [build_toc_item(root_id) for root_id in self.root_node_ids]

    def get_all_nodes_at_level(self, level: int) -> list[ChapterNode]:
        """获取指定层级的所有节点

        Args:
            level: 章节层级（1-6）

        Returns:
            该层级的所有章节节点列表
        """
        return [node for node in self.all_nodes.values() if node.level == level]


class TocItem(BaseModel):
    """目录项"""

    title: str = Field(description="章节标题")
    level: int = Field(description="层级（1=章，2=节，3=小节...）")
    page_start: int = Field(description="起始页码")
    page_end: int | None = Field(default=None, description="结束页码")
    children: list["TocItem"] = Field(default_factory=list, description="子章节")


class TocTree(BaseModel):
    """目录树"""

    reg_id: str = Field(description="规程标识")
    title: str = Field(description="规程标题")
    total_pages: int = Field(description="总页数")
    items: list[TocItem] = Field(default_factory=list, description="顶级目录项")


class SearchResult(BaseModel):
    """搜索结果"""

    reg_id: str = Field(description="规程标识")
    page_num: int = Field(description="页码")
    chapter_path: list[str] = Field(description="章节路径")
    snippet: str = Field(description="匹配片段")
    score: float = Field(description="相关性分数")
    block_id: str | None = Field(default=None, description="匹配的内容块ID")

    @property
    def source(self) -> str:
        """返回来源引用字符串"""
        chapter_str = " > ".join(self.chapter_path) if self.chapter_path else ""
        return f"{self.reg_id} P{self.page_num}" + (f" ({chapter_str})" if chapter_str else "")


class PageContent(BaseModel):
    """页面范围读取结果"""

    reg_id: str = Field(description="规程标识")
    start_page: int = Field(description="起始页码")
    end_page: int = Field(description="结束页码")
    content_markdown: str = Field(description="合并后的 Markdown 内容")
    pages: list[PageDocument] = Field(description="原始页面列表")
    has_merged_tables: bool = Field(default=False, description="是否包含合并的跨页表格")

    @property
    def source(self) -> str:
        """返回来源引用字符串"""
        if self.start_page == self.end_page:
            return f"{self.reg_id} P{self.start_page}"
        return f"{self.reg_id} P{self.start_page}-{self.end_page}"


class RegulationInfo(BaseModel):
    """规程基本信息"""

    reg_id: str = Field(description="规程标识")
    title: str = Field(description="规程标题")
    source_file: str = Field(description="源文件名")
    total_pages: int = Field(description="总页数")
    indexed_at: str = Field(description="索引时间（ISO 格式）")


# ============================================================================
# 表格注册表模型（全局表格索引）
# ============================================================================


class TableSegment(BaseModel):
    """表格段（跨页表格的单个部分）"""

    segment_id: str = Field(description="原始 table_id")
    page_num: int = Field(description="所在页码")
    block_id: str = Field(description="所在内容块ID")
    is_header: bool = Field(default=False, description="是否包含表头")
    row_start: int = Field(default=0, description="起始行（在合并表格中的位置）")
    row_end: int = Field(default=0, description="结束行（在合并表格中的位置）")


class TableEntry(BaseModel):
    """表格注册表条目"""

    table_id: str = Field(description="统一ID（跨页表格共用首个段落的ID）")
    caption: str | None = Field(default=None, description="表格标题")
    chapter_path: list[str] = Field(default_factory=list, description="所属章节路径")
    page_start: int = Field(description="起始页码")
    page_end: int = Field(description="结束页码")
    is_cross_page: bool = Field(default=False, description="是否为跨页表格")
    segments: list[TableSegment] = Field(default_factory=list, description="表格段列表")
    row_count: int = Field(description="合并后总行数")
    col_count: int = Field(description="列数")
    col_headers: list[str] = Field(default_factory=list, description="列标题")
    merged_markdown: str = Field(default="", description="合并后的 Markdown 内容")
    created_at: str = Field(default="", description="创建时间（ISO 格式）")


class TableRegistry(BaseModel):
    """表格注册表（全局表格索引）"""

    reg_id: str = Field(description="规程标识")
    version: str = Field(default="1.0", description="注册表版本")
    total_tables: int = Field(default=0, description="表格总数")
    cross_page_tables: int = Field(default=0, description="跨页表格数")
    tables: dict[str, TableEntry] = Field(
        default_factory=dict, description="表格映射 {table_id: TableEntry}"
    )
    segment_to_table: dict[str, str] = Field(
        default_factory=dict, description="段落ID到主表格ID映射"
    )
    page_to_tables: dict[int, list[str]] = Field(
        default_factory=dict, description="页码到表格ID列表映射"
    )
