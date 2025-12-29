"""MCP 工具定义

定义 GridCode 的三个核心 MCP 工具：
1. get_toc - 获取规程目录
2. smart_search - 智能检索
3. read_page_range - 读取页面范围
"""

import re
from typing import Literal

from loguru import logger

from grid_code.exceptions import (
    AnnotationNotFoundError,
    ChapterNotFoundError,
    InvalidPageRangeError,
    ReferenceResolutionError,
    RegulationNotFoundError,
    TableNotFoundError,
)
from grid_code.index import HybridSearch
from grid_code.index.table_search import TableHybridSearch
from grid_code.storage import PageStore
from grid_code.storage.models import (
    ActiveChapter,
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
        table_search: TableHybridSearch | None = None,
    ):
        """
        初始化工具集

        Args:
            page_store: 页面存储实例
            hybrid_search: 混合检索实例
            table_search: 表格混合检索实例
        """
        self.page_store = page_store or PageStore()
        self.hybrid_search = hybrid_search or HybridSearch()
        self._table_search = table_search

    @property
    def table_search(self) -> TableHybridSearch:
        """获取表格混合检索实例（延迟加载）"""
        if self._table_search is None:
            self._table_search = TableHybridSearch()
        return self._table_search

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

    def get_page_chapter_info(
        self,
        reg_id: str,
        page_num: int,
    ) -> dict:
        """
        获取指定页面的章节信息

        返回该页面的所有活跃章节，包括从上页延续的章节和本页首次出现的章节。

        Args:
            reg_id: 规程标识
            page_num: 页码

        Returns:
            页面章节信息，包含:
            - reg_id: 规程标识
            - page_num: 页码
            - active_chapters: 活跃章节列表
            - total_chapters: 总章节数
            - new_chapters_count: 本页首次出现的章节数
            - inherited_chapters_count: 从上页延续的章节数

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        # 验证规程存在
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 加载页面
        page = self.page_store.load_page(reg_id, page_num)

        # 转换活跃章节为字典格式
        active_chapters_info = [
            {
                "node_id": ch.node_id,
                "section_number": ch.section_number,
                "title": ch.title,
                "level": ch.level,
                "page_num": ch.page_num,
                "inherited": ch.inherited,
                "has_direct_content": ch.has_direct_content,
                "full_title": ch.full_title,
            }
            for ch in page.active_chapters
        ]

        return {
            "reg_id": reg_id,
            "page_num": page_num,
            "active_chapters": active_chapters_info,
            "total_chapters": len(active_chapters_info),
            "new_chapters_count": sum(1 for ch in page.active_chapters if not ch.inherited),
            "inherited_chapters_count": sum(1 for ch in page.active_chapters if ch.inherited),
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

    # ==================== Phase 1: 核心多跳工具 ====================

    def lookup_annotation(
        self,
        reg_id: str,
        annotation_id: str,
        page_hint: int | None = None,
    ) -> dict:
        """
        查找并返回指定注释的完整内容

        处理表格单元格中常见的 "见注1"、"方案A" 等引用。
        支持多种注释标识变体：注1/注①/注一、方案A/方案甲 等。

        Args:
            reg_id: 规程标识，如 'angui_2024'
            annotation_id: 注释标识，如 '注1', '注①', '方案A', '方案甲'
            page_hint: 页码提示（可选），优先从该页附近搜索

        Returns:
            注释信息，包含:
            - annotation_id: 注释标识
            - content: 注释完整内容
            - page_num: 所在页码
            - related_blocks: 关联的内容块ID列表
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
            AnnotationNotFoundError: 注释不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 标准化注释ID（处理变体）
        normalized_id = self._normalize_annotation_id(annotation_id)

        # 获取规程信息
        info = self.page_store.load_info(reg_id)
        total_pages = info.total_pages

        # 确定搜索顺序（如果有 page_hint，优先搜索附近页面）
        if page_hint and 1 <= page_hint <= total_pages:
            # 从 page_hint 向两边扩展搜索
            search_order = self._get_search_order_from_hint(page_hint, total_pages)
        else:
            # 顺序搜索所有页面
            search_order = list(range(1, total_pages + 1))

        # 搜索注释
        for page_num in search_order:
            page = self.page_store.load_page(reg_id, page_num)
            for annotation in page.annotations:
                # 检查原始ID或标准化ID匹配
                if (
                    annotation.annotation_id == annotation_id
                    or self._normalize_annotation_id(annotation.annotation_id)
                    == normalized_id
                ):
                    return {
                        "annotation_id": annotation.annotation_id,
                        "content": annotation.content,
                        "page_num": page_num,
                        "related_blocks": annotation.related_blocks,
                        "source": f"{reg_id} P{page_num} {annotation.annotation_id}",
                    }

        raise AnnotationNotFoundError(reg_id, annotation_id)

    def _normalize_annotation_id(self, annotation_id: str) -> str:
        """
        标准化注释ID，处理各种变体

        Args:
            annotation_id: 原始注释标识

        Returns:
            标准化后的注释标识（小写、数字统一）
        """
        result = annotation_id.lower()

        # 中文数字转阿拉伯数字
        cn_nums = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                   "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        for cn, num in cn_nums.items():
            result = result.replace(cn, num)

        # 圈数字转普通数字
        circle_nums = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
                       "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10"}
        for circle, num in circle_nums.items():
            result = result.replace(circle, num)

        # 中文大写字母转小写
        cn_letters = {"甲": "a", "乙": "b", "丙": "c", "丁": "d"}
        for cn, letter in cn_letters.items():
            result = result.replace(cn, letter)

        return result

    def _get_search_order_from_hint(
        self, page_hint: int, total_pages: int
    ) -> list[int]:
        """
        根据页码提示生成搜索顺序

        Args:
            page_hint: 提示页码
            total_pages: 总页数

        Returns:
            搜索顺序列表（从提示页向两边扩展）
        """
        order = [page_hint]
        for offset in range(1, total_pages):
            if page_hint - offset >= 1:
                order.append(page_hint - offset)
            if page_hint + offset <= total_pages:
                order.append(page_hint + offset)
            if len(order) >= total_pages:
                break
        return order

    def search_tables(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
        limit: int = 10,
    ) -> list[dict]:
        """
        搜索表格（支持精确关键词和模糊语义搜索）

        Args:
            query: 搜索查询
                - 表格标题: "表6-2", "母线故障处置"
                - 内容关键词: "母线失压", "复奉直流"
                - 章节范围: "西南分区"
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            search_mode: 搜索模式
                - "keyword": 仅关键词精确匹配
                - "semantic": 仅语义相似度搜索
                - "hybrid": 混合搜索（默认）
            limit: 返回结果数量限制

        Returns:
            搜索结果列表，每个包含:
            - table_id: 表格标识
            - caption: 表格标题
            - reg_id: 规程标识
            - page_start: 起始页码
            - page_end: 结束页码
            - pages: 所有相关页码列表
            - chapter_path: 章节路径
            - is_cross_page: 是否跨页
            - row_count: 行数
            - col_count: 列数
            - col_headers: 列标题
            - snippet: 匹配片段预览
            - score: 相关性分数
            - match_type: 匹配类型
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 尝试使用表格索引搜索
        if self.table_search.has_index(reg_id):
            results = self.table_search.search(
                query=query,
                reg_id=reg_id,
                chapter_scope=chapter_scope,
                search_mode=search_mode,
                limit=limit,
            )

            return [
                {
                    "table_id": r.table_id,
                    "caption": r.caption,
                    "reg_id": r.reg_id,
                    "page_start": r.page_start,
                    "page_end": r.page_end,
                    "pages": r.pages,
                    "chapter_path": r.chapter_path,
                    "is_cross_page": r.is_cross_page,
                    "row_count": r.row_count,
                    "col_count": r.col_count,
                    "col_headers": r.col_headers,
                    "snippet": r.snippet,
                    "score": r.score,
                    "match_type": r.match_type,
                    "source": r.source,
                }
                for r in results
            ]

        # 降级：使用原始遍历方法
        logger.warning(f"[search_tables] 规程 {reg_id} 没有表格索引，使用降级遍历搜索")
        return self._search_tables_fallback(query, reg_id, chapter_scope, limit)

    def _search_tables_fallback(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None,
        limit: int,
    ) -> list[dict]:
        """降级的表格搜索（遍历所有页面）"""
        results = []
        query_lower = query.lower()

        info = self.page_store.load_info(reg_id)

        for page_num in range(1, info.total_pages + 1):
            page = self.page_store.load_page(reg_id, page_num)

            if chapter_scope:
                chapter_path_str = " ".join(page.chapter_path)
                if chapter_scope not in chapter_path_str:
                    continue

            for block in page.content_blocks:
                if block.block_type != "table" or not block.table_meta:
                    continue

                table_meta = block.table_meta
                match_type = None

                caption_match = table_meta.caption and query_lower in table_meta.caption.lower()
                cell_match = any(query_lower in cell.content.lower() for cell in table_meta.cells)

                if caption_match and cell_match:
                    match_type = "both"
                elif caption_match:
                    match_type = "caption"
                elif cell_match:
                    match_type = "content"

                if match_type:
                    results.append({
                        "table_id": table_meta.table_id,
                        "caption": table_meta.caption,
                        "reg_id": reg_id,
                        "page_start": page_num,
                        "page_end": page_num,
                        "pages": [page_num],
                        "chapter_path": block.chapter_path,
                        "is_cross_page": table_meta.is_truncated,
                        "row_count": table_meta.row_count,
                        "col_count": table_meta.col_count,
                        "col_headers": table_meta.col_headers,
                        "snippet": block.content_markdown[:200],
                        "score": 1.0 if match_type == "caption" else 0.8,
                        "match_type": match_type,
                        "source": f"{reg_id} P{page_num}"
                        + (f" {table_meta.caption}" if table_meta.caption else ""),
                    })

        priority = {"caption": 0, "both": 1, "content": 2}
        results.sort(key=lambda x: priority.get(x["match_type"], 3))

        return results[:limit]

    def resolve_reference(
        self,
        reg_id: str,
        reference_text: str,
    ) -> dict:
        """
        解析并解决交叉引用

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
            - reference_type: 引用类型（'chapter', 'section', 'table', 'annotation', 'appendix', 'article'）
            - parsed_target: 解析出的目标（如 "第六章", "表6-2"）
            - resolved: 是否成功解析
            - target_location: 目标位置信息
            - preview: 目标内容预览（前300字符）
            - source: 完整来源引用
            - error: 错误信息（如未找到）

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 尝试各种引用模式
        ref_result = self._parse_reference(reference_text)
        if not ref_result:
            raise ReferenceResolutionError(reference_text, "无法识别引用格式")

        ref_type, parsed_target = ref_result

        # 根据引用类型解析目标
        try:
            if ref_type == "chapter":
                return self._resolve_chapter_reference(reg_id, parsed_target, reference_text)
            elif ref_type == "section":
                return self._resolve_section_reference(reg_id, parsed_target, reference_text)
            elif ref_type == "table":
                return self._resolve_table_reference(reg_id, parsed_target, reference_text)
            elif ref_type == "annotation":
                return self._resolve_annotation_reference(reg_id, parsed_target, reference_text)
            elif ref_type == "appendix":
                return self._resolve_appendix_reference(reg_id, parsed_target, reference_text)
            elif ref_type == "article":
                return self._resolve_article_reference(reg_id, parsed_target, reference_text)
            else:
                raise ReferenceResolutionError(reference_text, f"不支持的引用类型: {ref_type}")
        except (AnnotationNotFoundError, ChapterNotFoundError, TableNotFoundError) as e:
            return {
                "reference_type": ref_type,
                "parsed_target": parsed_target,
                "resolved": False,
                "target_location": None,
                "preview": None,
                "source": None,
                "error": str(e),
            }

    def _parse_reference(self, reference_text: str) -> tuple[str, str] | None:
        """
        解析引用文本，识别引用类型和目标

        Args:
            reference_text: 引用文本

        Returns:
            (引用类型, 解析目标) 或 None（如果无法识别）
        """
        text = reference_text.strip()

        # 中文数字映射
        cn_to_num = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                     "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
                     "十一": "11", "十二": "12"}

        # 章节编号引用: "见2.1.4", "参见2.1.4.1.6"
        section_pattern = r"(?:见|参见|详见|按)?(\d+(?:\.\d+)+)"
        match = re.search(section_pattern, text)
        if match:
            return ("section", match.group(1))

        # 章引用: "见第六章", "详见第3章"
        chapter_pattern = r"(?:见|参见|详见)?第([一二三四五六七八九十\d]+)章"
        match = re.search(chapter_pattern, text)
        if match:
            chapter_num = match.group(1)
            # 转换中文数字
            if chapter_num in cn_to_num:
                chapter_num = cn_to_num[chapter_num]
            return ("chapter", chapter_num)

        # 节引用: "见第三节"
        section_cn_pattern = r"(?:见|参见|详见)?第([一二三四五六七八九十\d]+)节"
        match = re.search(section_cn_pattern, text)
        if match:
            section_num = match.group(1)
            if section_num in cn_to_num:
                section_num = cn_to_num[section_num]
            return ("section", section_num)

        # 表格引用: "见表6-2", "参见表1", "附表A"
        table_pattern = r"(?:见|参见|详见)?(?:附)?表(\d+[-－]?\d*|[A-Za-z])"
        match = re.search(table_pattern, text)
        if match:
            return ("table", f"表{match.group(1)}")

        # 注释引用: "见注1", "参见方案A"
        annotation_pattern = r"(?:见|参见)?(注[0-9①②③④⑤⑥⑦⑧⑨⑩一二三四五六七八九十\d]+|方案[A-Za-z甲乙丙丁])"
        match = re.search(annotation_pattern, text)
        if match:
            return ("annotation", match.group(1))

        # 附录引用: "见附录A", "详见附录三"
        appendix_pattern = r"(?:见|参见|详见)?附录([A-Za-z一二三四五六七八九十])"
        match = re.search(appendix_pattern, text)
        if match:
            appendix_id = match.group(1)
            if appendix_id in cn_to_num:
                appendix_id = cn_to_num[appendix_id]
            return ("appendix", f"附录{appendix_id}")

        # 条款引用: "见第X条", "按本规程第Y条"
        article_pattern = r"(?:见|参见|按.*)?第([一二三四五六七八九十百千\d]+)条"
        match = re.search(article_pattern, text)
        if match:
            article_num = match.group(1)
            if article_num in cn_to_num:
                article_num = cn_to_num[article_num]
            return ("article", article_num)

        return None

    def _resolve_chapter_reference(
        self, reg_id: str, chapter_num: str, original_text: str
    ) -> dict:
        """解析章引用"""
        doc_structure = self.page_store.load_document_structure(reg_id)
        if not doc_structure:
            raise ReferenceResolutionError(original_text, "文档结构未生成")

        # 查找匹配的章节（第X章对应顶级节点）
        for node in doc_structure.all_nodes.values():
            if node.level == 1 and node.section_number == chapter_num:
                # 获取章节内容预览
                content = self.read_chapter_content(reg_id, node.section_number, include_children=False)
                preview = content.get("content_markdown", "")[:300]

                return {
                    "reference_type": "chapter",
                    "parsed_target": f"第{chapter_num}章",
                    "resolved": True,
                    "target_location": {
                        "section_number": node.section_number,
                        "title": node.title,
                        "page_num": node.page_num,
                        "node_id": node.node_id,
                    },
                    "preview": preview,
                    "source": f"{reg_id} {node.section_number} {node.title} (P{node.page_num})",
                }

        raise ChapterNotFoundError(reg_id, f"第{chapter_num}章")

    def _resolve_section_reference(
        self, reg_id: str, section_number: str, original_text: str
    ) -> dict:
        """解析章节编号引用"""
        doc_structure = self.page_store.load_document_structure(reg_id)
        if not doc_structure:
            raise ReferenceResolutionError(original_text, "文档结构未生成")

        node = doc_structure.get_node_by_section_number(section_number)
        if not node:
            raise ChapterNotFoundError(reg_id, section_number)

        # 获取章节内容预览
        content = self.read_chapter_content(reg_id, section_number, include_children=False)
        preview = content.get("content_markdown", "")[:300]

        return {
            "reference_type": "section",
            "parsed_target": section_number,
            "resolved": True,
            "target_location": {
                "section_number": node.section_number,
                "title": node.title,
                "page_num": node.page_num,
                "node_id": node.node_id,
            },
            "preview": preview,
            "source": f"{reg_id} {node.section_number} {node.title} (P{node.page_num})",
        }

    def _resolve_table_reference(
        self, reg_id: str, table_target: str, original_text: str
    ) -> dict:
        """解析表格引用"""
        # 搜索表格
        results = self.search_tables(table_target, reg_id, search_cells=False, limit=1)
        if not results:
            raise TableNotFoundError(reg_id, table_target)

        table = results[0]
        return {
            "reference_type": "table",
            "parsed_target": table_target,
            "resolved": True,
            "target_location": {
                "table_id": table["table_id"],
                "caption": table["caption"],
                "page_num": table["page_num"],
                "is_truncated": table["is_truncated"],
            },
            "preview": f"表格: {table['caption'] or table_target}, {table['row_count']}行 x {table['col_count']}列",
            "source": table["source"],
        }

    def _resolve_annotation_reference(
        self, reg_id: str, annotation_id: str, original_text: str
    ) -> dict:
        """解析注释引用"""
        result = self.lookup_annotation(reg_id, annotation_id)
        return {
            "reference_type": "annotation",
            "parsed_target": annotation_id,
            "resolved": True,
            "target_location": {
                "annotation_id": result["annotation_id"],
                "page_num": result["page_num"],
            },
            "preview": result["content"][:300],
            "source": result["source"],
        }

    def _resolve_appendix_reference(
        self, reg_id: str, appendix_id: str, original_text: str
    ) -> dict:
        """解析附录引用"""
        # 搜索附录（通常在目录或章节结构中）
        doc_structure = self.page_store.load_document_structure(reg_id)
        if doc_structure:
            for node in doc_structure.all_nodes.values():
                if appendix_id.lower() in node.title.lower() or appendix_id.lower() in node.section_number.lower():
                    content = self.read_chapter_content(reg_id, node.section_number, include_children=False)
                    preview = content.get("content_markdown", "")[:300]
                    return {
                        "reference_type": "appendix",
                        "parsed_target": appendix_id,
                        "resolved": True,
                        "target_location": {
                            "section_number": node.section_number,
                            "title": node.title,
                            "page_num": node.page_num,
                        },
                        "preview": preview,
                        "source": f"{reg_id} {node.section_number} {node.title} (P{node.page_num})",
                    }

        # 如果在章节结构中找不到，尝试全文搜索
        results = self.smart_search(appendix_id, reg_id, limit=1)
        if results:
            return {
                "reference_type": "appendix",
                "parsed_target": appendix_id,
                "resolved": True,
                "target_location": {
                    "page_num": results[0]["page_num"],
                },
                "preview": results[0]["snippet"],
                "source": results[0]["source"],
            }

        raise ReferenceResolutionError(original_text, f"未找到{appendix_id}")

    def _resolve_article_reference(
        self, reg_id: str, article_num: str, original_text: str
    ) -> dict:
        """解析条款引用"""
        # 搜索条款
        results = self.smart_search(f"第{article_num}条", reg_id, limit=3)
        if results:
            return {
                "reference_type": "article",
                "parsed_target": f"第{article_num}条",
                "resolved": True,
                "target_location": {
                    "page_num": results[0]["page_num"],
                    "chapter_path": results[0]["chapter_path"],
                },
                "preview": results[0]["snippet"],
                "source": results[0]["source"],
            }

        raise ReferenceResolutionError(original_text, f"未找到第{article_num}条")

    # ==================== Phase 2: 上下文工具 ====================

    def search_annotations(
        self,
        reg_id: str,
        pattern: str | None = None,
        annotation_type: str | None = None,
    ) -> list[dict]:
        """
        搜索规程中的所有注释

        Args:
            reg_id: 规程标识
            pattern: 内容匹配模式（可选），支持简单文本匹配
            annotation_type: 注释类型过滤（可选）
                - 'note': 注释类（注1, 注①等）
                - 'plan': 方案类（方案A, 方案甲等）
                - None: 不过滤

        Returns:
            匹配的注释列表，每个包含:
            - annotation_id: 注释标识
            - content: 注释完整内容（截取前200字符）
            - page_num: 所在页码
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        results = []
        info = self.page_store.load_info(reg_id)

        for page_num in range(1, info.total_pages + 1):
            page = self.page_store.load_page(reg_id, page_num)

            for annotation in page.annotations:
                # 类型过滤
                if annotation_type:
                    ann_id_lower = annotation.annotation_id.lower()
                    if annotation_type == "note" and not ann_id_lower.startswith("注"):
                        continue
                    if annotation_type == "plan" and not ann_id_lower.startswith("方案"):
                        continue

                # 内容匹配
                if pattern and pattern.lower() not in annotation.content.lower():
                    continue

                results.append({
                    "annotation_id": annotation.annotation_id,
                    "content": annotation.content[:200] + ("..." if len(annotation.content) > 200 else ""),
                    "page_num": page_num,
                    "source": f"{reg_id} P{page_num} {annotation.annotation_id}",
                })

        return results

    def get_table_by_id(
        self,
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """
        获取完整表格内容（按表格ID）

        优先使用表格注册表（O(1) 查找），如果注册表不存在则降级为遍历页面。
        对于跨页表格，会自动返回合并后的完整内容。

        Args:
            reg_id: 规程标识
            table_id: 表格标识（可以是主表格 ID 或段落 ID）
            include_merged: 如果表格跨页，是否自动合并（默认True）

        Returns:
            表格完整信息，包含:
            - table_id: 表格标识
            - caption: 表格标题
            - page_num: 起始页码
            - page_range: [起始页, 结束页]（如跨页）
            - is_cross_page: 是否为跨页表格
            - row_count: 行数
            - col_count: 列数
            - col_headers: 列标题
            - markdown: 表格Markdown格式
            - chapter_path: 所属章节路径
            - segments: 表格段落信息（如跨页）
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
            TableNotFoundError: 表格不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 优先使用表格注册表（O(1) 查找）
        table_entry = self.page_store.get_table_by_id(reg_id, table_id)

        if table_entry:
            # 从 TableEntry 构建返回结果
            start_page = table_entry.page_start
            end_page = table_entry.page_end

            # 构建来源
            if start_page == end_page:
                source = f"{reg_id} P{start_page}"
            else:
                source = f"{reg_id} P{start_page}-{end_page}"
            if table_entry.caption:
                source += f" {table_entry.caption}"

            # 构建段落信息
            segments = [
                {
                    "segment_id": seg.segment_id,
                    "page_num": seg.page_num,
                    "is_header": seg.is_header,
                    "row_range": [seg.row_start, seg.row_end],
                }
                for seg in table_entry.segments
            ]

            return {
                "table_id": table_entry.table_id,
                "caption": table_entry.caption,
                "page_num": start_page,
                "page_range": [start_page, end_page],
                "is_cross_page": table_entry.is_cross_page,
                "row_count": table_entry.row_count,
                "col_count": table_entry.col_count,
                "col_headers": table_entry.col_headers,
                "markdown": table_entry.merged_markdown,
                "chapter_path": table_entry.chapter_path,
                "segments": segments,
                "source": source,
            }

        # 降级：遍历所有页面查找（向后兼容）
        return self._get_table_by_id_legacy(reg_id, table_id, include_merged)

    def _get_table_by_id_legacy(
        self,
        reg_id: str,
        table_id: str,
        include_merged: bool = True,
    ) -> dict:
        """
        遍历页面查找表格（向后兼容）

        当表格注册表不存在时使用此方法。

        Args:
            reg_id: 规程标识
            table_id: 表格标识
            include_merged: 如果表格跨页，是否自动合并

        Returns:
            表格完整信息

        Raises:
            TableNotFoundError: 表格不存在
        """
        info = self.page_store.load_info(reg_id)

        # 查找表格
        for page_num in range(1, info.total_pages + 1):
            page = self.page_store.load_page(reg_id, page_num)

            for block in page.content_blocks:
                if block.block_type != "table" or not block.table_meta:
                    continue

                if block.table_meta.table_id == table_id:
                    table_meta = block.table_meta
                    start_page = page_num
                    end_page = page_num

                    # 如果表格跨页且需要合并
                    markdown_content = block.content_markdown
                    if include_merged and table_meta.is_truncated:
                        # 读取后续页面合并表格
                        page_content = self.page_store.load_page_range(
                            reg_id, start_page, min(start_page + 5, info.total_pages)
                        )
                        markdown_content = page_content.content_markdown
                        end_page = page_content.end_page

                    # 获取页面注释
                    annotations = [
                        {
                            "annotation_id": ann.annotation_id,
                            "content": ann.content,
                        }
                        for ann in page.annotations
                    ]

                    # 构建来源
                    if start_page == end_page:
                        source = f"{reg_id} P{start_page}"
                    else:
                        source = f"{reg_id} P{start_page}-{end_page}"
                    if table_meta.caption:
                        source += f" {table_meta.caption}"

                    return {
                        "table_id": table_meta.table_id,
                        "caption": table_meta.caption,
                        "page_num": start_page,
                        "page_range": [start_page, end_page],
                        "is_cross_page": start_page != end_page,
                        "row_count": table_meta.row_count,
                        "col_count": table_meta.col_count,
                        "col_headers": table_meta.col_headers,
                        "row_headers": table_meta.row_headers,
                        "cells": [
                            {
                                "row": cell.row,
                                "col": cell.col,
                                "content": cell.content,
                                "row_span": cell.row_span,
                                "col_span": cell.col_span,
                            }
                            for cell in table_meta.cells
                        ],
                        "markdown": markdown_content,
                        "chapter_path": block.chapter_path,
                        "annotations": annotations,
                        "source": source,
                    }

        raise TableNotFoundError(reg_id, table_id)

    def get_block_with_context(
        self,
        reg_id: str,
        block_id: str,
        context_blocks: int = 2,
    ) -> dict:
        """
        读取指定内容块及其上下文

        Args:
            reg_id: 规程标识
            block_id: 内容块标识（从搜索结果获取）
            context_blocks: 上下文块数量（前后各N个块），默认2

        Returns:
            内容块及上下文，包含:
            - target_block: 目标块完整信息
            - page_num: 所在页码
            - before_blocks: 前序块列表
            - after_blocks: 后续块列表
            - page_annotations: 页面注释列表
            - active_chapters: 活跃章节信息
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        info = self.page_store.load_info(reg_id)

        # 查找目标块
        for page_num in range(1, info.total_pages + 1):
            page = self.page_store.load_page(reg_id, page_num)

            for idx, block in enumerate(page.content_blocks):
                if block.block_id == block_id:
                    # 找到目标块
                    before_blocks = []
                    after_blocks = []

                    # 获取前序块
                    for i in range(max(0, idx - context_blocks), idx):
                        b = page.content_blocks[i]
                        before_blocks.append({
                            "block_id": b.block_id,
                            "block_type": b.block_type,
                            "content_markdown": b.content_markdown,
                        })

                    # 获取后续块
                    for i in range(idx + 1, min(len(page.content_blocks), idx + context_blocks + 1)):
                        b = page.content_blocks[i]
                        after_blocks.append({
                            "block_id": b.block_id,
                            "block_type": b.block_type,
                            "content_markdown": b.content_markdown,
                        })

                    # 如果上下文不足，尝试从相邻页面获取
                    if len(before_blocks) < context_blocks and page_num > 1:
                        prev_page = self.page_store.load_page(reg_id, page_num - 1)
                        needed = context_blocks - len(before_blocks)
                        for b in prev_page.content_blocks[-needed:]:
                            before_blocks.insert(0, {
                                "block_id": b.block_id,
                                "block_type": b.block_type,
                                "content_markdown": b.content_markdown,
                                "from_page": page_num - 1,
                            })

                    if len(after_blocks) < context_blocks and page_num < info.total_pages:
                        next_page = self.page_store.load_page(reg_id, page_num + 1)
                        needed = context_blocks - len(after_blocks)
                        for b in next_page.content_blocks[:needed]:
                            after_blocks.append({
                                "block_id": b.block_id,
                                "block_type": b.block_type,
                                "content_markdown": b.content_markdown,
                                "from_page": page_num + 1,
                            })

                    return {
                        "target_block": {
                            "block_id": block.block_id,
                            "block_type": block.block_type,
                            "content_markdown": block.content_markdown,
                            "chapter_path": block.chapter_path,
                            "table_meta": block.table_meta.model_dump() if block.table_meta else None,
                        },
                        "page_num": page_num,
                        "before_blocks": before_blocks,
                        "after_blocks": after_blocks,
                        "page_annotations": [
                            {
                                "annotation_id": ann.annotation_id,
                                "content": ann.content,
                            }
                            for ann in page.annotations
                        ],
                        "active_chapters": [
                            {
                                "section_number": ch.section_number,
                                "title": ch.title,
                                "level": ch.level,
                                "inherited": ch.inherited,
                            }
                            for ch in page.active_chapters
                        ],
                        "source": f"{reg_id} P{page_num}",
                    }

        return {"error": f"未找到内容块 '{block_id}'"}

    # ==================== Phase 3: 发现工具 ====================

    def find_similar_content(
        self,
        reg_id: str,
        query_text: str | None = None,
        source_block_id: str | None = None,
        limit: int = 5,
        exclude_same_page: bool = True,
    ) -> list[dict]:
        """
        查找语义相似的内容

        可以基于文本查询或已有内容块查找相似内容。

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

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 确定查询文本
        search_query = query_text
        source_page = None

        if source_block_id and not query_text:
            # 从块ID获取内容
            info = self.page_store.load_info(reg_id)
            for page_num in range(1, info.total_pages + 1):
                page = self.page_store.load_page(reg_id, page_num)
                for block in page.content_blocks:
                    if block.block_id == source_block_id:
                        search_query = block.content_markdown[:500]  # 截取前500字符作为查询
                        source_page = page_num
                        break
                if search_query:
                    break

        if not search_query:
            return [{"error": "必须提供 query_text 或有效的 source_block_id"}]

        # 使用混合搜索查找相似内容
        # 增加 limit 以便过滤后仍有足够结果
        search_limit = limit * 3 if exclude_same_page else limit
        results = self.hybrid_search.search(
            query=search_query,
            reg_id=reg_id,
            limit=search_limit,
        )

        similar_results = []
        for r in results:
            # 排除同页内容
            if exclude_same_page and source_page and r.page_num == source_page:
                continue

            # 排除源块本身
            if source_block_id and r.block_id == source_block_id:
                continue

            similar_results.append({
                "block_id": r.block_id,
                "page_num": r.page_num,
                "chapter_path": r.chapter_path,
                "snippet": r.snippet,
                "similarity_score": round(r.score, 4),
                "source": r.source,
            })

            if len(similar_results) >= limit:
                break

        return similar_results

    def compare_sections(
        self,
        reg_id: str,
        section_a: str,
        section_b: str,
        include_tables: bool = True,
    ) -> dict:
        """
        比较两个章节的内容

        Args:
            reg_id: 规程标识
            section_a: 第一个章节编号，如 "2.1.4"
            section_b: 第二个章节编号，如 "2.1.5"
            include_tables: 是否包含表格内容，默认True

        Returns:
            比较结果，包含:
            - section_a_info: 第一个章节的信息
            - section_b_info: 第二个章节的信息
            - common_keywords: 共同关键词
            - structural_comparison: 结构比较
            - source: 来源引用

        Raises:
            RegulationNotFoundError: 规程不存在
            ChapterNotFoundError: 章节不存在
        """
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        # 获取两个章节的内容
        content_a = self.read_chapter_content(reg_id, section_a, include_children=True)
        content_b = self.read_chapter_content(reg_id, section_b, include_children=True)

        # 如果有错误，直接返回
        if "error" in content_a:
            raise ChapterNotFoundError(reg_id, section_a)
        if "error" in content_b:
            raise ChapterNotFoundError(reg_id, section_b)

        # 统计表格数量
        tables_a = self._count_tables_in_content(content_a.get("content_markdown", ""))
        tables_b = self._count_tables_in_content(content_b.get("content_markdown", ""))

        # 统计列表数量
        lists_a = self._count_lists_in_content(content_a.get("content_markdown", ""))
        lists_b = self._count_lists_in_content(content_b.get("content_markdown", ""))

        # 提取关键词
        keywords_a = self._extract_keywords(content_a.get("content_markdown", ""))
        keywords_b = self._extract_keywords(content_b.get("content_markdown", ""))
        common_keywords = list(set(keywords_a) & set(keywords_b))

        return {
            "section_a_info": {
                "section_number": section_a,
                "title": content_a.get("title", ""),
                "full_path": content_a.get("full_path", []),
                "page_range": content_a.get("page_range", []),
                "block_count": content_a.get("block_count", 0),
                "children_count": len(content_a.get("children", [])),
                "table_count": tables_a,
                "list_count": lists_a,
                "content_preview": content_a.get("content_markdown", "")[:500],
            },
            "section_b_info": {
                "section_number": section_b,
                "title": content_b.get("title", ""),
                "full_path": content_b.get("full_path", []),
                "page_range": content_b.get("page_range", []),
                "block_count": content_b.get("block_count", 0),
                "children_count": len(content_b.get("children", [])),
                "table_count": tables_b,
                "list_count": lists_b,
                "content_preview": content_b.get("content_markdown", "")[:500],
            },
            "common_keywords": common_keywords[:20],  # 最多返回20个共同关键词
            "structural_comparison": {
                "block_diff": content_a.get("block_count", 0) - content_b.get("block_count", 0),
                "children_diff": len(content_a.get("children", [])) - len(content_b.get("children", [])),
                "table_diff": tables_a - tables_b,
                "list_diff": lists_a - lists_b,
            },
            "source": f"{reg_id} {section_a} vs {section_b}",
        }

    def _count_tables_in_content(self, content: str) -> int:
        """统计内容中的表格数量"""
        # 简单统计 Markdown 表格（以 | 开头的行）
        lines = content.split("\n")
        table_lines = [l for l in lines if l.strip().startswith("|")]
        # 估算表格数量（连续的表格行算一个表格）
        table_count = 0
        in_table = False
        for line in lines:
            if line.strip().startswith("|"):
                if not in_table:
                    table_count += 1
                    in_table = True
            else:
                in_table = False
        return table_count

    def _count_lists_in_content(self, content: str) -> int:
        """统计内容中的列表数量"""
        # 统计以数字或破折号开头的行
        lines = content.split("\n")
        list_count = 0
        for line in lines:
            stripped = line.strip()
            if stripped and (stripped[0].isdigit() or stripped.startswith("-") or stripped.startswith("•")):
                list_count += 1
        return list_count

    def _extract_keywords(self, content: str, min_length: int = 2) -> list[str]:
        """从内容中提取关键词"""
        # 简单的关键词提取：提取中文词组
        import re
        # 匹配中文词组（2-6个字符）
        pattern = r"[\u4e00-\u9fa5]{" + str(min_length) + r",6}"
        keywords = re.findall(pattern, content)
        # 去重并统计频率
        from collections import Counter
        keyword_counts = Counter(keywords)
        # 返回出现次数最多的关键词
        return [kw for kw, _ in keyword_counts.most_common(30)]
