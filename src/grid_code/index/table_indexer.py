"""表格索引构建器

从 TableRegistry 构建表格的 FTS5 和向量索引。
"""

from loguru import logger

from grid_code.index.table_fts5 import TableFTS5Index
from grid_code.index.table_lancedb import TableLanceDBIndex
from grid_code.storage.models import TableRegistry
from grid_code.storage.page_store import PageStore


class TableIndexer:
    """表格索引构建器

    负责从 TableRegistry 构建表格索引。
    """

    def __init__(
        self,
        page_store: PageStore | None = None,
        fts_index: TableFTS5Index | None = None,
        vector_index: TableLanceDBIndex | None = None,
    ):
        """
        初始化表格索引构建器

        Args:
            page_store: PageStore 实例
            fts_index: TableFTS5Index 实例
            vector_index: TableLanceDBIndex 实例
        """
        self._page_store = page_store
        self._fts_index = fts_index
        self._vector_index = vector_index

    @property
    def page_store(self) -> PageStore:
        """获取 PageStore（延迟加载）"""
        if self._page_store is None:
            self._page_store = PageStore()
        return self._page_store

    @property
    def fts_index(self) -> TableFTS5Index:
        """获取 FTS5 索引（延迟加载）"""
        if self._fts_index is None:
            self._fts_index = TableFTS5Index()
        return self._fts_index

    @property
    def vector_index(self) -> TableLanceDBIndex:
        """获取向量索引（延迟加载）"""
        if self._vector_index is None:
            self._vector_index = TableLanceDBIndex()
        return self._vector_index

    def build_index(self, reg_id: str, rebuild: bool = False) -> dict:
        """
        为规程构建表格索引

        Args:
            reg_id: 规程标识
            rebuild: 是否重建索引（删除现有索引后重建）

        Returns:
            构建统计信息:
            - reg_id: 规程标识
            - total_tables: 表格总数
            - indexed_fts: FTS5 索引数量
            - indexed_vector: 向量索引数量
        """
        stats = {
            "reg_id": reg_id,
            "total_tables": 0,
            "indexed_fts": 0,
            "indexed_vector": 0,
            "cross_page_tables": 0,
        }

        # 加载表格注册表
        registry = self.page_store.load_table_registry(reg_id)
        if registry is None:
            logger.warning(f"[TableIndexer] 规程 {reg_id} 没有表格注册表，尝试构建...")
            registry = self._build_registry(reg_id)
            if registry is None:
                logger.error(f"[TableIndexer] 无法为规程 {reg_id} 构建表格注册表")
                return stats

        stats["total_tables"] = registry.total_tables
        stats["cross_page_tables"] = registry.cross_page_tables

        # 如果需要重建，先删除现有索引
        if rebuild:
            logger.info(f"[TableIndexer] 删除规程 {reg_id} 的现有表格索引...")
            self.fts_index.delete_regulation(reg_id)
            self.vector_index.delete_regulation(reg_id)

        # 构建 FTS5 索引
        logger.info(f"[TableIndexer] 构建 FTS5 索引: {reg_id}...")
        stats["indexed_fts"] = self.fts_index.index_registry(registry)

        # 构建向量索引
        logger.info(f"[TableIndexer] 构建向量索引: {reg_id}...")
        stats["indexed_vector"] = self.vector_index.index_registry(registry)

        logger.info(
            f"[TableIndexer] 规程 {reg_id} 表格索引完成: "
            f"共 {stats['total_tables']} 个表格 "
            f"(跨页 {stats['cross_page_tables']} 个), "
            f"FTS5 {stats['indexed_fts']} 条, "
            f"向量 {stats['indexed_vector']} 条"
        )

        return stats

    def _build_registry(self, reg_id: str) -> TableRegistry | None:
        """
        从页面构建表格注册表

        Args:
            reg_id: 规程标识

        Returns:
            TableRegistry 或 None（如果构建失败）
        """
        try:
            from grid_code.parser.table_registry_builder import TableRegistryBuilder

            builder = TableRegistryBuilder(self.page_store)
            registry = builder.build(reg_id)
            self.page_store.save_table_registry(registry)
            return registry
        except Exception as e:
            logger.error(f"[TableIndexer] 构建表格注册表失败: {e}")
            return None

    def delete_index(self, reg_id: str) -> None:
        """
        删除规程的表格索引

        Args:
            reg_id: 规程标识
        """
        logger.info(f"[TableIndexer] 删除规程 {reg_id} 的表格索引...")
        self.fts_index.delete_regulation(reg_id)
        self.vector_index.delete_regulation(reg_id)
        logger.info(f"[TableIndexer] 规程 {reg_id} 的表格索引已删除")

    def get_index_stats(self, reg_id: str) -> dict:
        """
        获取规程的表格索引统计信息

        Args:
            reg_id: 规程标识

        Returns:
            统计信息字典
        """
        fts_count = self.fts_index.get_table_count(reg_id)
        vector_count = self.vector_index.get_table_count(reg_id)

        registry = self.page_store.load_table_registry(reg_id)
        total_tables = registry.total_tables if registry else 0

        return {
            "reg_id": reg_id,
            "total_tables": total_tables,
            "indexed_fts": fts_count,
            "indexed_vector": vector_count,
            "index_complete": fts_count == total_tables and vector_count == total_tables,
        }

    def close(self):
        """关闭索引连接"""
        if self._fts_index:
            self._fts_index.close()
        if self._vector_index:
            self._vector_index.close()
