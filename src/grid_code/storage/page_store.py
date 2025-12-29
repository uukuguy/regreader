"""页面存储管理

负责 PageDocument 的持久化存储和读取。
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from grid_code.config import get_settings
from grid_code.exceptions import PageNotFoundError, RegulationNotFoundError, StorageError
from grid_code.storage.models import (
    DocumentStructure,
    PageContent,
    PageDocument,
    RegulationInfo,
    TableEntry,
    TableRegistry,
    TocTree,
)


class PageStore:
    """页面存储管理器"""

    def __init__(self, pages_dir: Path | None = None):
        """
        初始化存储管理器

        Args:
            pages_dir: 页面存储目录，默认使用配置中的路径
        """
        settings = get_settings()
        self.pages_dir = pages_dir or settings.pages_dir
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def _get_reg_dir(self, reg_id: str) -> Path:
        """获取规程存储目录"""
        return self.pages_dir / reg_id

    def _get_page_path(self, reg_id: str, page_num: int) -> Path:
        """获取页面文件路径"""
        return self._get_reg_dir(reg_id) / f"page_{page_num:04d}.json"

    def _get_toc_path(self, reg_id: str) -> Path:
        """获取目录文件路径"""
        return self._get_reg_dir(reg_id) / "toc.json"

    def _get_info_path(self, reg_id: str) -> Path:
        """获取规程信息文件路径"""
        return self._get_reg_dir(reg_id) / "info.json"

    def _get_structure_path(self, reg_id: str) -> Path:
        """获取文档结构文件路径"""
        return self._get_reg_dir(reg_id) / "structure.json"

    def _get_table_registry_path(self, reg_id: str) -> Path:
        """获取表格注册表文件路径"""
        return self._get_reg_dir(reg_id) / "table_registry.json"

    def save_pages(
        self,
        pages: list[PageDocument],
        toc: TocTree | None = None,
        doc_structure: DocumentStructure | None = None,
        source_file: str = "",
    ) -> RegulationInfo:
        """
        保存页面列表

        Args:
            pages: PageDocument 列表
            toc: 目录树（可选）
            doc_structure: 文档结构（可选）
            source_file: 源文件名

        Returns:
            规程信息

        Raises:
            StorageError: 保存失败
        """
        if not pages:
            raise StorageError("页面列表为空")

        reg_id = pages[0].reg_id
        reg_dir = self._get_reg_dir(reg_id)
        reg_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"保存规程 {reg_id}: {len(pages)} 页")

        try:
            # 保存每一页
            for page in pages:
                page_path = self._get_page_path(reg_id, page.page_num)
                with open(page_path, "w", encoding="utf-8") as f:
                    json.dump(page.model_dump(), f, ensure_ascii=False, indent=2)

            # 保存目录
            if toc:
                toc_path = self._get_toc_path(reg_id)
                with open(toc_path, "w", encoding="utf-8") as f:
                    json.dump(toc.model_dump(), f, ensure_ascii=False, indent=2)

            # 保存文档结构
            if doc_structure:
                structure_path = self._get_structure_path(reg_id)
                with open(structure_path, "w", encoding="utf-8") as f:
                    json.dump(doc_structure.model_dump(), f, ensure_ascii=False, indent=2)
                logger.info(f"文档结构已保存: {len(doc_structure.all_nodes)} 个章节节点")

            # 保存规程信息
            info = RegulationInfo(
                reg_id=reg_id,
                title=toc.title if toc else reg_id,
                source_file=source_file,
                total_pages=len(pages),
                indexed_at=datetime.now().isoformat(),
            )
            info_path = self._get_info_path(reg_id)
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info.model_dump(), f, ensure_ascii=False, indent=2)

            logger.info(f"规程 {reg_id} 保存完成")
            return info

        except Exception as e:
            raise StorageError(f"保存规程 {reg_id} 失败: {e}") from e

    def load_page(self, reg_id: str, page_num: int) -> PageDocument:
        """
        加载单页

        Args:
            reg_id: 规程标识
            page_num: 页码

        Returns:
            PageDocument

        Raises:
            RegulationNotFoundError: 规程不存在
            PageNotFoundError: 页面不存在
        """
        reg_dir = self._get_reg_dir(reg_id)
        if not reg_dir.exists():
            raise RegulationNotFoundError(reg_id)

        page_path = self._get_page_path(reg_id, page_num)
        if not page_path.exists():
            raise PageNotFoundError(reg_id, page_num)

        with open(page_path, encoding="utf-8") as f:
            data = json.load(f)
            return PageDocument.model_validate(data)

    def load_page_range(
        self, reg_id: str, start_page: int, end_page: int
    ) -> PageContent:
        """
        加载页面范围（自动处理跨页表格拼接）

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            PageContent（包含合并后的内容）

        Raises:
            RegulationNotFoundError: 规程不存在
            PageNotFoundError: 页面不存在
        """
        pages = []
        for page_num in range(start_page, end_page + 1):
            try:
                page = self.load_page(reg_id, page_num)
                pages.append(page)
            except PageNotFoundError:
                # 跳过不存在的页面
                logger.warning(f"页面 {reg_id} P{page_num} 不存在，跳过")
                continue

        if not pages:
            raise PageNotFoundError(reg_id, start_page)

        # 合并内容
        merged_markdown, has_merged_tables = self._merge_pages(pages)

        return PageContent(
            reg_id=reg_id,
            start_page=start_page,
            end_page=end_page,
            content_markdown=merged_markdown,
            pages=pages,
            has_merged_tables=has_merged_tables,
        )

    def _merge_pages(self, pages: list[PageDocument]) -> tuple[str, bool]:
        """
        合并多页内容，处理跨页表格

        使用显式标记和启发式检测两种方式识别跨页表格：
        1. 显式标记：使用 continues_from_prev/continues_to_next 标记
        2. 启发式：当上页最后是表格、下页第一个也是表格且列数相同时合并

        Returns:
            (合并后的 Markdown, 是否包含合并的表格)
        """
        if not pages:
            return "", False

        parts = []
        has_merged_tables = False
        pending_table: dict | None = None  # {lines: list[str], col_count: int}

        def get_table_col_count(table_md: str) -> int:
            """从表格 Markdown 获取列数"""
            lines = [l for l in table_md.split("\n") if l.strip().startswith("|")]
            if lines:
                # 计算第一行的列数
                return lines[0].count("|") - 1
            return 0

        def should_merge_tables(prev_block, next_block) -> bool:
            """判断两个表格是否应该合并（启发式检测）"""
            if not prev_block or not next_block:
                return False
            if prev_block.block_type != "table" or next_block.block_type != "table":
                return False

            # 比较列数
            prev_cols = get_table_col_count(prev_block.content_markdown)
            next_cols = get_table_col_count(next_block.content_markdown)

            if prev_cols == 0 or next_cols == 0:
                return False

            # 列数相同则认为是跨页表格
            return prev_cols == next_cols

        for i, page in enumerate(pages):
            # 添加页面分隔标记
            parts.append(f"\n<!-- Page {page.page_num} -->\n")

            # 获取下一页信息（用于启发式检测）
            next_page = pages[i + 1] if i + 1 < len(pages) else None
            next_first_block = next_page.content_blocks[0] if next_page and next_page.content_blocks else None

            # 检查是否需要从待处理表格中合并
            if pending_table is not None:
                first_block = page.content_blocks[0] if page.content_blocks else None
                if first_block and first_block.block_type == "table":
                    # 检查列数是否匹配
                    first_cols = get_table_col_count(first_block.content_markdown)
                    if first_cols == pending_table["col_count"]:
                        # 合并表格内容
                        table_lines = first_block.content_markdown.split("\n")
                        # 跳过表头（前两行：标题行和分隔行）
                        data_lines = [
                            line for line in table_lines[2:]
                            if line.strip() and line.startswith("|")
                        ]
                        pending_table["lines"].extend(data_lines)
                        has_merged_tables = True

                        # 输出合并后的表格
                        parts.append("\n".join(pending_table["lines"]))
                        pending_table = None

                        # 添加该页剩余内容
                        for block in page.content_blocks[1:]:
                            parts.append(block.content_markdown)

                        # 检查最后一个块是否可能延续到下页
                        if page.content_blocks:
                            last_block = page.content_blocks[-1]
                            if should_merge_tables(last_block, next_first_block):
                                # 开始新的跨页表格收集
                                pending_table = {
                                    "lines": last_block.content_markdown.split("\n"),
                                    "col_count": get_table_col_count(last_block.content_markdown),
                                }
                                # 移除刚添加的最后一个块（因为要延迟输出）
                                parts.pop()
                        continue
                else:
                    # 下一页第一个不是表格，刷新待处理表格
                    parts.append("\n".join(pending_table["lines"]))
                    pending_table = None

            # 处理当前页内容
            # 检查最后一个块是否可能延续到下页（显式标记或启发式）
            last_block = page.content_blocks[-1] if page.content_blocks else None
            is_explicit_cross_page = (
                page.continues_to_next and
                last_block and
                last_block.block_type == "table" and
                last_block.table_meta and
                last_block.table_meta.is_truncated
            )
            is_heuristic_cross_page = should_merge_tables(last_block, next_first_block)

            if is_explicit_cross_page or is_heuristic_cross_page:
                # 当前页最后的表格可能跨页
                for j, block in enumerate(page.content_blocks):
                    if j == len(page.content_blocks) - 1 and block.block_type == "table":
                        # 最后一个表格，开始收集
                        pending_table = {
                            "lines": block.content_markdown.split("\n"),
                            "col_count": get_table_col_count(block.content_markdown),
                        }
                    else:
                        parts.append(block.content_markdown)
            else:
                # 普通页面，直接添加内容
                parts.append(page.content_markdown)

        # 处理最后的待处理表格
        if pending_table is not None:
            parts.append("\n".join(pending_table["lines"]))

        return "\n".join(parts), has_merged_tables

    def load_toc(self, reg_id: str) -> TocTree:
        """
        加载目录

        Args:
            reg_id: 规程标识

        Returns:
            TocTree

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        toc_path = self._get_toc_path(reg_id)
        if not toc_path.exists():
            # 如果没有目录文件，检查规程是否存在
            if not self._get_reg_dir(reg_id).exists():
                raise RegulationNotFoundError(reg_id)
            # 返回空目录
            info = self.load_info(reg_id)
            return TocTree(
                reg_id=reg_id,
                title=info.title,
                total_pages=info.total_pages,
                items=[],
            )

        with open(toc_path, encoding="utf-8") as f:
            data = json.load(f)
            return TocTree.model_validate(data)

    def load_info(self, reg_id: str) -> RegulationInfo:
        """
        加载规程信息

        Args:
            reg_id: 规程标识

        Returns:
            RegulationInfo

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        info_path = self._get_info_path(reg_id)
        if not info_path.exists():
            raise RegulationNotFoundError(reg_id)

        with open(info_path, encoding="utf-8") as f:
            data = json.load(f)
            return RegulationInfo.model_validate(data)

    def load_document_structure(self, reg_id: str) -> DocumentStructure | None:
        """
        加载文档结构

        Args:
            reg_id: 规程标识

        Returns:
            DocumentStructure，如果不存在返回 None
        """
        structure_path = self._get_structure_path(reg_id)
        if not structure_path.exists():
            return None

        with open(structure_path, encoding="utf-8") as f:
            data = json.load(f)
            return DocumentStructure.model_validate(data)

    def save_document_structure(self, doc_structure: DocumentStructure) -> None:
        """
        单独保存文档结构

        Args:
            doc_structure: 文档结构
        """
        reg_dir = self._get_reg_dir(doc_structure.reg_id)
        reg_dir.mkdir(parents=True, exist_ok=True)

        structure_path = self._get_structure_path(doc_structure.reg_id)
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(doc_structure.model_dump(), f, ensure_ascii=False, indent=2)

        logger.info(f"文档结构已保存: {len(doc_structure.all_nodes)} 个章节节点")

    def list_regulations(self) -> list[RegulationInfo]:
        """
        列出所有已入库的规程

        Returns:
            RegulationInfo 列表
        """
        regulations = []
        for reg_dir in self.pages_dir.iterdir():
            if reg_dir.is_dir():
                try:
                    info = self.load_info(reg_dir.name)
                    regulations.append(info)
                except RegulationNotFoundError:
                    continue
        return regulations

    def delete_regulation(self, reg_id: str) -> bool:
        """
        删除规程

        Args:
            reg_id: 规程标识

        Returns:
            是否删除成功
        """
        reg_dir = self._get_reg_dir(reg_id)
        if not reg_dir.exists():
            return False

        import shutil
        shutil.rmtree(reg_dir)
        logger.info(f"规程 {reg_id} 已删除")
        return True

    def exists(self, reg_id: str) -> bool:
        """检查规程是否存在"""
        return self._get_reg_dir(reg_id).exists()

    # ========================================================================
    # 表格注册表相关方法
    # ========================================================================

    def save_table_registry(self, registry: TableRegistry) -> None:
        """保存表格注册表

        Args:
            registry: 表格注册表
        """
        reg_dir = self._get_reg_dir(registry.reg_id)
        reg_dir.mkdir(parents=True, exist_ok=True)

        registry_path = self._get_table_registry_path(registry.reg_id)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry.model_dump(), f, ensure_ascii=False, indent=2)

        logger.info(
            f"表格注册表已保存: {registry.total_tables} 个表格, "
            f"{registry.cross_page_tables} 个跨页表格"
        )

    def load_table_registry(self, reg_id: str) -> TableRegistry | None:
        """加载表格注册表

        Args:
            reg_id: 规程标识

        Returns:
            TableRegistry，如果不存在返回 None
        """
        registry_path = self._get_table_registry_path(reg_id)
        if not registry_path.exists():
            return None

        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
            return TableRegistry.model_validate(data)

    def get_table_by_id(self, reg_id: str, table_id: str) -> TableEntry | None:
        """通过 ID 快速获取表格

        优先使用表格注册表（O(1) 查找），如果注册表不存在则降级为遍历页面。

        Args:
            reg_id: 规程标识
            table_id: 表格 ID（可以是主表格 ID 或段落 ID）

        Returns:
            TableEntry，如果不存在返回 None
        """
        # 优先使用注册表
        registry = self.load_table_registry(reg_id)
        if registry:
            # 直接查找主表格
            if table_id in registry.tables:
                return registry.tables[table_id]

            # 通过段落 ID 映射查找
            if table_id in registry.segment_to_table:
                master_id = registry.segment_to_table[table_id]
                return registry.tables.get(master_id)

            return None

        # 降级：遍历所有页面查找（向后兼容）
        return self._get_table_by_id_legacy(reg_id, table_id)

    def _get_table_by_id_legacy(self, reg_id: str, table_id: str) -> TableEntry | None:
        """遍历页面查找表格（向后兼容）

        Args:
            reg_id: 规程标识
            table_id: 表格 ID

        Returns:
            TableEntry，如果不存在返回 None
        """
        try:
            info = self.load_info(reg_id)
        except RegulationNotFoundError:
            return None

        for page_num in range(1, info.total_pages + 1):
            try:
                page = self.load_page(reg_id, page_num)
                for block in page.content_blocks:
                    if (
                        block.block_type == "table"
                        and block.table_meta
                        and block.table_meta.table_id == table_id
                    ):
                        # 构建简单的 TableEntry（不含跨页合并）
                        from grid_code.storage.models import TableSegment

                        return TableEntry(
                            table_id=table_id,
                            caption=block.table_meta.caption,
                            chapter_path=block.chapter_path,
                            page_start=page_num,
                            page_end=page_num,
                            is_cross_page=False,
                            segments=[
                                TableSegment(
                                    segment_id=table_id,
                                    page_num=page_num,
                                    block_id=block.block_id,
                                    is_header=True,
                                    row_start=0,
                                    row_end=block.table_meta.row_count,
                                )
                            ],
                            row_count=block.table_meta.row_count,
                            col_count=block.table_meta.col_count,
                            col_headers=block.table_meta.col_headers,
                            merged_markdown=block.content_markdown,
                        )
            except PageNotFoundError:
                continue

        return None

    def get_tables_on_page(self, reg_id: str, page_num: int) -> list[TableEntry]:
        """获取指定页面上的所有表格

        Args:
            reg_id: 规程标识
            page_num: 页码

        Returns:
            TableEntry 列表
        """
        registry = self.load_table_registry(reg_id)
        if registry and page_num in registry.page_to_tables:
            table_ids = registry.page_to_tables[page_num]
            return [
                registry.tables[tid]
                for tid in table_ids
                if tid in registry.tables
            ]

        # 降级：从页面读取
        try:
            page = self.load_page(reg_id, page_num)
            results = []
            for block in page.content_blocks:
                if block.block_type == "table" and block.table_meta:
                    entry = self._get_table_by_id_legacy(
                        reg_id, block.table_meta.table_id
                    )
                    if entry:
                        results.append(entry)
            return results
        except (RegulationNotFoundError, PageNotFoundError):
            return []
