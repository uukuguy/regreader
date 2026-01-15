"""RegReader 核心层

提供全局配置和异常定义。
"""

from .config import RegReaderSettings, get_settings
from .exceptions import (
    AnnotationNotFoundError,
    ChapterNotFoundError,
    IndexError,
    InvalidPageRangeError,
    PageNotFoundError,
    ParserError,
    ReferenceResolutionError,
    RegReaderError,
    RegulationNotFoundError,
    StorageError,
    TableNotFoundError,
)

__all__ = [
    # Config
    "RegReaderSettings",
    "get_settings",
    # Exceptions
    "RegReaderError",
    "ParserError",
    "StorageError",
    "IndexError",
    "RegulationNotFoundError",
    "PageNotFoundError",
    "InvalidPageRangeError",
    "ChapterNotFoundError",
    "AnnotationNotFoundError",
    "TableNotFoundError",
    "ReferenceResolutionError",
]
