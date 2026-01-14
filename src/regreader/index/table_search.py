"""表格混合检索

结合表格关键词检索和语义检索，使用 RRF 算法合并结果。
"""

from typing import Literal

from loguru import logger

from regreader.config import get_settings
from regreader.index.table_fts5 import TableFTS5Index
from regreader.index.table_lancedb import TableLanceDBIndex
from regreader.storage.models import TableSearchResult


class TableHybridSearch:
    """表格混合检索器

    支持三种搜索模式：
    - keyword: 仅使用 FTS5 关键词搜索
    - semantic: 仅使用向量语义搜索
    - hybrid: 混合搜索（RRF 算法合并）
    """

    def __init__(
        self,
        fts_index: TableFTS5Index | None = None,
        vector_index: TableLanceDBIndex | None = None,
    ):
        """
        初始化表格混合检索器

        Args:
            fts_index: 表格 FTS5 索引实例
            vector_index: 表格向量索引实例
        """
        settings = get_settings()

        # 延迟初始化索引
        self._fts_index = fts_index
        self._vector_index = vector_index

        self.fts_weight = settings.fts_weight
        self.vector_weight = settings.vector_weight

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

    def search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        search_mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
        limit: int = 10,
    ) -> list[TableSearchResult]:
        """
        执行表格搜索

        Args:
            query: 搜索查询
                - 表格标题: "表6-2", "母线故障处置"
                - 内容关键词: "母线失压", "复奉直流"
                - 章节范围: "西南分区"
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            search_mode: 搜索模式
                - "keyword": 仅关键词精确匹配
                - "semantic": 仅语义相似度搜索
                - "hybrid": 混合搜索（默认）
            limit: 返回结果数量限制

        Returns:
            TableSearchResult 列表
        """
        if search_mode == "keyword":
            return self._keyword_search(query, reg_id, chapter_scope, limit)
        elif search_mode == "semantic":
            return self._semantic_search(query, reg_id, chapter_scope, limit)
        else:
            return self._hybrid_search(query, reg_id, chapter_scope, limit)

    def _keyword_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None,
        limit: int,
    ) -> list[TableSearchResult]:
        """仅使用关键词搜索"""
        return self.fts_index.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
        )

    def _semantic_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None,
        limit: int,
    ) -> list[TableSearchResult]:
        """仅使用语义搜索"""
        return self.vector_index.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
        )

    def _hybrid_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None,
        limit: int,
    ) -> list[TableSearchResult]:
        """混合搜索（RRF 合并）"""
        # 分别执行两种检索
        keyword_results = self.fts_index.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
        )
        semantic_results = self.vector_index.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
        )

        logger.debug(
            f"表格关键词检索到 {len(keyword_results)} 条，"
            f"语义检索到 {len(semantic_results)} 条"
        )

        # 合并结果
        return self._merge_results(keyword_results, semantic_results, limit)

    def _merge_results(
        self,
        keyword_results: list[TableSearchResult],
        semantic_results: list[TableSearchResult],
        limit: int,
    ) -> list[TableSearchResult]:
        """
        使用 RRF (Reciprocal Rank Fusion) 算法合并结果

        Args:
            keyword_results: 关键词搜索结果
            semantic_results: 语义搜索结果
            limit: 返回数量限制

        Returns:
            合并后的搜索结果
        """
        # 使用 table_id 作为唯一键
        result_map: dict[str, TableSearchResult] = {}
        score_map: dict[str, float] = {}

        k = 60  # RRF 参数

        # 处理关键词检索结果
        for rank, result in enumerate(keyword_results):
            key = result.table_id
            rrf_score = self.fts_weight / (k + rank + 1)

            if key not in result_map:
                result_map[key] = result
                score_map[key] = 0
            score_map[key] += rrf_score

        # 处理语义检索结果
        for rank, result in enumerate(semantic_results):
            key = result.table_id
            rrf_score = self.vector_weight / (k + rank + 1)

            if key not in result_map:
                result_map[key] = result
                score_map[key] = 0
            score_map[key] += rrf_score

        # 按合并分数排序
        sorted_keys = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)

        # 构建最终结果
        merged = []
        for key in sorted_keys[:limit]:
            result = result_map[key]
            # 创建新的结果对象，更新分数
            merged.append(TableSearchResult(
                table_id=result.table_id,
                caption=result.caption,
                reg_id=result.reg_id,
                page_start=result.page_start,
                page_end=result.page_end,
                chapter_path=result.chapter_path,
                is_cross_page=result.is_cross_page,
                row_count=result.row_count,
                col_count=result.col_count,
                col_headers=result.col_headers,
                snippet=result.snippet,
                score=score_map[key],
                match_type=result.match_type,
            ))

        return merged

    def has_index(self, reg_id: str) -> bool:
        """检查规程是否有表格索引

        Args:
            reg_id: 规程标识

        Returns:
            是否存在索引
        """
        fts_count = self.fts_index.get_table_count(reg_id)
        return fts_count > 0

    def close(self):
        """关闭索引连接"""
        if self._fts_index:
            self._fts_index.close()
        if self._vector_index:
            self._vector_index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
