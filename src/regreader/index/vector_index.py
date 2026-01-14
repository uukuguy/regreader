"""兼容性模块

此模块已迁移至 regreader.index.vector.lancedb
保留此文件以兼容旧代码导入。
"""

from regreader.index.vector.lancedb import LanceDBIndex

# 向后兼容：保留旧类名
VectorIndex = LanceDBIndex

__all__ = ["VectorIndex", "LanceDBIndex"]
