"""RegReader 工具协议定义

定义统一的工具接口协议，支持本地和 MCP 两种实现方式。
所有工具实现（RegReaderTools 和 RegReaderMCPToolsAdapter）都遵循此协议。
"""

from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class RegReaderToolsProtocol(Protocol):
    """RegReader 工具协议

    定义所有工具方法的接口签名。
    本地实现 (RegReaderTools) 和 MCP 适配器 (RegReaderMCPToolsAdapter)
    都实现此协议，使 CLI 代码无需关心具体实现方式。
    """

    # ==================== 基础工具 ====================

    def get_toc(self, reg_id: str) -> dict:
        """获取规程目录树

        Args:
            reg_id: 规程标识（如 'angui_2024'）

        Returns:
            目录树结构，包含标题、页码范围等信息
        """
        ...

    def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """智能混合检索（关键词 + 语义）

        Args:
            query: 搜索查询
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制
            block_types: 限定块类型列表（可选）
            section_number: 精确匹配章节号（可选）

        Returns:
            搜索结果列表
        """
        ...

    def read_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """读取连续页面的完整内容

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            页面内容字典
        """
        ...

    def list_regulations(self) -> list[dict]:
        """列出所有已入库的规程

        Returns:
            规程信息列表
        """
        ...

    def get_chapter_structure(self, reg_id: str) -> dict:
        """获取完整章节结构

        Args:
            reg_id: 规程标识

        Returns:
            章节结构信息
        """
        ...

    def get_page_chapter_info(
        self,
        reg_id: str,
        page_num: int,
    ) -> dict:
        """获取指定页面的章节信息

        Args:
            reg_id: 规程标识
            page_num: 页码

        Returns:
            页面章节信息
        """
        ...

    def read_chapter_content(
        self,
        reg_id: str,
        section_number: str,
        include_children: bool = True,
    ) -> dict:
        """读取指定章节的完整内容

        Args:
            reg_id: 规程标识
            section_number: 章节编号
            include_children: 是否包含子章节内容

        Returns:
            章节内容
        """
        ...

    # ==================== Phase 1: 核心多跳工具 ====================

    def lookup_annotation(
        self,
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """查找并返回指定注释的完整内容

        Args:
            reg_id: 规程标识
            annotation_id: 注释标识
            page_hint: 页码提示（可选）

        Returns:
            注释信息
        """
        ...

    def search_tables(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
        limit: int = 10,
    ) -> list[dict]:
        """搜索表格

        Args:
            query: 搜索查询
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            search_mode: 搜索模式
            limit: 返回结果数量限制

        Returns:
            搜索结果列表
        """
        ...

    def resolve_reference(
        self,
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """解析并解决交叉引用

        Args:
            reg_id: 规程标识
            reference_text: 引用文本

        Returns:
            解析后的引用内容
        """
        ...

    # ==================== Phase 2: 上下文工具 ====================

    def search_annotations(
        self,
        reg_id: str,
        pattern: str | None = None,
        annotation_type: str | None = None,
    ) -> list[dict]:
        """搜索规程中的所有注释

        Args:
            reg_id: 规程标识
            pattern: 内容匹配模式（可选）
            annotation_type: 注释类型过滤（可选）

        Returns:
            匹配的注释列表
        """
        ...

    def get_table_by_id(
        self,
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """获取完整表格内容

        Args:
            reg_id: 规程标识
            table_id: 表格标识
            include_merged: 如果表格跨页，是否自动合并

        Returns:
            表格完整信息
        """
        ...

    def get_block_with_context(
        self,
        reg_id: str,
        block_id: str,
        context_blocks: int = 2,
    ) -> dict:
        """读取指定内容块及其上下文

        Args:
            reg_id: 规程标识
            block_id: 内容块标识
            context_blocks: 上下文块数量

        Returns:
            内容块及上下文
        """
        ...

    # ==================== Phase 3: 发现工具 ====================

    def find_similar_content(
        self,
        reg_id: str,
        query_text: str | None = None,
        source_block_id: str | None = None,
        limit: int = 5,
        exclude_same_page: bool = True,
    ) -> list[dict]:
        """查找语义相似的内容

        Args:
            reg_id: 规程标识
            query_text: 查询文本（与 source_block_id 二选一）
            source_block_id: 源内容块ID（与 query_text 二选一）
            limit: 返回结果数量限制
            exclude_same_page: 是否排除同页内容

        Returns:
            相似内容列表
        """
        ...

    def compare_sections(
        self,
        reg_id: str,
        section_a: str,
        section_b: str,
        include_tables: bool = True,
    ) -> dict:
        """比较两个章节的内容

        Args:
            reg_id: 规程标识
            section_a: 第一个章节编号
            section_b: 第二个章节编号
            include_tables: 是否包含表格内容

        Returns:
            比较结果
        """
        ...
