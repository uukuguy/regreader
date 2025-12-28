"""GridCode 核心数据模型

定义页面存储、内容块、表格等核心数据结构。
"""

from typing import Literal

from pydantic import BaseModel, Field


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


class ContentBlock(BaseModel):
    """页面内的内容块（文本、表格、标题、列表）"""

    block_id: str = Field(description="内容块唯一标识")
    block_type: Literal["text", "table", "heading", "list"] = Field(description="内容块类型")
    order_in_page: int = Field(description="在页面中的顺序（从0开始）")
    content_markdown: str = Field(description="Markdown 格式内容")
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
    chapter_path: list[str] = Field(
        default_factory=list, description="章节路径（如 ['第六章', '事故处理', '母线故障']）"
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

    def get_tables(self) -> list[ContentBlock]:
        """获取页面中的所有表格"""
        return [block for block in self.content_blocks if block.block_type == "table"]

    def get_headings(self) -> list[ContentBlock]:
        """获取页面中的所有标题"""
        return [block for block in self.content_blocks if block.block_type == "heading"]


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
