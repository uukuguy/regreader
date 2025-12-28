"""混合检索接口

结合 FTS5 关键词检索和 LanceDB 语义检索。
"""

from loguru import logger

from grid_code.config import get_settings
from grid_code.index.fts_index import FTSIndex
from grid_code.index.vector_index import VectorIndex
from grid_code.storage.models import SearchResult


class HybridSearch:
    """混合检索器"""

    def __init__(
        self,
        fts_index: FTSIndex | None = None,
        vector_index: VectorIndex | None = None,
    ):
        """
        初始化混合检索器

        Args:
            fts_index: FTS 索引实例
            vector_index: 向量索引实例
        """
        self.fts_index = fts_index or FTSIndex()
        self.vector_index = vector_index or VectorIndex()

        settings = get_settings()
        self.fts_weight = settings.fts_weight
        self.vector_weight = settings.vector_weight

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        执行混合检索

        Args:
            query: 搜索查询
            reg_id: 限定规程（可选）
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制

        Returns:
            合并后的 SearchResult 列表
        """
        # 分别执行两种检索
        fts_results = self.fts_index.search(
            query, reg_id=reg_id, chapter_scope=chapter_scope, limit=limit
        )
        vector_results = self.vector_index.search(
            query, reg_id=reg_id, chapter_scope=chapter_scope, limit=limit
        )

        logger.debug(f"FTS 检索到 {len(fts_results)} 条，向量检索到 {len(vector_results)} 条")

        # 合并结果
        merged = self._merge_results(fts_results, vector_results, limit)

        return merged

    def _merge_results(
        self,
        fts_results: list[SearchResult],
        vector_results: list[SearchResult],
        limit: int,
    ) -> list[SearchResult]:
        """
        合并两种检索的结果

        使用 RRF (Reciprocal Rank Fusion) 算法合并排名
        """
        # 使用 (reg_id, page_num, block_id) 作为唯一键
        result_map: dict[tuple, SearchResult] = {}
        score_map: dict[tuple, float] = {}

        k = 60  # RRF 参数

        # 处理 FTS 结果
        for rank, result in enumerate(fts_results):
            key = (result.reg_id, result.page_num, result.block_id)
            rrf_score = self.fts_weight / (k + rank + 1)

            if key not in result_map:
                result_map[key] = result
                score_map[key] = 0
            score_map[key] += rrf_score

        # 处理向量结果
        for rank, result in enumerate(vector_results):
            key = (result.reg_id, result.page_num, result.block_id)
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
            # 更新分数为合并后的 RRF 分数
            merged.append(SearchResult(
                reg_id=result.reg_id,
                page_num=result.page_num,
                chapter_path=result.chapter_path,
                snippet=result.snippet,
                score=score_map[key],
                block_id=result.block_id,
            ))

        return merged

    def close(self):
        """关闭索引连接"""
        self.fts_index.close()
        self.vector_index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
