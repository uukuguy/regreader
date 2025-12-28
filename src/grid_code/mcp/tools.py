"""MCP 工具定义

定义 GridCode 的三个核心 MCP 工具：
1. get_toc - 获取规程目录
2. smart_search - 智能检索
3. read_page_range - 读取页面范围
"""

from grid_code.exceptions import (
    ChapterNotFoundError,
    InvalidPageRangeError,
    RegulationNotFoundError,
)
from grid_code.index import HybridSearch
from grid_code.storage import PageStore
from grid_code.storage.models import (
    ChapterNode,
    DocumentStructure,
    PageContent,
    SearchResult,
    TocTree,
)


class GridCodeTools:
    """GridCode MCP 工具集"""

    def __init__(
        self,
        page_store: PageStore | None = None,
        hybrid_search: HybridSearch | None = None,
    ):
        """
        初始化工具集

        Args:
            page_store: 页面存储实例
            hybrid_search: 混合检索实例
        """
        self.page_store = page_store or PageStore()
        self.hybrid_search = hybrid_search or HybridSearch()

    def get_toc(self, reg_id: str) -> dict:
        """
        获取规程目录树

        Args:
            reg_id: 规程标识（如 'angui_2024'）

        Returns:
            目录树结构，包含标题、页码范围等信息

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        toc = self.page_store.load_toc(reg_id)
        return toc.model_dump()

    def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[dict]:
        """
        智能混合检索（关键词 + 语义）

        Args:
            query: 搜索查询（如 "母线失压"）
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选，如 "第六章"）
            limit: 返回结果数量限制
            block_types: 限定块类型列表（可选，如 ["text", "table"]）
            section_number: 精确匹配章节号（可选，如 "2.1.4.1.6"）

        Returns:
            搜索结果列表，每个结果包含:
            - page_num: 页码
            - chapter_path: 章节路径
            - snippet: 匹配片段
            - score: 相关性分数
            - source: 来源引用
            - block_id: 块标识
        """
        # 验证规程存在
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        results = self.hybrid_search.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
            block_types=block_types,
            section_number=section_number,
        )

        return [
            {
                "page_num": r.page_num,
                "chapter_path": r.chapter_path,
                "snippet": r.snippet,
                "score": r.score,
                "source": r.source,
                "block_id": r.block_id,
            }
            for r in results
        ]

    def read_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """
        读取连续页面的完整内容

        自动处理跨页表格拼接。

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            页面内容，包含:
            - content_markdown: 合并后的 Markdown 内容
            - source: 来源引用
            - has_merged_tables: 是否包含合并的跨页表格
            - pages: 原始页面数据

        Raises:
            InvalidPageRangeError: 无效的页码范围
            RegulationNotFoundError: 规程不存在
        """
        if start_page > end_page:
            raise InvalidPageRangeError(start_page, end_page)
        if start_page < 1:
            raise InvalidPageRangeError(start_page, end_page)

        # 限制单次读取的页数
        max_pages = 10
        if end_page - start_page + 1 > max_pages:
            end_page = start_page + max_pages - 1

        page_content = self.page_store.load_page_range(reg_id, start_page, end_page)

        return {
            "content_markdown": page_content.content_markdown,
            "source": page_content.source,
            "start_page": page_content.start_page,
            "end_page": page_content.end_page,
            "has_merged_tables": page_content.has_merged_tables,
            "page_count": len(page_content.pages),
        }

    def list_regulations(self) -> list[dict]:
        """
        列出所有已入库的规程

        Returns:
            规程信息列表
        """
        regulations = self.page_store.list_regulations()
        return [r.model_dump() for r in regulations]

    def get_chapter_structure(self, reg_id: str) -> dict:
        """
        获取完整章节结构

        Args:
            reg_id: 规程标识

        Returns:
            章节结构信息，包含:
            - reg_id: 规程标识
            - total_chapters: 章节总数
            - root_nodes: 顶级章节列表

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        doc_structure = self.page_store.load_document_structure(reg_id)

        if doc_structure is None:
            return {
                "reg_id": reg_id,
                "total_chapters": 0,
                "root_nodes": [],
                "message": "文档结构未生成，请重新入库以生成章节结构",
            }

        root_nodes = []
        for node_id in doc_structure.root_node_ids:
            node = doc_structure.all_nodes.get(node_id)
            if node:
                root_nodes.append({
                    "node_id": node.node_id,
                    "section_number": node.section_number,
                    "title": node.title,
                    "level": node.level,
                    "page_num": node.page_num,
                    "children_count": len(node.children_ids),
                    "has_direct_content": node.has_direct_content,
                })

        return {
            "reg_id": reg_id,
            "total_chapters": len(doc_structure.all_nodes),
            "root_nodes": root_nodes,
        }

    def read_chapter_content(
        self,
        reg_id: str,
        section_number: str,
        include_children: bool = True,
    ) -> dict:
        """
        读取指定章节的完整内容

        获取某个章节编号下的所有内容块，自动处理跨页情况。

        Args:
            reg_id: 规程标识
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
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
            ChapterNotFoundError: 章节不存在
        """
        # 验证规程存在
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 加载文档结构
        doc_structure = self.page_store.load_document_structure(reg_id)
        if doc_structure is None:
            return {
                "error": "文档结构未生成，请重新入库以生成章节结构",
                "section_number": section_number,
            }

        # 查找章节节点
        target_node = None
        for node in doc_structure.all_nodes.values():
            if node.section_number == section_number:
                target_node = node
                break

        if not target_node:
            raise ChapterNotFoundError(reg_id, section_number)

        # 获取要包含的节点ID列表
        node_ids = {target_node.node_id}
        if include_children:
            node_ids.update(self._get_all_descendant_ids(doc_structure, target_node))

        # 收集该章节的所有内容块
        content_blocks = []
        page_nums: set[int] = set()

        # 遍历所有页面，收集属于这些节点的块
        info = self.page_store.load_info(reg_id)
        for page_num in range(1, info.total_pages + 1):
            page = self.page_store.load_page(reg_id, page_num)
            for block in page.content_blocks:
                if block.chapter_node_id in node_ids:
                    content_blocks.append({
                        "page_num": page_num,
                        "order_in_page": block.order_in_page,
                        "content": block.content_markdown,
                    })
                    page_nums.add(page_num)

        # 按页码和块顺序排序
        content_blocks.sort(key=lambda x: (x["page_num"], x["order_in_page"]))

        # 合并为 Markdown
        content_markdown = self._merge_blocks_to_markdown(content_blocks)

        # 构建子章节信息
        children = []
        for child_id in target_node.children_ids:
            child_node = doc_structure.all_nodes.get(child_id)
            if child_node:
                children.append({
                    "section_number": child_node.section_number,
                    "title": child_node.title,
                    "page_num": child_node.page_num,
                })

        # 构建页码范围
        if page_nums:
            page_range = [min(page_nums), max(page_nums)]
            source = f"{reg_id} {section_number} (P{page_range[0]}-{page_range[1]})"
        else:
            page_range = [target_node.page_num, target_node.page_num]
            source = f"{reg_id} {section_number} (P{target_node.page_num})"

        return {
            "section_number": section_number,
            "title": target_node.title,
            "full_path": doc_structure.get_chapter_path(target_node.node_id),
            "content_markdown": content_markdown,
            "page_range": page_range,
            "block_count": len(content_blocks),
            "children": children,
            "children_included": include_children,
            "source": source,
        }

    def _get_all_descendant_ids(
        self,
        doc_structure: DocumentStructure,
        node: ChapterNode,
    ) -> set[str]:
        """
        递归获取所有后代节点ID

        Args:
            doc_structure: 文档结构
            node: 当前节点

        Returns:
            所有后代节点ID的集合
        """
        descendants: set[str] = set()
        for child_id in node.children_ids:
            descendants.add(child_id)
            child_node = doc_structure.all_nodes.get(child_id)
            if child_node:
                descendants.update(self._get_all_descendant_ids(doc_structure, child_node))
        return descendants

    def _merge_blocks_to_markdown(self, content_blocks: list[dict]) -> str:
        """
        合并内容块为 Markdown 字符串

        Args:
            content_blocks: 内容块列表

        Returns:
            合并后的 Markdown 字符串
        """
        parts = []
        for item in content_blocks:
            content = item["content"].strip()
            if content:
                parts.append(content)
        return "\n\n".join(parts)
