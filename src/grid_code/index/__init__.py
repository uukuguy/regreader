"""索引模块

提供可插拔的关键词索引和向量索引实现。
"""

from .base import BaseKeywordIndex, BaseVectorIndex
from .hybrid_search import HybridSearch

# 关键词索引实现
from .keyword import FTS5Index, TantivyIndex, WhooshIndex

# 向量索引实现
from .vector import LanceDBIndex, QdrantIndex

# 表格专用索引
from .table_fts5 import TableFTS5Index
from .table_lancedb import TableLanceDBIndex
from .table_search import TableHybridSearch
from .table_indexer import TableIndexer

# 向后兼容：保留旧的导入名称
FTSIndex = FTS5Index
VectorIndex = LanceDBIndex

__all__ = [
    # 抽象基类
    "BaseKeywordIndex",
    "BaseVectorIndex",
    # 混合检索
    "HybridSearch",
    # 关键词索引
    "FTS5Index",
    "TantivyIndex",
    "WhooshIndex",
    # 向量索引
    "LanceDBIndex",
    "QdrantIndex",
    # 表格专用索引
    "TableFTS5Index",
    "TableLanceDBIndex",
    "TableHybridSearch",
    "TableIndexer",
    # 向后兼容
    "FTSIndex",
    "VectorIndex",
]
