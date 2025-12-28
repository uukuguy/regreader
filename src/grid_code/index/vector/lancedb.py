"""LanceDB 向量索引

实现基于 LanceDB 的语义检索。
"""

from pathlib import Path

import lancedb
from loguru import logger

from grid_code.config import get_settings
from grid_code.index.base import BaseVectorIndex
from grid_code.storage.models import PageDocument, SearchResult


class LanceDBIndex(BaseVectorIndex):
    """LanceDB 向量索引"""

    TABLE_NAME = "page_vectors"

    def __init__(self, db_path: Path | None = None):
        """
        初始化向量索引

        Args:
            db_path: LanceDB 数据库路径，默认使用配置中的路径
        """
        settings = get_settings()
        self.db_path = db_path or settings.lancedb_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db: lancedb.DBConnection | None = None
        self._table: lancedb.table.Table | None = None
        self._embedder = None
        self.embedding_model_name = settings.embedding_model
        self._embedding_dimension = settings.embedding_dimension

    @property
    def name(self) -> str:
        return "LanceDB"

    @property
    def embedding_dimension(self) -> int:
        return self._embedding_dimension

    @property
    def db(self) -> lancedb.DBConnection:
        """获取数据库连接"""
        if self._db is None:
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    @property
    def embedder(self):
        """延迟加载嵌入模型"""
        if self._embedder is None:
            logger.info(f"加载嵌入模型: {self.embedding_model_name}")
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.embedding_model_name)
        return self._embedder

    def _get_table(self) -> lancedb.table.Table | None:
        """获取向量表"""
        if self._table is None:
            try:
                self._table = self.db.open_table(self.TABLE_NAME)
            except Exception:
                return None
        return self._table

    def _create_table(self, data: list[dict]):
        """创建向量表"""
        self._table = self.db.create_table(
            self.TABLE_NAME,
            data=data,
            mode="overwrite",
        )

    def _embed_text(self, text: str) -> list[float]:
        """生成文本嵌入向量"""
        embedding = self.embedder.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本嵌入向量"""
        embeddings = self.embedder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def index_page(self, page: PageDocument) -> None:
        """索引单个页面"""
        records = []

        for block in page.content_blocks:
            content = block.content_markdown.strip()
            if not content or len(content) < 10:
                continue

            vector = self._embed_text(content)

            records.append({
                "vector": vector,
                "reg_id": page.reg_id,
                "page_num": page.page_num,
                "block_id": block.block_id,
                "content": content[:500],
                "chapter_path": " > ".join(page.chapter_path),
            })

        if not records:
            return

        table = self._get_table()
        if table is None:
            self._create_table(records)
        else:
            table.add(records)

    def index_pages(self, pages: list[PageDocument]) -> None:
        """批量索引页面"""
        logger.info(f"[LanceDB] 开始向量索引 {len(pages)} 页...")

        all_records = []
        all_texts = []

        text_to_record = []
        for page in pages:
            for block in page.content_blocks:
                content = block.content_markdown.strip()
                if not content or len(content) < 10:
                    continue

                all_texts.append(content)
                text_to_record.append({
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
        all_vectors = self._embed_texts(all_texts)

        for i, record in enumerate(text_to_record):
            record["vector"] = all_vectors[i]
            all_records.append(record)

        table = self._get_table()
        if table is None:
            self._create_table(all_records)
        else:
            table.add(all_records)

        logger.info("[LanceDB] 向量索引构建完成")

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """语义搜索"""
        table = self._get_table()
        if table is None:
            logger.warning("向量索引表不存在")
            return []

        query_vector = self._embed_text(query)
        search_query = table.search(query_vector).limit(limit * 2)

        try:
            results_df = search_query.to_pandas()
        except Exception as e:
            logger.warning(f"LanceDB 搜索错误: {e}")
            return []

        if results_df.empty:
            return []

        results = []
        for _, row in results_df.iterrows():
            if reg_id and row["reg_id"] != reg_id:
                continue
            if chapter_scope and chapter_scope not in row["chapter_path"]:
                continue

            chapter_path = row["chapter_path"].split(" > ") if row["chapter_path"] else []

            results.append(SearchResult(
                reg_id=row["reg_id"],
                page_num=int(row["page_num"]),
                chapter_path=chapter_path,
                snippet=row["content"],
                score=1 - row["_distance"],
                block_id=row["block_id"],
            ))

            if len(results) >= limit:
                break

        return results

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有向量"""
        table = self._get_table()
        if table is None:
            return

        try:
            table.delete(f"reg_id = '{reg_id}'")
            logger.info(f"[LanceDB] 已删除规程 {reg_id} 的向量索引")
        except Exception as e:
            logger.warning(f"LanceDB 删除向量索引失败: {e}")

    def close(self) -> None:
        """关闭连接"""
        self._db = None
        self._table = None
