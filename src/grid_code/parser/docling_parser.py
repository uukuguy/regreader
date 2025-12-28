"""Docling 文档解析器

封装 Docling 库，实现 PDF/DOCX → 结构化数据的转换。
"""

from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter
from docling.datamodel.document import ConversionResult
from loguru import logger

from grid_code.exceptions import ParserError


class DoclingParser:
    """Docling 文档解析器"""

    def __init__(self):
        """初始化解析器"""
        self._converter: DocumentConverter | None = None

    @property
    def converter(self) -> DocumentConverter:
        """延迟初始化 DocumentConverter"""
        if self._converter is None:
            logger.info("初始化 Docling DocumentConverter...")
            self._converter = DocumentConverter()
        return self._converter

    def parse(self, file_path: str | Path) -> ConversionResult:
        """
        解析文档文件

        Args:
            file_path: 文档文件路径（支持 PDF, DOCX, PPTX, XLSX, HTML）

        Returns:
            Docling ConversionResult 对象

        Raises:
            ParserError: 文件不存在或解析失败
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise ParserError(f"文件不存在: {file_path}")

        logger.info(f"开始解析文档: {file_path.name}")

        try:
            result = self.converter.convert(str(file_path))
            logger.info(f"文档解析完成: {file_path.name}")
            return result
        except Exception as e:
            raise ParserError(f"文档解析失败: {file_path.name} - {e}") from e

    def parse_to_markdown(self, file_path: str | Path) -> str:
        """
        解析文档并导出为 Markdown

        Args:
            file_path: 文档文件路径

        Returns:
            Markdown 格式的文档内容
        """
        result = self.parse(file_path)
        return result.document.export_to_markdown()

    def parse_to_dict(self, file_path: str | Path) -> dict[str, Any]:
        """
        解析文档并导出为字典

        Args:
            file_path: 文档文件路径

        Returns:
            文档的结构化字典表示
        """
        result = self.parse(file_path)
        return result.document.export_to_dict()

    def get_page_count(self, result: ConversionResult) -> int:
        """
        获取文档总页数

        Args:
            result: Docling 解析结果

        Returns:
            文档总页数
        """
        doc = result.document
        # 从 provenance 中提取最大页码
        max_page = 0
        for item in doc.texts:
            if item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no') and prov.page_no:
                        max_page = max(max_page, prov.page_no)
        for item in doc.tables:
            if item.prov:
                for prov in item.prov:
                    if hasattr(prov, 'page_no') and prov.page_no:
                        max_page = max(max_page, prov.page_no)
        return max_page
