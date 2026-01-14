"""兼容性模块

此模块已迁移至 regreader.index.keyword.fts5
保留此文件以兼容旧代码导入。
"""

from regreader.index.keyword.fts5 import FTS5Index

# 向后兼容：保留旧类名
FTSIndex = FTS5Index

__all__ = ["FTSIndex", "FTS5Index"]
