"""Markdown 导出服务

提供灵活的规程导出功能，支持多种导出模式和元数据配置。
"""

from pathlib import Path

from loguru import logger

from regreader.core.exceptions import (
    ChapterNotFoundError,
    InvalidPageRangeError,
    RegulationNotFoundError,
)
from regreader.storage import PageStore
from regreader.storage.models import (
    ChapterNode,
    ContentBlock,
    DocumentStructure,
    ExportConfig,
    ExportMetadata,
    ExportResult,
    PageDocument,
    TocItem,
    TocTree,
)


class ExportService:
    """Markdown 导出服务"""

    def __init__(self, page_store: PageStore | None = None):
        """初始化导出服务

        Args:
            page_store: PageStore 实例（如果为 None 则创建新实例）
        """
        self.page_store = page_store or PageStore()

    # ==================== 公共导出方法 ====================

    def export_full_regulation(
        self,
        reg_id: str,
        config: ExportConfig | None = None,
    ) -> ExportResult:
        """导出完整规程到单个 Markdown 文件

        Args:
            reg_id: 规程标识
            config: 导出配置（如果为 None 则使用默认配置）

        Returns:
            ExportResult 包含输出路径和统计信息

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        config = config or ExportConfig()

        try:
            # 加载规程信息和结构
            info = self.page_store.load_info(reg_id)
            toc = self.page_store.load_toc(reg_id)
            doc_structure = self.page_store.load_document_structure(reg_id)

            # 加载所有页面
            pages = []
            for page_num in range(1, info.total_pages + 1):
                try:
                    page = self.page_store.load_page(reg_id, page_num)
                    pages.append(page)
                except Exception as e:
                    logger.warning(f"Failed to load page {page_num}: {e}")

            # 构建元数据
            metadata = ExportMetadata(
                reg_id=reg_id,
                title=info.title,
                pages=f"1-{info.total_pages}",
                export_mode="full",
                total_pages=len(pages),
                chapter_count=len(doc_structure.all_nodes) if doc_structure else 0,
            )

            # 生成内容
            content = self._build_markdown_content(
                pages=pages,
                metadata=metadata,
                toc=toc,
                config=config,
            )

            # 写入文件或返回内容
            if config.output_path:
                output_path = self._write_to_file(content, config.output_path, config)
                return ExportResult(
                    success=True,
                    output_path=output_path,
                    metadata=metadata,
                    stats=self._calculate_stats(pages, content),
                )
            else:
                return ExportResult(
                    success=True,
                    content=content,
                    metadata=metadata,
                    stats=self._calculate_stats(pages, content),
                )

        except Exception as e:
            logger.error(f"Export failed for {reg_id}: {e}")
            return ExportResult(
                success=False,
                error=str(e),
            )

    def export_chapter(
        self,
        reg_id: str,
        section_number: str,
        config: ExportConfig | None = None,
        include_children: bool = True,
    ) -> ExportResult:
        """导出指定章节到 Markdown（基于内容块精确过滤）

        Args:
            reg_id: 规程标识
            section_number: 章节编号（如 "2.1.4"）
            config: 导出配置
            include_children: 是否包含子章节

        Returns:
            ExportResult 包含章节内容

        Raises:
            ChapterNotFoundError: 章节不存在
        """
        config = config or ExportConfig()

        try:
            # 加载文档结构
            doc_structure = self.page_store.load_document_structure(reg_id)
            if not doc_structure:
                raise ChapterNotFoundError(reg_id, section_number)

            # 查找章节节点
            chapter_node = doc_structure.get_node_by_section_number(section_number)
            if not chapter_node:
                raise ChapterNotFoundError(reg_id, section_number)

            # 收集章节内容块（精确过滤）
            blocks_with_pages, page_nums = self._collect_chapter_blocks(
                reg_id, chapter_node, doc_structure, include_children
            )

            if not blocks_with_pages:
                logger.warning(f"No content blocks found for chapter {section_number}")

            # 构建元数据
            chapter_path = doc_structure.get_chapter_path(chapter_node.node_id)
            sorted_pages = sorted(page_nums) if page_nums else []
            metadata = ExportMetadata(
                reg_id=reg_id,
                title=self.page_store.load_info(reg_id).title,
                chapter=" > ".join(chapter_path),
                section_number=section_number,
                pages=f"{sorted_pages[0]}-{sorted_pages[-1]}" if sorted_pages else None,
                export_mode="chapter",
                total_pages=len(page_nums),
            )

            # 生成内容（基于内容块）
            content = self._build_markdown_from_blocks(
                blocks_with_pages=blocks_with_pages,
                metadata=metadata,
                config=config,
            )

            # 输出处理
            if config.output_path:
                output_path = self._write_to_file(content, config.output_path, config)
                return ExportResult(
                    success=True,
                    output_path=output_path,
                    metadata=metadata,
                    stats=self._calculate_stats_from_blocks(blocks_with_pages, content),
                )
            else:
                return ExportResult(
                    success=True,
                    content=content,
                    metadata=metadata,
                    stats=self._calculate_stats_from_blocks(blocks_with_pages, content),
                )

        except Exception as e:
            logger.error(f"Chapter export failed: {e}")
            return ExportResult(success=False, error=str(e))

    def export_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
        config: ExportConfig | None = None,
    ) -> ExportResult:
        """导出页面范围到 Markdown

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码
            config: 导出配置

        Returns:
            ExportResult 包含页面范围内容

        Raises:
            InvalidPageRangeError: 页面范围无效
        """
        config = config or ExportConfig()

        try:
            # 验证页面范围
            info = self.page_store.load_info(reg_id)
            if start_page < 1 or end_page > info.total_pages or start_page > end_page:
                raise InvalidPageRangeError(reg_id, start_page, end_page)

            # 加载页面
            pages = []
            for page_num in range(start_page, end_page + 1):
                page = self.page_store.load_page(reg_id, page_num)
                pages.append(page)

            # 构建元数据
            metadata = ExportMetadata(
                reg_id=reg_id,
                title=info.title,
                pages=f"{start_page}-{end_page}" if start_page != end_page else str(start_page),
                export_mode="pages",
                total_pages=len(pages),
            )

            # 生成内容
            content = self._build_markdown_content(
                pages=pages,
                metadata=metadata,
                toc=None,
                config=config,
            )

            # 输出处理
            if config.output_path:
                output_path = self._write_to_file(content, config.output_path, config)
                return ExportResult(
                    success=True,
                    output_path=output_path,
                    metadata=metadata,
                    stats=self._calculate_stats(pages, content),
                )
            else:
                return ExportResult(
                    success=True,
                    content=content,
                    metadata=metadata,
                    stats=self._calculate_stats(pages, content),
                )

        except Exception as e:
            logger.error(f"Page range export failed: {e}")
            return ExportResult(success=False, error=str(e))

    # ==================== 辅助方法 ====================

    def _build_markdown_from_blocks(
        self,
        blocks_with_pages: list[tuple[ContentBlock, int]],
        metadata: ExportMetadata,
        config: ExportConfig,
    ) -> str:
        """从内容块列表构建 Markdown 内容（用于章节导出）

        Args:
            blocks_with_pages: (内容块, 页码)元组列表
            metadata: 导出元数据
            config: 导出配置

        Returns:
            完整的 Markdown 内容
        """
        parts = []

        # 1. YAML frontmatter
        if config.include_yaml_frontmatter:
            parts.append(self._build_yaml_frontmatter(metadata))
            parts.append("")

        # 2. 标题
        parts.append(f"# {metadata.title}")
        if metadata.chapter:
            parts.append(f"\n## {metadata.chapter}")
        parts.append("")

        # 3. 正文内容（按页码和 order_in_page 排序）
        sorted_blocks = sorted(blocks_with_pages, key=lambda x: (x[1], x[0].order_in_page))

        current_page = None
        for block, page_num in sorted_blocks:
            # 添加页码标记（如果配置启用且页码变化）
            if config.include_page_markers and page_num != current_page:
                if current_page is not None:  # 不在第一个块前添加标记
                    parts.append("")
                parts.append(f"<!-- Page {page_num} -->")
                parts.append("")
                current_page = page_num

            # 添加内容块
            parts.append(block.content_markdown)

        # 4. 注释汇总（如果配置启用）
        if config.include_annotations:
            # 注意：内容块本身不包含注释，需要从页面加载
            # 这里简化处理，暂不支持注释汇总
            pass

        return "\n".join(parts)

    def _calculate_stats_from_blocks(
        self, blocks_with_pages: list[tuple[ContentBlock, int]], content: str
    ) -> dict[str, int]:
        """从内容块列表计算统计信息

        Args:
            blocks_with_pages: (内容块, 页码)元组列表
            content: 生成的 Markdown 内容

        Returns:
            统计信息字典
        """
        # 统计表格数量
        table_count = sum(1 for block, _ in blocks_with_pages if block.block_type == "table")

        # 统计涉及的页面数量
        page_nums = set(page_num for _, page_num in blocks_with_pages)

        return {
            "pages": len(page_nums),
            "blocks": len(blocks_with_pages),
            "tables": table_count,
            "annotations": 0,  # 暂不支持
            "size_kb": len(content.encode("utf-8")) // 1024,
        }

    def _build_markdown_content(
        self,
        pages: list[PageDocument],
        metadata: ExportMetadata,
        toc: TocTree | None,
        config: ExportConfig,
    ) -> str:
        """构建完整的 Markdown 内容"""
        parts = []

        # 1. YAML frontmatter
        if config.include_yaml_frontmatter:
            parts.append(self._build_yaml_frontmatter(metadata))
            parts.append("")

        # 2. 标题
        parts.append(f"# {metadata.title}")
        if metadata.chapter:
            parts.append(f"\n## {metadata.chapter}")
        parts.append("")

        # 3. TOC（如果请求且位置为 top）
        if config.include_toc and toc and config.toc_position == "top":
            parts.append("## 目录\n")
            parts.append(self._build_toc_markdown(toc, config.toc_max_depth))
            parts.append("\n---\n")

        # 4. 正文内容
        if config.merge_cross_page_tables:
            merged_content, has_merged = self.page_store._merge_pages(
                pages, include_page_markers=config.include_page_markers
            )
            parts.append(merged_content)
        else:
            for page in pages:
                if config.include_page_markers:
                    parts.append(f"\n<!-- Page {page.page_num} -->\n")
                parts.append(page.content_markdown)

        # 5. 注释汇总
        if config.include_annotations:
            annotations = [ann for page in pages for ann in page.annotations]
            if annotations:
                parts.append("\n\n---\n\n## 注释\n")
                for ann in annotations:
                    parts.append(f"\n**{ann.annotation_id}**: {ann.content}\n")

        # 6. TOC at bottom
        if config.include_toc and toc and config.toc_position == "bottom":
            parts.append("\n---\n\n## 目录\n")
            parts.append(self._build_toc_markdown(toc, config.toc_max_depth))

        return "\n".join(parts)

    def _build_yaml_frontmatter(self, metadata: ExportMetadata) -> str:
        """生成 YAML frontmatter 块"""
        import yaml

        data = {
            "reg_id": metadata.reg_id,
            "title": metadata.title,
            "exported_at": metadata.exported_at,
            "export_mode": metadata.export_mode,
        }

        if metadata.chapter:
            data["chapter"] = metadata.chapter
        if metadata.section_number:
            data["section_number"] = metadata.section_number
        if metadata.pages:
            data["pages"] = metadata.pages
        if metadata.total_pages:
            data["total_pages"] = metadata.total_pages
        if metadata.keywords:
            data["keywords"] = metadata.keywords

        yaml_content = yaml.dump(data, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_content}---"

    def _build_toc_markdown(self, toc: TocTree, max_depth: int) -> str:
        """生成层级化的 Markdown 目录"""
        lines = []

        def format_item(item: TocItem, level: int = 0):
            if level >= max_depth:
                return

            indent = "  " * level
            page_info = f" (P{item.page_start})" if item.page_start else ""
            lines.append(f"{indent}- {item.title}{page_info}")

            for child in item.children:
                format_item(child, level + 1)

        for item in toc.items:
            format_item(item)

        return "\n".join(lines)

    def _add_page_markers_to_merged(self, content: str, pages: list[PageDocument]) -> str:
        """在合并内容中添加页码标记"""
        # 简单实现：在每个页面的开始位置添加标记
        # 注意：这是一个简化版本，实际可能需要更复杂的逻辑
        result_parts = []
        for page in pages:
            marker = f"\n<!-- Page {page.page_num} -->\n"
            result_parts.append(marker)
            # 这里简化处理，实际应该从 merged content 中提取对应页面的内容

        # 由于 _merge_pages 已经合并了内容，我们只在开头添加第一个标记
        if pages:
            return f"<!-- Page {pages[0].page_num} -->\n\n{content}"
        return content

    def _calculate_stats(self, pages: list[PageDocument], content: str) -> dict[str, int]:
        """计算导出统计信息"""
        table_count = sum(len(page.get_tables()) for page in pages)
        annotation_count = sum(len(page.annotations) for page in pages)

        return {
            "pages": len(pages),
            "tables": table_count,
            "annotations": annotation_count,
            "size_kb": len(content.encode("utf-8")) // 1024,
        }

    def _write_to_file(self, content: str, path: Path, config: ExportConfig) -> Path:
        """写入内容到文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=config.encoding)
        logger.info(f"Exported to {path}")
        return path

    def _collect_chapter_pages(
        self,
        reg_id: str,
        chapter_node: ChapterNode,
        doc_structure: DocumentStructure,
        include_children: bool,
    ) -> list[PageDocument]:
        """收集章节的所有页面（已废弃，保留用于向后兼容）

        Args:
            reg_id: 规程标识
            chapter_node: 章节节点
            doc_structure: 文档结构
            include_children: 是否包含子章节

        Returns:
            章节页面列表
        """
        pages = []

        # 获取章节起始页
        start_page = chapter_node.page_num

        # 查找章节结束页
        end_page = self._find_chapter_end_page(chapter_node, doc_structure)

        # 加载页面范围
        for page_num in range(start_page, end_page + 1):
            try:
                page = self.page_store.load_page(reg_id, page_num)
                pages.append(page)
            except Exception as e:
                logger.warning(f"Failed to load page {page_num}: {e}")

        return pages

    def _collect_chapter_blocks(
        self,
        reg_id: str,
        chapter_node: ChapterNode,
        doc_structure: DocumentStructure,
        include_children: bool,
    ) -> tuple[list[tuple[ContentBlock, int]], set[int]]:
        """收集章节的所有内容块（基于 chapter_node_id 精确过滤）

        Args:
            reg_id: 规程标识
            chapter_node: 章节节点
            doc_structure: 文档结构
            include_children: 是否包含子章节

        Returns:
            ((内容块, 页码)元组列表, 涉及的页码集合)
        """
        blocks_with_pages: list[tuple[ContentBlock, int]] = []
        page_nums: set[int] = set()

        # 收集目标章节节点ID
        target_node_ids = {chapter_node.node_id}
        if include_children:
            target_node_ids.update(self._collect_descendant_node_ids(chapter_node, doc_structure))

        # 获取章节起始页和结束页范围
        start_page = chapter_node.page_num
        end_page = self._find_chapter_end_page(chapter_node, doc_structure)

        # 遍历页面范围，收集匹配的内容块
        for page_num in range(start_page, end_page + 1):
            try:
                page = self.page_store.load_page(reg_id, page_num)
                for block in page.content_blocks:
                    # 如果 chapter_node_id 存在，使用精确匹配
                    if block.chapter_node_id is not None:
                        if block.chapter_node_id in target_node_ids:
                            blocks_with_pages.append((block, page_num))
                            page_nums.add(page_num)
                    else:
                        # 如果 chapter_node_id 为 None，使用章节路径匹配（降级方案）
                        # 检查块的章节路径是否以目标章节开头
                        if self._block_belongs_to_chapter(block, chapter_node, doc_structure, include_children):
                            blocks_with_pages.append((block, page_num))
                            page_nums.add(page_num)
            except Exception as e:
                logger.warning(f"Failed to load page {page_num}: {e}")

        return blocks_with_pages, page_nums

    def _block_belongs_to_chapter(
        self,
        block: ContentBlock,
        chapter_node: ChapterNode,
        doc_structure: DocumentStructure,
        include_children: bool,
    ) -> bool:
        """检查内容块是否属于指定章节（降级方案，用于 chapter_node_id 为 None 的情况）

        Args:
            block: 内容块
            chapter_node: 章节节点
            doc_structure: 文档结构
            include_children: 是否包含子章节

        Returns:
            是否属于该章节
        """
        if not block.chapter_path:
            return False

        # 获取目标章节的完整标题
        target_section = chapter_node.section_number

        # 检查块的章节路径中是否包含目标章节
        for path_item in block.chapter_path:
            if path_item.startswith(target_section):
                if include_children:
                    # 包含子章节：只要以目标章节编号开头即可
                    return True
                else:
                    # 不包含子章节：必须完全匹配
                    return path_item.startswith(f"{target_section} ") or path_item == target_section

        return False

    def _collect_descendant_node_ids(
        self, node: ChapterNode, doc_structure: DocumentStructure
    ) -> set[str]:
        """递归收集所有子孙节点ID

        Args:
            node: 起始节点
            doc_structure: 文档结构

        Returns:
            子孙节点ID集合
        """
        descendants = set()
        for child_id in node.children_ids:
            descendants.add(child_id)
            child_node = doc_structure.all_nodes.get(child_id)
            if child_node:
                descendants.update(self._collect_descendant_node_ids(child_node, doc_structure))
        return descendants

    def _find_chapter_end_page(
        self, node: ChapterNode, doc_structure: DocumentStructure
    ) -> int:
        """查找章节的结束页码

        Args:
            node: 章节节点
            doc_structure: 文档结构

        Returns:
            结束页码
        """
        # 简化实现：查找下一个同级或上级节点的起始页
        # 如果没有，使用规程总页数
        info = self.page_store.load_info(doc_structure.reg_id)

        # 获取所有节点并按页码排序
        all_nodes = sorted(doc_structure.all_nodes.values(), key=lambda n: n.page_num)

        # 查找当前节点的位置
        current_index = next((i for i, n in enumerate(all_nodes) if n.node_id == node.node_id), -1)

        if current_index == -1 or current_index == len(all_nodes) - 1:
            # 最后一个节点，使用总页数
            return info.total_pages

        # 查找下一个同级或更高级别的节点
        for next_node in all_nodes[current_index + 1 :]:
            if next_node.level <= node.level:
                # 如果下一个节点在同一页，结束页就是当前页
                # 否则结束页是下一个节点的前一页
                if next_node.page_num == node.page_num:
                    return node.page_num
                else:
                    return next_node.page_num - 1

        # 没有找到，使用总页数
        return info.total_pages
