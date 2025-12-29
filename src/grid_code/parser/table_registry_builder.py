"""表格注册表构建器

负责从页面文档中构建全局表格注册表，支持跨页表格的检测和合并。
"""

from datetime import datetime

from loguru import logger

from grid_code.storage.models import (
    PageDocument,
    TableEntry,
    TableRegistry,
    TableSegment,
)


class TableRegistryBuilder:
    """表格注册表构建器

    从 PageDocument 列表构建 TableRegistry，自动检测并合并跨页表格。
    """

    def __init__(self, reg_id: str):
        """初始化构建器

        Args:
            reg_id: 规程标识
        """
        self.reg_id = reg_id

    def build(self, pages: list[PageDocument]) -> TableRegistry:
        """构建表格注册表

        Args:
            pages: PageDocument 列表（按页码排序）

        Returns:
            TableRegistry 实例
        """
        if not pages:
            return TableRegistry(reg_id=self.reg_id)

        # 确保页面按页码排序
        sorted_pages = sorted(pages, key=lambda p: p.page_num)

        # 收集所有表格块
        table_groups = self._group_cross_page_tables(sorted_pages)

        # 构建注册表
        tables: dict[str, TableEntry] = {}
        segment_to_table: dict[str, str] = {}
        page_to_tables: dict[int, list[str]] = {}
        cross_page_count = 0

        for group in table_groups:
            entry = self._build_table_entry(group)
            tables[entry.table_id] = entry

            if entry.is_cross_page:
                cross_page_count += 1

            # 建立段落到表格的映射
            for segment in entry.segments:
                segment_to_table[segment.segment_id] = entry.table_id

                # 建立页码到表格的映射
                page_num = segment.page_num
                if page_num not in page_to_tables:
                    page_to_tables[page_num] = []
                if entry.table_id not in page_to_tables[page_num]:
                    page_to_tables[page_num].append(entry.table_id)

        registry = TableRegistry(
            reg_id=self.reg_id,
            total_tables=len(tables),
            cross_page_tables=cross_page_count,
            tables=tables,
            segment_to_table=segment_to_table,
            page_to_tables=page_to_tables,
        )

        logger.info(
            f"表格注册表构建完成: {len(tables)} 个表格, 其中 {cross_page_count} 个跨页表格"
        )

        return registry

    def _group_cross_page_tables(
        self, pages: list[PageDocument]
    ) -> list[list[tuple[PageDocument, int]]]:
        """分组跨页表格

        Args:
            pages: 按页码排序的页面列表

        Returns:
            表格分组列表，每组包含 (page, block_index) 元组
        """
        groups: list[list[tuple[PageDocument, int]]] = []
        current_group: list[tuple[PageDocument, int]] = []
        prev_last_table_info: tuple[int, int] | None = None  # (block_index, col_count)

        for page in pages:
            # 检查当前页第一个块是否是延续的表格
            first_table_idx = None
            first_table_cols = 0

            for idx, block in enumerate(page.content_blocks):
                if block.block_type == "table" and block.table_meta:
                    first_table_idx = idx
                    first_table_cols = block.table_meta.col_count
                    break
                elif block.block_type not in ("heading",):
                    # 第一个非标题内容不是表格
                    break

            # 判断是否应该与前页表格合并
            should_merge = False
            if (
                prev_last_table_info is not None
                and first_table_idx is not None
                and first_table_idx == 0  # 表格是页面第一个块
            ):
                prev_cols = prev_last_table_info[1]
                # 列数相同则认为是跨页表格
                if prev_cols == first_table_cols:
                    # 额外检查：下页表格是否有标题（有标题通常是新表格）
                    first_block = page.content_blocks[first_table_idx]
                    if first_block.table_meta and not first_block.table_meta.caption:
                        should_merge = True

            if should_merge and current_group:
                # 将当前页第一个表格加入当前组
                current_group.append((page, first_table_idx))
            else:
                # 结束当前组（如果有）
                if current_group:
                    groups.append(current_group)
                    current_group = []

            # 处理当前页的所有表格
            for idx, block in enumerate(page.content_blocks):
                if block.block_type == "table" and block.table_meta:
                    # 跳过已经加入当前组的第一个表格
                    if should_merge and idx == first_table_idx:
                        continue

                    # 新表格开始新的组
                    if current_group:
                        groups.append(current_group)
                    current_group = [(page, idx)]

            # 记录当前页最后一个表格的信息
            prev_last_table_info = None
            for idx in range(len(page.content_blocks) - 1, -1, -1):
                block = page.content_blocks[idx]
                if block.block_type == "table" and block.table_meta:
                    prev_last_table_info = (idx, block.table_meta.col_count)
                    break

        # 添加最后一组
        if current_group:
            groups.append(current_group)

        return groups

    def _build_table_entry(
        self, group: list[tuple[PageDocument, int]]
    ) -> TableEntry:
        """从表格组构建 TableEntry

        Args:
            group: (page, block_index) 元组列表

        Returns:
            TableEntry 实例
        """
        if not group:
            raise ValueError("表格组不能为空")

        # 使用第一个表格的 ID 作为主 ID
        first_page, first_idx = group[0]
        first_block = first_page.content_blocks[first_idx]
        first_meta = first_block.table_meta

        table_id = first_meta.table_id if first_meta else first_block.block_id
        caption = first_meta.caption if first_meta else None
        chapter_path = first_block.chapter_path.copy()

        # 收集所有段落
        segments: list[TableSegment] = []
        all_markdown_lines: list[str] = []
        total_rows = 0
        col_count = first_meta.col_count if first_meta else 0
        col_headers = first_meta.col_headers.copy() if first_meta else []

        for i, (page, idx) in enumerate(group):
            block = page.content_blocks[idx]
            meta = block.table_meta

            segment_id = meta.table_id if meta else block.block_id
            is_header = i == 0  # 只有第一个段落包含表头

            # 解析 Markdown 获取行数
            table_lines = [
                line
                for line in block.content_markdown.split("\n")
                if line.strip().startswith("|")
            ]

            if i == 0:
                # 第一个表格：保留表头
                all_markdown_lines.extend(table_lines)
                # 行数 = 总行数 - 表头行 - 分隔行
                data_row_count = max(0, len(table_lines) - 2)
            else:
                # 后续表格：跳过表头（前两行）
                data_lines = table_lines[2:] if len(table_lines) > 2 else []
                all_markdown_lines.extend(data_lines)
                data_row_count = len(data_lines)

            row_start = total_rows
            total_rows += data_row_count
            row_end = total_rows

            segments.append(
                TableSegment(
                    segment_id=segment_id,
                    page_num=page.page_num,
                    block_id=block.block_id,
                    is_header=is_header,
                    row_start=row_start,
                    row_end=row_end,
                )
            )

        # 确定页面范围
        page_start = group[0][0].page_num
        page_end = group[-1][0].page_num
        is_cross_page = page_start != page_end

        return TableEntry(
            table_id=table_id,
            caption=caption,
            chapter_path=chapter_path,
            page_start=page_start,
            page_end=page_end,
            is_cross_page=is_cross_page,
            segments=segments,
            row_count=total_rows,
            col_count=col_count,
            col_headers=col_headers,
            merged_markdown="\n".join(all_markdown_lines),
            created_at=datetime.now().isoformat(),
        )

    @staticmethod
    def get_table_col_count(table_md: str) -> int:
        """从表格 Markdown 获取列数

        Args:
            table_md: 表格 Markdown 内容

        Returns:
            列数
        """
        lines = [line for line in table_md.split("\n") if line.strip().startswith("|")]
        if lines:
            return lines[0].count("|") - 1
        return 0
