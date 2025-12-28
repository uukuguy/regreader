"""页面级数据提取器

从 Docling 解析结果中提取页面级别的结构化数据。
"""

import re
from collections import defaultdict
from typing import Any

from docling.datamodel.document import ConversionResult
from loguru import logger

from grid_code.storage.models import (
    Annotation,
    ContentBlock,
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

    def extract_pages(self, result: ConversionResult) -> list[PageDocument]:
        """
        从 Docling 结果提取所有页面

        Args:
            result: Docling 解析结果

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
            self._process_table_item(item, page_contents)

        # 构建 PageDocument 列表
        pages = []
        sorted_page_nums = sorted(page_contents.keys())

        for i, page_num in enumerate(sorted_page_nums):
            blocks = page_contents[page_num]
            # 按在页面中的顺序排序
            blocks.sort(key=lambda x: x.get("order", 0))

            # 构建内容块
            content_blocks = []
            annotations = []
            for j, block_data in enumerate(blocks):
                if block_data.get("is_annotation"):
                    annotations.append(self._create_annotation(block_data))
                else:
                    content_blocks.append(self._create_content_block(block_data, j))

            # 生成页面 Markdown
            content_markdown = self._generate_page_markdown(content_blocks, annotations)

            # 检测跨页
            continues_from_prev = self._check_continues_from_prev(blocks)
            continues_to_next = self._check_continues_to_next(blocks)

            page = PageDocument(
                reg_id=self.reg_id,
                page_num=page_num,
                chapter_path=self._current_chapter_path.copy(),
                content_blocks=content_blocks,
                content_markdown=content_markdown,
                continues_from_prev=continues_from_prev,
                continues_to_next=continues_to_next,
                annotations=annotations,
            )
            pages.append(page)

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

        # 收集标题信息
        headings: list[dict[str, Any]] = []
        for item in doc.texts:
            if hasattr(item, 'label') and 'heading' in str(item.label).lower():
                page_num = 1
                if item.prov:
                    for prov in item.prov:
                        if hasattr(prov, 'page_no') and prov.page_no:
                            page_num = prov.page_no
                            break

                # 解析标题级别
                level = self._parse_heading_level(item.label, item.text)

                headings.append({
                    "title": item.text.strip(),
                    "level": level,
                    "page_num": page_num,
                })

        # 构建层级目录
        toc_items = self._build_toc_hierarchy(headings)

        # 获取总页数
        total_pages = max((h["page_num"] for h in headings), default=1)

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

        if hasattr(item, 'label'):
            label = str(item.label).lower()
            if 'heading' in label:
                block_type = "heading"
                heading_level = self._parse_heading_level(item.label, item.text)
                # 更新章节路径
                self._update_chapter_path(item.text, heading_level)
            elif 'list' in label:
                block_type = "list"
            elif 'footnote' in label or self._is_annotation_text(item.text):
                is_annotation = True

        page_contents[page_num].append({
            "type": block_type,
            "text": item.text,
            "order": order,
            "heading_level": heading_level,
            "is_annotation": is_annotation,
        })

    def _process_table_item(
        self, item: Any, page_contents: dict[int, list[dict[str, Any]]]
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

        # 生成表格 Markdown - 优先使用 Docling 内置方法
        table_md = ""
        if hasattr(item, 'export_to_markdown'):
            try:
                table_md = item.export_to_markdown()
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

    def _create_content_block(self, block_data: dict[str, Any], order: int) -> ContentBlock:
        """创建 ContentBlock 对象"""
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

        return ContentBlock(
            block_id=self._generate_id(block_type),
            block_type=block_type,
            order_in_page=order,
            content_markdown=text,
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

    def _generate_id(self, prefix: str) -> str:
        """生成唯一 ID"""
        import uuid
        short_uuid = str(uuid.uuid4())[:8]
        return f"{prefix}_{short_uuid}"
