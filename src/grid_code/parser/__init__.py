"""文档解析模块"""

from .docling_parser import (
    DoclingParser,
    DoclingParserConfig,
    create_fast_parser,
    create_parser_for_chinese_pdf,
)
from .page_extractor import PageExtractor

__all__ = [
    "DoclingParser",
    "DoclingParserConfig",
    "PageExtractor",
    "create_parser_for_chinese_pdf",
    "create_fast_parser",
]
