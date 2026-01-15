"""混合检索接口

结合关键词检索和语义检索，支持多种后端实现。
"""

from loguru import logger

from regreader.core.config import get_settings
from regreader.index.base import BaseKeywordIndex, BaseVectorIndex
from regreader.storage.models import SearchResult


class HybridSearch:
    """混合检索器

    支持可插拔的关键词索引和向量索引后端。
    """

    def __init__(
        self,
        keyword_index: BaseKeywordIndex | None = None,
        vector_index: BaseVectorIndex | None = None,
    ):
        """
        初始化混合检索器

        Args:
            keyword_index: 关键词索引实例（BaseKeywordIndex 子类）
            vector_index: 向量索引实例（BaseVectorIndex 子类）
        """
        settings = get_settings()

        # 延迟导入，避免循环依赖
        if keyword_index is None:
            keyword_index = self._create_default_keyword_index(settings)
        if vector_index is None:
            vector_index = self._create_default_vector_index(settings)

        self.keyword_index = keyword_index
        self.vector_index = vector_index

        self.fts_weight = settings.fts_weight
        self.vector_weight = settings.vector_weight

        logger.info(
            f"混合检索器初始化完成: 关键词={self.keyword_index.name}, "
            f"向量={self.vector_index.name}"
        )

    def _create_default_keyword_index(self, settings) -> BaseKeywordIndex:
        """根据配置创建默认关键词索引"""
        backend = getattr(settings, "keyword_index_backend", "fts5")

        if backend == "tantivy":
            from regreader.index.keyword import TantivyIndex
            return TantivyIndex()
        elif backend == "whoosh":
            from regreader.index.keyword import WhooshIndex
            return WhooshIndex()
        else:  # 默认使用 fts5
            from regreader.index.keyword import FTS5Index
            return FTS5Index()

    def _create_default_vector_index(self, settings) -> BaseVectorIndex:
        """根据配置创建默认向量索引"""
        backend = getattr(settings, "vector_index_backend", "lancedb")

        if backend == "qdrant":
            from regreader.index.vector import QdrantIndex
            return QdrantIndex()
        else:  # 默认使用 lancedb
            from regreader.index.vector import LanceDBIndex
            return LanceDBIndex()

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[SearchResult]:
        """
        执行混合检索

        Args:
            query: 搜索查询
            reg_id: 限定规程（可选）
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制
            block_types: 限定块类型列表（可选）
            section_number: 精确匹配章节号（可选）

        Returns:
            合并后的 SearchResult 列表
        """
        # 分别执行两种检索
        keyword_results = self.keyword_index.search(
            query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
            block_types=block_types,
            section_number=section_number,
        )
        vector_results = self.vector_index.search(
            query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
            block_types=block_types,
            section_number=section_number,
        )

        logger.debug(
            f"关键词检索到 {len(keyword_results)} 条，向量检索到 {len(vector_results)} 条"
        )

        # 合并结果
        merged = self._merge_results(keyword_results, vector_results, limit)

        return merged

    def _merge_results(
        self,
        keyword_results: list[SearchResult],
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

        # 处理关键词检索结果
        for rank, result in enumerate(keyword_results):
            key = (result.reg_id, result.page_num, result.block_id)
            rrf_score = self.fts_weight / (k + rank + 1)

            if key not in result_map:
                result_map[key] = result
                score_map[key] = 0
            score_map[key] += rrf_score

        # 处理向量检索结果
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
        self.keyword_index.close()
        self.vector_index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
