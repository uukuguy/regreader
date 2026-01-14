"""页面级数据提取器

从 Docling 解析结果中提取页面级别的结构化数据。
"""

import re
from collections import defaultdict
from typing import Any

from docling.datamodel.document import ConversionResult
from loguru import logger

from regreader.storage.models import (
    ActiveChapter,
    Annotation,
    ChapterNode,
    ContentBlock,
    DocumentStructure,
    PageDocument,
    TableCell,
    TableMeta,
    TocItem,
    TocTree,
)


class PageExtractor:
    """从 Docling 结果提取页面级数据"""

    def __init__(self, reg_id: str):
        """
        初始化提取器

        Args:
            reg_id: 规程标识（如 'angui_2024'）
        """
        self.reg_id = reg_id
        self._current_chapter_path: list[str] = []
        self._current_chapter_node: ChapterNode | None = None

    def extract_document_structure(self, result: ConversionResult) -> DocumentStructure:
        """
        第一阶段：提取全局章节结构

        遍历文档所有文本项，识别章节标题，构建层级关系。

        Args:
            result: Docling 解析结果

        Returns:
            DocumentStructure 文档结构
        """
        doc = result.document
        all_nodes: dict[str, ChapterNode] = {}
        root_node_ids: list[str] = []
        node_stack: list[tuple[int, str]] = []  # (level, node_id)

        # 跟踪上一个 numeric_single 类型的 level-1 章节编号
        # 用于验证编号是否连续，避免假阳性
        last_numeric_single_level1: int = 0

        for item in doc.texts:
            # 获取页码
            page_num = 1
            if item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no') and prov.page_no:
                        page_num = prov.page_no
                        break

            # 解析章节信息
            is_section, section_info = self._parse_section_info(item.text)
            if not is_section or section_info is None:
                continue

            # 对 numeric_single 类型进行顺序验证
            # 只接受连续递增的编号，避免把章节内的编号列表项误识别为顶级章节
            if section_info.get("pattern_type") == "numeric_single":
                try:
                    current_num = int(section_info["number"])
                    # 验证编号是否连续: 期望是 last + 1
                    # 允许第一个章节是 1，或者是上一个章节 + 1
                    if current_num != last_numeric_single_level1 + 1:
                        # 编号不连续，跳过此项（可能是章节内的编号列表项）
                        logger.debug(
                            f"跳过非连续 numeric_single: {section_info['number']}.{section_info['title'][:20]} "
                            f"(期望 {last_numeric_single_level1 + 1}，页码 {page_num})"
                        )
                        continue
                    # 更新计数器
                    last_numeric_single_level1 = current_num
                except ValueError:
                    # 编号不是纯数字，跳过
                    continue

            # 创建 ChapterNode
            node_id = self._generate_id("chapter")
            node = ChapterNode(
                node_id=node_id,
                section_number=section_info["number"],
                title=section_info["title"],
                level=section_info["level"],
                page_num=page_num,
            )

            # 维护层级关系
            while node_stack and node_stack[-1][0] >= node.level:
                node_stack.pop()

            if node_stack:
                parent_id = node_stack[-1][1]
                node.parent_id = parent_id
                all_nodes[parent_id].children_ids.append(node_id)
            else:
                root_node_ids.append(node_id)

            all_nodes[node_id] = node
            node_stack.append((node.level, node_id))

        logger.info(f"提取章节结构: {len(all_nodes)} 个章节节点, {len(root_node_ids)} 个顶级节点")

        return DocumentStructure(
            reg_id=self.reg_id,
            all_nodes=all_nodes,
            root_node_ids=root_node_ids,
        )

    def _parse_section_info(self, text: str) -> tuple[bool, dict[str, Any] | None]:
        """
        解析章节信息

        Args:
            text: 文本内容

        Returns:
            (is_section, section_info) 元组
            section_info 包含:
                - number: 章节编号 (如 "2.1.4.1.6")
                - title: 章节标题（纯文本，不含编号）
                - level: 章节层级 (1-6)
                - direct_content: 章节号后的直接内容（如有）
                - pattern_type: 匹配的模式类型 (numeric, numeric_single, chapter, section)
        """
        text = text.strip()
        if not text:
            return False, None

        # 章节编号模式
        patterns = [
            # 多级数字编号（有空格）: "2.1.4 标题..." 或 "2.1.4. 标题..."
            # 至少两级数字（如 2.1），避免把 "500 千伏..." 误识别
            (r'^(\d+\.\d+(?:\.\d+)*)\.?\s+(.*)$', 'numeric'),
            # 多级数字编号（无空格）: "2.1.线路" 或 "2.2.1.三峡左岸电厂"
            # 用于 wengui_2024 等编号后直接跟标题的规程
            (r'^(\d+(?:\.\d+)+)\.([^\d\s].*)$', 'numeric'),
            # 单级数字编号: "1.总则" 或 "2.国调直接调度设备范围"
            # 匹配 "数字.非数字开头的标题"，用于 wengui_2024 等规程
            (r'^(\d+)\.([^\d\s].*)$', 'numeric_single'),
            # 中文章: "第一章 总则" 或 "第1章 总则"
            (r'^(第[一二三四五六七八九十百千\d]+章)\s*(.*)$', 'chapter'),
            # 中文节: "第一节 概述"
            (r'^(第[一二三四五六七八九十百千\d]+节)\s*(.*)$', 'section'),
        ]

        for pattern, pattern_type in patterns:
            match = re.match(pattern, text, re.DOTALL)
            if match:
                section_num = match.group(1)
                remaining = match.group(2).strip()

                # 计算层级
                if pattern_type == 'numeric':
                    level = section_num.count('.') + 1
                elif pattern_type == 'numeric_single':
                    # 单级数字编号：如 "1.总则" -> level 1
                    level = 1
                elif pattern_type == 'chapter':
                    level = 1
                elif pattern_type == 'section':
                    level = 2
                else:
                    level = 2

                # 简化逻辑：数字编号章节，后续全部作为标题，不分割
                # 中文章节标题，后续全部作为标题，不分割
                title = remaining
                direct_content = ""

                return True, {
                    "number": section_num,
                    "title": title,
                    "level": level,
                    "direct_content": direct_content,
                    "pattern_type": pattern_type,
                }

        return False, None

    def _find_chapter_node_by_text(
        self,
        doc_structure: DocumentStructure,
        text: str,
        page_num: int
    ) -> ChapterNode | None:
        """根据文本和页码查找对应的章节节点"""
        is_section, section_info = self._parse_section_info(text)
        if not is_section or section_info is None:
            return None

        # 在 DocumentStructure 中查找匹配的节点
        for node in doc_structure.all_nodes.values():
            if (node.section_number == section_info["number"] and
                    node.page_num == page_num):
                return node

        return None

    def _collect_active_chapters(
        self,
        doc_structure: DocumentStructure,
        current_page_nodes: list[ChapterNode],
        prev_page_last_node: ChapterNode | None,
    ) -> list[ActiveChapter]:
        """收集本页所有活跃章节（首次出现 + 延续）

        Args:
            doc_structure: 文档结构
            current_page_nodes: 本页首次出现的章节节点
            prev_page_last_node: 上一页最后一个章节节点

        Returns:
            活跃章节列表（包括首次出现和延续的章节）
        """
        active_chapters = []

        # 1. 收集延续的章节（从上一页的最后章节向上遍历所有祖先）
        inherited_nodes: list[ChapterNode] = []
        if prev_page_last_node:
            current = prev_page_last_node
            while current:
                inherited_nodes.insert(0, current)
                current = doc_structure.all_nodes.get(current.parent_id) if current.parent_id else None

        # 将延续的章节转换为 ActiveChapter（inherited=True）
        for node in inherited_nodes:
            active_chapters.append(ActiveChapter(
                node_id=node.node_id,
                section_number=node.section_number,
                title=node.title,
                level=node.level,
                page_num=node.page_num,
                inherited=True,
            ))

        # 2. 添加本页首次出现的章节（inherited=False）
        for node in current_page_nodes:
            active_chapters.append(ActiveChapter(
                node_id=node.node_id,
                section_number=node.section_number,
                title=node.title,
                level=node.level,
                page_num=node.page_num,
                inherited=False,
            ))

        return active_chapters

    def extract_pages(
        self,
        result: ConversionResult,
        doc_structure: DocumentStructure | None = None
    ) -> list[PageDocument]:
        """
        第二阶段：提取页面内容并关联章节结构

        Args:
            result: Docling 解析结果
            doc_structure: 文档结构（可选，如提供则为每个块添加章节关联）

        Returns:
            PageDocument 列表
        """
        doc = result.document

        # 按页码分组内容
        page_contents: dict[int, list[dict[str, Any]]] = defaultdict(list)

        # 处理文本内容
        for item in doc.texts:
            self._process_text_item(item, page_contents)

        # 处理表格
        for item in doc.tables:
            self._process_table_item(item, page_contents, doc)

        # 构建 PageDocument 列表
        pages = []
        sorted_page_nums = sorted(page_contents.keys())

        # 追踪上一页的最后章节节点（用于收集延续章节）
        prev_page_last_node: ChapterNode | None = None

        for i, page_num in enumerate(sorted_page_nums):
            blocks = page_contents[page_num]
            # 按在页面中的顺序排序
            blocks.sort(key=lambda x: x.get("order", 0))

            # 本页首次出现的章节节点列表
            page_chapter_nodes: list[ChapterNode] = []

            # 第一遍：收集本页所有章节节点（但不更新 _current_chapter_node）
            if doc_structure:
                for block_data in blocks:
                    if block_data.get("type") == "heading" and block_data.get("heading_level"):
                        node = self._find_chapter_node_by_text(
                            doc_structure, block_data["text"], page_num
                        )
                        if node and node not in page_chapter_nodes:
                            page_chapter_nodes.append(node)

            # 收集活跃章节（首次出现 + 延续）
            active_chapters: list[ActiveChapter] = []
            if doc_structure:
                active_chapters = self._collect_active_chapters(
                    doc_structure=doc_structure,
                    current_page_nodes=page_chapter_nodes,
                    prev_page_last_node=prev_page_last_node,
                )

            # 构建内容块（在此过程中更新章节状态）
            content_blocks = []
            annotations = []
            for j, block_data in enumerate(blocks):
                if block_data.get("is_annotation"):
                    annotations.append(self._create_annotation(block_data))
                    continue

                # 如果是标题，先更新章节状态
                if block_data.get("type") == "heading" and block_data.get("heading_level"):
                    self._update_chapter_path(block_data["text"], block_data["heading_level"])
                    if doc_structure:
                        node = self._find_chapter_node_by_text(
                            doc_structure, block_data["text"], page_num
                        )
                        if node:
                            self._current_chapter_node = node

                # 创建内容块
                block = self._create_content_block(block_data, j, doc_structure)
                content_blocks.append(block)

            # 过滤页尾的孤立页码数字
            if content_blocks:
                last_block = content_blocks[-1]
                if last_block.block_type == "text":
                    content_stripped = last_block.content_markdown.strip()
                    # 检查是否为纯 1-3 位数字
                    if re.match(r'^\d{1,3}$', content_stripped):
                        logger.debug(f"过滤页尾页码: page {page_num}, content '{content_stripped}'")
                        content_blocks.pop()

            # 生成页面 Markdown
            content_markdown = self._generate_page_markdown(content_blocks, annotations)

            # 检测跨页
            continues_from_prev = self._check_continues_from_prev(blocks)
            continues_to_next = self._check_continues_to_next(blocks)

            # 创建 PageDocument
            page = PageDocument(
                reg_id=self.reg_id,
                page_num=page_num,
                active_chapters=active_chapters,
                content_blocks=content_blocks,
                content_markdown=content_markdown,
                continues_from_prev=continues_from_prev,
                continues_to_next=continues_to_next,
                annotations=annotations,
            )
            pages.append(page)

            # 更新上一页的最后章节节点
            if page_chapter_nodes:
                prev_page_last_node = page_chapter_nodes[-1]

        logger.info(f"提取完成: {len(pages)} 页")
        return pages

    def extract_toc(self, result: ConversionResult) -> TocTree:
        """
        从 Docling 结果提取目录

        Args:
            result: Docling 解析结果

        Returns:
            TocTree 目录树
        """
        doc = result.document
        doc_title = getattr(doc, 'title', None) or self.reg_id

        # 获取文档总页数
        total_pages = 1
        all_page_nums = set()
        for item in doc.texts:
            if item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no') and prov.page_no:
                        all_page_nums.add(prov.page_no)
        if all_page_nums:
            total_pages = max(all_page_nums)

        # 收集标题信息（同时使用 Docling 标签和智能检测）
        headings: list[dict[str, Any]] = []
        for item in doc.texts:
            page_num = 1
            if item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no') and prov.page_no:
                        page_num = prov.page_no
                        break

            # 首先检查 Docling 标签
            is_heading = hasattr(item, 'label') and 'heading' in str(item.label).lower()
            level = None

            if is_heading:
                # Docling 识别为标题
                level = self._parse_heading_level(item.label, item.text)
            else:
                # 使用智能检测
                level = self._detect_heading_from_text(item.text)

            if level is not None:
                # 截取标题文字（最多100字符用于显示）
                title_text = item.text.strip()
                if len(title_text) > 100:
                    title_text = title_text[:100] + "..."

                headings.append({
                    "title": title_text,
                    "level": level,
                    "page_num": page_num,
                })

        # 构建层级目录
        toc_items = self._build_toc_hierarchy(headings)

        return TocTree(
            reg_id=self.reg_id,
            title=doc_title,
            total_pages=total_pages,
            items=toc_items,
        )

    def _process_text_item(
        self, item: Any, page_contents: dict[int, list[dict[str, Any]]]
    ):
        """处理文本项"""
        page_num = 1
        order = 0

        if item.prov:
            for prov in item.prov:
                if hasattr(prov, 'page_no') and prov.page_no:
                    page_num = prov.page_no
                if hasattr(prov, 'bbox') and prov.bbox:
                    # 使用 y 坐标作为排序依据
                    order = -prov.bbox.t if hasattr(prov.bbox, 't') else 0

        # 判断内容类型
        block_type = "text"
        heading_level = None
        is_annotation = False

        # 首先检查 Docling 标签
        if hasattr(item, 'label'):
            label = str(item.label).lower()
            if 'heading' in label:
                block_type = "heading"
                heading_level = self._parse_heading_level(item.label, item.text)
            elif 'list' in label:
                block_type = "list"
            elif 'footnote' in label or self._is_annotation_text(item.text):
                is_annotation = True

        # 智能标题检测：如果智能检测认为是标题，覆盖 Docling 的判断
        # 这样可以处理 Docling 误判的情况（如把章节标题标记为 list）
        if not is_annotation:
            detected_level = self._detect_heading_from_text(item.text)
            if detected_level is not None:
                block_type = "heading"
                heading_level = detected_level

        page_contents[page_num].append({
            "type": block_type,
            "text": item.text,
            "order": order,
            "heading_level": heading_level,
            "is_annotation": is_annotation,
        })

    def _is_toc_table(self, table_data: dict[str, Any], page_num: int) -> bool:
        """检测是否为目录表格

        检测规则：
        1. 表格内容包含大量纯数字页码（如 "4", "5", "12"...）
        2. 表格包含省略号（.......）
        3. 表格标题包含"目录"、"索引"等关键词
        4. 仅在文档前 10 页应用此检测

        Args:
            table_data: 表格数据
            page_num: 页码

        Returns:
            是否为目录表格
        """
        # 仅检测前 10 页
        if page_num > 10:
            return False

        cells = table_data.get("cells", [])
        if not cells:
            return False

        # 规则 1: 检查表格标题是否包含目录关键词
        caption = table_data.get("caption") or ""
        toc_keywords = ["目录", "索引", "目 录", "索 引", "contents", "index"]
        if any(keyword in caption.lower() for keyword in toc_keywords):
            logger.debug(f"检测到目录表格（标题关键词）: {caption}")
            return True

        # 规则 2: 检查是否包含大量省略号
        ellipsis_count = 0
        for cell in cells:
            if "..." in cell.content or "……" in cell.content or "...." in cell.content:
                ellipsis_count += 1
        if ellipsis_count >= len(cells) * 0.3:  # 30% 以上单元格包含省略号
            logger.debug(f"检测到目录表格（省略号）: page {page_num}")
            return True

        # 规则 3: 检查是否包含大量纯数字页码
        # 统计纯数字单元格（1-3 位数字，可能带括号）
        page_number_count = 0
        for cell in cells:
            content = cell.content.strip()
            # 匹配纯数字或带括号的数字（如 "1", "12", "(1)", "（1）"）
            if re.match(r'^[（(]?\d{1,3}[)）]?$', content):
                page_number_count += 1

        # 如果超过 20% 的单元格是页码，认为是目录表格
        if page_number_count >= max(3, len(cells) * 0.2):
            logger.debug(f"检测到目录表格（页码）: page {page_num}, 页码单元格 {page_number_count}/{len(cells)}")
            return True

        return False

    def _process_table_item(
        self, item: Any, page_contents: dict[int, list[dict[str, Any]]], doc: Any = None
    ):
        """处理表格项"""
        page_num = 1
        order = 0
        is_truncated = False

        if item.prov:
            pages_in_table = []
            for prov in item.prov:
                if hasattr(prov, 'page_no') and prov.page_no:
                    pages_in_table.append(prov.page_no)
                if hasattr(prov, 'bbox') and prov.bbox:
                    order = -prov.bbox.t if hasattr(prov.bbox, 't') else 0

            if pages_in_table:
                page_num = min(pages_in_table)
                is_truncated = len(set(pages_in_table)) > 1

        # 提取表格数据
        table_data = self._extract_table_data(item)

        # 检测是否为目录表格，如果是则跳过
        if self._is_toc_table(table_data, page_num):
            logger.info(f"跳过目录表格: page {page_num}")
            return

        # 生成表格 Markdown - 优先使用 Docling 内置方法
        table_md = ""
        if hasattr(item, 'export_to_markdown'):
            try:
                table_md = item.export_to_markdown(doc=doc) if doc else item.export_to_markdown()
            except Exception:
                table_md = self._table_to_markdown(table_data)
        else:
            table_md = self._table_to_markdown(table_data)

        page_contents[page_num].append({
            "type": "table",
            "text": table_md,
            "order": order,
            "table_data": table_data,
            "is_truncated": is_truncated,
            "is_annotation": False,
        })

    def _extract_table_data(self, item: Any) -> dict[str, Any]:
        """提取表格结构化数据

        根据 Docling TableCell 的正确属性名称：
        - start_row_offset_idx / end_row_offset_idx: 行位置
        - start_col_offset_idx / end_col_offset_idx: 列位置
        - text: 单元格文本
        - row_span / col_span: 跨行/跨列
        - row_header / column_header: 是否为标题单元格
        """
        cells = []
        row_headers = []
        col_headers = []
        max_row = 0
        max_col = 0

        # 尝试从 Docling 表格对象提取数据
        if hasattr(item, 'data') and item.data:
            data = item.data

            # 优先使用 num_rows 和 num_cols 属性
            if hasattr(data, 'num_rows'):
                max_row = data.num_rows
            if hasattr(data, 'num_cols'):
                max_col = data.num_cols

            if hasattr(data, 'table_cells'):
                for cell in data.table_cells:
                    # 使用正确的 Docling TableCell 属性名称
                    row = getattr(cell, 'start_row_offset_idx', 0)
                    col = getattr(cell, 'start_col_offset_idx', 0)
                    content = getattr(cell, 'text', '')
                    row_span = getattr(cell, 'row_span', 1)
                    col_span = getattr(cell, 'col_span', 1)
                    is_row_header = getattr(cell, 'row_header', False)
                    is_col_header = getattr(cell, 'column_header', False)

                    cells.append(TableCell(
                        row=row,
                        col=col,
                        content=content,
                        row_span=row_span,
                        col_span=col_span,
                    ))

                    # 如果没有从 data 获取到尺寸，从单元格计算
                    if max_row == 0:
                        max_row = max(max_row, row + row_span)
                    if max_col == 0:
                        max_col = max(max_col, col + col_span)

                    # 检测标题行/列
                    if is_col_header or row == 0:
                        col_headers.append(content)
                    if is_row_header or (col == 0 and row > 0):
                        row_headers.append(content)

        # 获取表格标题
        caption = None
        if hasattr(item, 'captions') and item.captions:
            # captions 是一个列表
            caption_texts = []
            for cap in item.captions:
                if hasattr(cap, 'text'):
                    caption_texts.append(cap.text)
            if caption_texts:
                caption = " ".join(caption_texts)
        elif hasattr(item, 'caption') and item.caption:
            caption = item.caption

        return {
            "table_id": self._generate_id("table"),
            "caption": caption,
            "cells": cells,
            "row_count": max_row,
            "col_count": max_col,
            "row_headers": row_headers,
            "col_headers": col_headers,
        }

    def _table_to_markdown(self, table_data: dict[str, Any]) -> str:
        """将表格数据转换为 Markdown"""
        cells = table_data.get("cells", [])
        if not cells:
            return ""

        row_count = table_data.get("row_count", 0)
        col_count = table_data.get("col_count", 0)

        if row_count == 0 or col_count == 0:
            return ""

        # 构建二维数组
        grid = [["" for _ in range(col_count)] for _ in range(row_count)]
        for cell in cells:
            if cell.row < row_count and cell.col < col_count:
                grid[cell.row][cell.col] = cell.content.replace("\n", " ").strip()

        # 生成 Markdown
        lines = []

        # 标题（如果有）
        caption = table_data.get("caption")
        if caption:
            lines.append(f"**{caption}**\n")

        # 表头
        if row_count > 0:
            lines.append("| " + " | ".join(grid[0]) + " |")
            lines.append("|" + "|".join(["---"] * col_count) + "|")

            # 数据行
            for row in grid[1:]:
                lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _create_content_block(
        self,
        block_data: dict[str, Any],
        order: int,
        doc_structure: DocumentStructure | None = None
    ) -> ContentBlock:
        """创建 ContentBlock 对象

        Args:
            block_data: 块数据
            order: 在页面中的顺序
            doc_structure: 文档结构（可选）

        Returns:
            ContentBlock 对象
        """
        block_type = block_data["type"]
        text = block_data["text"]

        table_meta = None
        if block_type == "table" and "table_data" in block_data:
            td = block_data["table_data"]
            table_meta = TableMeta(
                table_id=td["table_id"],
                caption=td.get("caption"),
                is_truncated=block_data.get("is_truncated", False),
                row_headers=td.get("row_headers", []),
                col_headers=td.get("col_headers", []),
                row_count=td.get("row_count", 0),
                col_count=td.get("col_count", 0),
                cells=td.get("cells", []),
            )

        # 获取块级章节信息
        chapter_path: list[str] = []
        chapter_node_id: str | None = None

        if doc_structure and self._current_chapter_node:
            chapter_path = doc_structure.get_chapter_path(self._current_chapter_node.node_id)
            chapter_node_id = self._current_chapter_node.node_id

        return ContentBlock(
            block_id=self._generate_id(block_type),
            block_type=block_type,
            order_in_page=order,
            content_markdown=text,
            chapter_path=chapter_path,
            chapter_node_id=chapter_node_id,
            table_meta=table_meta,
            heading_level=block_data.get("heading_level"),
        )

    def _create_annotation(self, block_data: dict[str, Any]) -> Annotation:
        """创建注释对象"""
        text = block_data["text"]
        # 尝试提取注释 ID（如 "注1", "注①"）
        match = re.match(r'^(注[0-9①②③④⑤⑥⑦⑧⑨⑩\d]+|方案[甲乙丙丁A-Z])', text)
        annotation_id = match.group(1) if match else self._generate_id("note")

        return Annotation(
            annotation_id=annotation_id,
            content=text,
            related_blocks=[],
        )

    def _generate_page_markdown(
        self, blocks: list[ContentBlock], annotations: list[Annotation]
    ) -> str:
        """生成页面完整 Markdown"""
        parts = []

        for block in blocks:
            if block.block_type == "heading" and block.heading_level:
                prefix = "#" * block.heading_level
                parts.append(f"{prefix} {block.content_markdown}\n")
            else:
                parts.append(block.content_markdown + "\n")

        # 添加注释
        if annotations:
            parts.append("\n---\n")
            for ann in annotations:
                parts.append(f"**{ann.annotation_id}**: {ann.content}\n")

        return "\n".join(parts)

    def _parse_heading_level(self, label: Any, text: str) -> int:
        """解析标题级别"""
        label_str = str(label).lower()

        # 从标签推断
        if 'section_header' in label_str or 'title' in label_str:
            return 1
        if 'heading_1' in label_str:
            return 1
        if 'heading_2' in label_str:
            return 2
        if 'heading_3' in label_str:
            return 3

        # 从文本内容推断
        if re.match(r'^第[一二三四五六七八九十\d]+章', text):
            return 1
        if re.match(r'^第[一二三四五六七八九十\d]+节', text):
            return 2
        if re.match(r'^\d+\.\d+', text):
            return 2
        if re.match(r'^\d+\.\d+\.\d+', text):
            return 3

        return 2  # 默认级别

    def _detect_heading_from_text(self, text: str) -> int | None:
        """从文本内容智能检测是否为标题及其级别

        当 Docling 未识别为标题时，通过文本模式进行检测。

        优先检查明确的章节编号格式（不限制长度），然后再检查其他格式。

        Args:
            text: 文本内容

        Returns:
            标题级别（1-4），如果不是标题则返回 None
        """
        text = text.strip()

        # 空文本不是标题
        if not text:
            return None

        # 0. 一级章节编号格式（如 "1. 总则"、"2. 系统结构"）
        # 匹配: "数字. 中文标题" 或 "数字. 标题"
        # 这种格式通常是文档的一级章节
        level1_pattern = r'^(\d{1,2})\.\s+[\u4e00-\u9fa5].{0,30}$'
        if len(text) <= 100 and re.match(level1_pattern, text):
            return 1

        # 1. 数字编号格式（最可靠，不限制长度）
        # 匹配各种章节编号格式：
        # - "2.1" -> 2级标题
        # - "2.1." -> 2级标题
        # - "2.1.1" -> 3级标题
        # - "2.1.1.1" -> 4级标题
        # 注意：单个数字不带点（如 "500"）不应该被识别为章节号
        number_pattern = r'^(\d+\.\d+(?:\.\d+)*)\.?\s+'
        match = re.match(number_pattern, text)

        if match:
            numbering = match.group(1)
            # 计算点的数量（级别）
            dot_count = numbering.count('.')
            if dot_count == 1:  # "2.1" 或 "2.1. 标题"
                return 2
            elif dot_count == 2:  # "2.1.1" 或 "2.1.1. 标题"
                return 3
            elif dot_count >= 3:  # "2.1.1.1" 或更多层级
                return 4

        # 2. 中文章节标记（限制长度避免误判）
        if len(text) <= 200:
            # "第X章" -> 1级标题
            if re.match(r'^第[一二三四五六七八九十百千\d]+章\s*[\s\u3000]*.{0,50}$', text):
                return 1
            # "第X节" -> 2级标题
            if re.match(r'^第[一二三四五六七八九十百千\d]+节\s*[\s\u3000]*.{0,50}$', text):
                return 2

        # 3. 纯数字编号开头 + 短文本（可能是标题）
        # 如 "1 概述"、"2 系统结构"
        # 限制：数字必须是 1-2 位，且后续文本不超过 30 字符
        if len(text) <= 200 and re.match(r'^\d{1,2}\s+[\u4e00-\u9fa5].{0,30}$', text):
            return 2

        # 4. 带括号的编号（如 "(一)"、"（1）"）
        if len(text) <= 200 and re.match(r'^[（(][一二三四五六七八九十\d]+[)）]\s*.{0,50}$', text):
            return 3

        # 5. 字母编号（如 "A. 标题"、"a) 标题"）
        if len(text) <= 200 and re.match(r'^[A-Za-z][.、)）]\s*.{0,50}$', text):
            return 4

        return None

    def _update_chapter_path(self, heading_text: str, level: int):
        """更新当前章节路径"""
        # 截断到当前级别
        self._current_chapter_path = self._current_chapter_path[:level - 1]
        # 添加当前标题
        self._current_chapter_path.append(heading_text.strip())

    def _is_annotation_text(self, text: str) -> bool:
        """判断是否为注释文本"""
        patterns = [
            r'^注[0-9①②③④⑤⑥⑦⑧⑨⑩\d]+[:：]',
            r'^方案[甲乙丙丁A-Z][:：]',
            r'^\(注',
            r'^（注',
        ]
        return any(re.match(p, text.strip()) for p in patterns)

    def _check_continues_from_prev(self, blocks: list[dict]) -> bool:
        """检查是否从上一页延续"""
        if not blocks:
            return False
        first_block = blocks[0]
        # 如果第一个块是表格且没有标题，可能是从上一页延续
        if first_block["type"] == "table":
            table_data = first_block.get("table_data", {})
            return table_data.get("caption") is None
        return False

    def _check_continues_to_next(self, blocks: list[dict]) -> bool:
        """检查是否延续到下一页"""
        if not blocks:
            return False
        last_block = blocks[-1]
        # 如果最后一个块是被截断的表格
        if last_block["type"] == "table":
            return last_block.get("is_truncated", False)
        return False

    def _build_toc_hierarchy(self, headings: list[dict]) -> list[TocItem]:
        """构建层级目录"""
        if not headings:
            return []

        root_items: list[TocItem] = []
        stack: list[tuple[int, TocItem]] = []  # (level, item)

        for i, h in enumerate(headings):
            # 确定结束页码
            page_end = None
            if i + 1 < len(headings):
                page_end = headings[i + 1]["page_num"] - 1

            item = TocItem(
                title=h["title"],
                level=h["level"],
                page_start=h["page_num"],
                page_end=page_end,
                children=[],
            )

            # 清理栈中级别 >= 当前级别的项
            while stack and stack[-1][0] >= h["level"]:
                stack.pop()

            if not stack:
                root_items.append(item)
            else:
                stack[-1][1].children.append(item)

            stack.append((h["level"], item))

        return root_items

    def build_toc_from_structure(
        self, doc_structure: DocumentStructure, total_pages: int
    ) -> TocTree:
        """
        从 DocumentStructure 构建 TocTree

        这确保 TocTree 与 DocumentStructure 使用相同的章节识别逻辑，
        避免独立解析导致的不一致问题。

        Args:
            doc_structure: 文档结构（从 extract_document_structure 获取）
            total_pages: 文档总页数

        Returns:
            TocTree 目录树
        """

        def build_toc_item(node: ChapterNode, all_nodes: dict[str, ChapterNode]) -> TocItem:
            """递归构建 TocItem"""
            # 计算 page_end: 如果有下一个同级或更高级节点，使用其 page_num - 1
            page_end: int | None = None

            # 构建子节点
            children: list[TocItem] = []
            for child_id in node.children_ids:
                if child_id in all_nodes:
                    child_item = build_toc_item(all_nodes[child_id], all_nodes)
                    children.append(child_item)

            # 格式化标题：包含章节编号
            title = f"{node.section_number} {node.title}" if node.title else node.section_number

            return TocItem(
                title=title,
                level=node.level,
                page_start=node.page_num,
                page_end=page_end,
                children=children,
            )

        # 从根节点构建 TocItem 列表
        root_items: list[TocItem] = []
        for root_id in doc_structure.root_node_ids:
            if root_id in doc_structure.all_nodes:
                root_item = build_toc_item(
                    doc_structure.all_nodes[root_id], doc_structure.all_nodes
                )
                root_items.append(root_item)

        return TocTree(
            reg_id=self.reg_id,
            title=self.reg_id,
            total_pages=total_pages,
            items=root_items,
        )

    def _generate_id(self, prefix: str) -> str:
        """生成唯一 ID"""
        import uuid
        short_uuid = str(uuid.uuid4())[:8]
        return f"{prefix}_{short_uuid}"
