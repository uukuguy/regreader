"""Qdrant 向量索引

实现基于 Qdrant 的语义检索。
https://github.com/qdrant/qdrant-client
"""

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from grid_code.config import get_settings
from grid_code.index.base import BaseVectorIndex
from grid_code.storage.models import PageDocument, SearchResult

if TYPE_CHECKING:
    from grid_code.embedding import BaseEmbedder


class QdrantIndex(BaseVectorIndex):
    """Qdrant 向量索引

    Qdrant 是高性能向量数据库，支持本地模式和服务器模式。
    """

    COLLECTION_NAME = "page_vectors"

    def __init__(
        self,
        path: Path | None = None,
        url: str | None = None,
        api_key: str | None = None,
        embedder: "BaseEmbedder | None" = None,
    ):
        """初始化 Qdrant 索引

        Args:
            path: 本地存储路径（本地模式）
            url: Qdrant 服务器 URL（服务器模式）
            api_key: API Key（服务器模式）
            embedder: 嵌入模型实例（可选，默认使用全局单例）
        """
        settings = get_settings()
        self.path = path or (settings.index_dir / "qdrant")
        self.url = url
        self.api_key = api_key

        self._client = None
        self._embedder = embedder

        self._init_client()

    @property
    def name(self) -> str:
        return "Qdrant"

    @property
    def embedding_dimension(self) -> int:
        return self.embedder.dimension

    @property
    def embedder(self) -> "BaseEmbedder":
        """获取嵌入模型（延迟初始化）"""
        if self._embedder is None:
            from grid_code.embedding import get_embedder

            self._embedder = get_embedder()
        return self._embedder

    def _init_client(self):
        """初始化 Qdrant 客户端"""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            logger.warning("qdrant-client 未安装，请运行: pip install qdrant-client")
            return

        # 创建客户端
        if self.url:
            # 服务器模式
            self._client = QdrantClient(url=self.url, api_key=self.api_key)
        else:
            # 本地模式
            self.path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self.path))

        # 创建或获取集合
        try:
            collections = self._client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.COLLECTION_NAME not in collection_names:
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self._embedding_dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.debug(f"Qdrant 集合 {self.COLLECTION_NAME} 创建完成")
            else:
                logger.debug(f"Qdrant 集合 {self.COLLECTION_NAME} 已存在")
        except Exception as e:
            logger.warning(f"Qdrant 集合初始化失败: {e}")

    def index_page(self, page: PageDocument) -> None:
        """索引单个页面"""
        if self._client is None:
            logger.warning("Qdrant 客户端未初始化")
            return

        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            return

        points = []
        for block in page.content_blocks:
            content = block.content_markdown.strip()
            if not content or len(content) < 10:
                continue

            vector = self.embedder.embed_document(content)

            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "reg_id": page.reg_id,
                    "page_num": page.page_num,
                    "block_id": block.block_id,
                    "content": content[:500],
                    "chapter_path": " > ".join(page.chapter_path),
                },
            ))

        if not points:
            return

        try:
            self._client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )
        except Exception as e:
            logger.warning(f"Qdrant 索引写入错误: {e}")

    def index_pages(self, pages: list[PageDocument]) -> None:
        """批量索引页面"""
        if self._client is None:
            logger.warning("Qdrant 客户端未初始化")
            return

        try:
            from qdrant_client.models import PointStruct
        except ImportError:
            return

        logger.info(f"[Qdrant] 开始向量索引 {len(pages)} 页...")

        all_texts = []
        text_to_payload = []

        for page in pages:
            for block in page.content_blocks:
                content = block.content_markdown.strip()
                if not content or len(content) < 10:
                    continue

                all_texts.append(content)
                text_to_payload.append({
                    "reg_id": page.reg_id,
                    "page_num": page.page_num,
                    "block_id": block.block_id,
                    "content": content[:500],
                    "chapter_path": " > ".join(page.chapter_path),
                })

        if not all_texts:
            logger.warning("没有可索引的内容")
            return

        logger.info(f"生成 {len(all_texts)} 个嵌入向量...")
        all_vectors = self.embedder.embed_documents(all_texts)

        # 批量创建 points
        points = []
        for i, payload in enumerate(text_to_payload):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=all_vectors[i],
                payload=payload,
            ))

        # 分批上传（每批 100 个）
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            try:
                self._client.upsert(
                    collection_name=self.COLLECTION_NAME,
                    points=batch,
                )
            except Exception as e:
                logger.warning(f"Qdrant 批量索引错误: {e}")

        logger.info("[Qdrant] 向量索引构建完成")

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """语义搜索"""
        if self._client is None:
            logger.warning("Qdrant 客户端未初始化")
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
        except ImportError:
            return []

        query_vector = self.embedder.embed_query(query)

        # 构建过滤条件
        query_filter = None
        if reg_id:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="reg_id",
                        match=MatchValue(value=reg_id),
                    )
                ]
            )

        try:
            search_result = self._client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit * 2,  # 多取一些用于章节过滤
            )
        except Exception as e:
            logger.warning(f"Qdrant 搜索错误: {e}")
            return []

        results = []
        for hit in search_result:
            payload = hit.payload or {}

            # 应用章节过滤
            doc_chapter_path = payload.get("chapter_path", "")
            if chapter_scope and chapter_scope not in doc_chapter_path:
                continue

            chapter_path = doc_chapter_path.split(" > ") if doc_chapter_path else []

            results.append(SearchResult(
                reg_id=payload.get("reg_id", ""),
                page_num=payload.get("page_num", 0),
                chapter_path=chapter_path,
                snippet=payload.get("content", ""),
                score=hit.score,
                block_id=payload.get("block_id"),
            ))

            if len(results) >= limit:
                break

        return results

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有向量"""
        if self._client is None:
            return

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
        except ImportError:
            return

        try:
            self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="reg_id",
                            match=MatchValue(value=reg_id),
                        )
                    ]
                ),
            )
            logger.info(f"[Qdrant] 已删除规程 {reg_id} 的向量索引")
        except Exception as e:
            logger.warning(f"Qdrant 删除向量索引失败: {e}")

    def close(self) -> None:
        """关闭连接"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
