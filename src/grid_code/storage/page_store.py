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
    PageContent,
    PageDocument,
    RegulationInfo,
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

    def save_pages(
        self,
        pages: list[PageDocument],
        toc: TocTree | None = None,
        source_file: str = "",
    ) -> RegulationInfo:
        """
        保存页面列表

        Args:
            pages: PageDocument 列表
            toc: 目录树（可选）
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

        Returns:
            (合并后的 Markdown, 是否包含合并的表格)
        """
        if not pages:
            return "", False

        parts = []
        has_merged_tables = False
        pending_table: list[str] | None = None

        for i, page in enumerate(pages):
            # 添加页面分隔标记
            parts.append(f"\n<!-- Page {page.page_num} -->\n")

            # 处理跨页表格
            if page.continues_from_prev and pending_table is not None:
                # 当前页从上一页延续，需要拼接表格
                for block in page.content_blocks:
                    if block.block_type == "table":
                        # 合并表格内容
                        table_lines = block.content_markdown.split("\n")
                        # 跳过表头（前两行：标题行和分隔行）
                        data_lines = [
                            line for line in table_lines[2:]
                            if line.strip() and line.startswith("|")
                        ]
                        pending_table.extend(data_lines)
                        has_merged_tables = True
                        break
                else:
                    # 没有找到表格，刷新待处理表格
                    parts.append("\n".join(pending_table))
                    pending_table = None
            else:
                # 刷新之前的待处理表格
                if pending_table is not None:
                    parts.append("\n".join(pending_table))
                    pending_table = None

            # 处理当前页内容
            if page.continues_to_next:
                # 当前页有跨页表格
                for block in page.content_blocks:
                    if block.block_type == "table" and block.table_meta and block.table_meta.is_truncated:
                        # 开始收集跨页表格
                        pending_table = block.content_markdown.split("\n")
                    else:
                        parts.append(block.content_markdown)
            else:
                # 普通页面，直接添加内容
                parts.append(page.content_markdown)

        # 处理最后的待处理表格
        if pending_table is not None:
            parts.append("\n".join(pending_table))

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
