"""表格专用 LanceDB 向量索引

按完整表格（TableEntry）进行语义嵌入，支持：
- 标题 + 章节 + 内容组合嵌入
- 语义相似度搜索
"""

from pathlib import Path
from typing import TYPE_CHECKING

import lancedb
from loguru import logger

from regreader.config import get_settings
from regreader.storage.models import TableEntry, TableRegistry, TableSearchResult

if TYPE_CHECKING:
    from regreader.embedding import BaseEmbedder


class TableLanceDBIndex:
    """表格专用 LanceDB 向量索引

    对 TableEntry 的以下信息进行语义嵌入：
    - caption: 表格标题
    - chapter_path: 章节路径
    - col_headers: 列标题
    - merged_markdown: 合并后的表格内容（截断）
    """

    TABLE_NAME = "table_vectors"

    def __init__(
        self,
        db_path: Path | None = None,
        embedder: "BaseEmbedder | None" = None,
    ):
        """初始化表格向量索引

        Args:
            db_path: LanceDB 数据库路径，默认使用配置中的路径
            embedder: 嵌入模型实例（可选，默认使用全局单例）
        """
        settings = get_settings()
        self.db_path = db_path or settings.index_dir / "table_vectors"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db: lancedb.DBConnection | None = None
        self._table: lancedb.table.Table | None = None
        self._embedder = embedder

    @property
    def name(self) -> str:
        return "TableLanceDB"

    @property
    def embedding_dimension(self) -> int:
        return self.embedder.dimension

    @property
    def db(self) -> lancedb.DBConnection:
        """获取数据库连接"""
        if self._db is None:
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    @property
    def embedder(self) -> "BaseEmbedder":
        """获取嵌入模型（延迟初始化）"""
        if self._embedder is None:
            from regreader.embedding import get_embedder

            self._embedder = get_embedder()
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

    def _build_embed_text(self, entry: TableEntry) -> str:
        """构建用于嵌入的文本

        组合标题、章节、列标题和内容，提升语义理解效果。

        Args:
            entry: TableEntry 对象

        Returns:
            用于嵌入的组合文本
        """
        parts = []

        # 添加标题
        if entry.caption:
            parts.append(f"表格标题: {entry.caption}")

        # 添加章节路径
        if entry.chapter_path:
            parts.append(f"所属章节: {' > '.join(entry.chapter_path)}")

        # 添加列标题
        if entry.col_headers:
            parts.append(f"列: {', '.join(entry.col_headers)}")

        # 添加表格内容（限制长度以避免嵌入模型截断）
        content = entry.merged_markdown
        max_content_len = 2000
        if len(content) > max_content_len:
            content = content[:max_content_len] + "..."
        parts.append(content)

        return "\n".join(parts)

    def index_table(self, entry: TableEntry, reg_id: str) -> None:
        """索引单个表格

        Args:
            entry: TableEntry 对象
            reg_id: 规程标识
        """
        embed_text = self._build_embed_text(entry)
        vector = self.embedder.embed_document(embed_text)

        record = {
            "vector": vector,
            "table_id": entry.table_id,
            "reg_id": reg_id,
            "caption": entry.caption or "",
            "chapter_path": " > ".join(entry.chapter_path),
            "page_start": entry.page_start,
            "page_end": entry.page_end,
            "is_cross_page": entry.is_cross_page,
            "row_count": entry.row_count,
            "col_count": entry.col_count,
            "col_headers": ", ".join(entry.col_headers),
            "content_preview": entry.merged_markdown[:500],
        }

        table = self._get_table()
        if table is None:
            self._create_table([record])
        else:
            table.add([record])

    def index_registry(self, registry: TableRegistry) -> int:
        """批量索引表格注册表

        Args:
            registry: TableRegistry 对象

        Returns:
            索引的表格数量
        """
        logger.info(f"[TableLanceDB] 开始索引 {len(registry.tables)} 个表格...")

        all_records = []
        all_texts = []
        entries_list = list(registry.tables.values())

        # 收集所有需要嵌入的文本
        for entry in entries_list:
            embed_text = self._build_embed_text(entry)
            all_texts.append(embed_text)

        if not all_texts:
            logger.warning("没有可索引的表格")
            return 0

        # 批量生成嵌入向量
        logger.info(f"生成 {len(all_texts)} 个表格嵌入向量...")
        all_vectors = self.embedder.embed_documents(all_texts)

        # 构建记录
        for i, entry in enumerate(entries_list):
            all_records.append({
                "vector": all_vectors[i],
                "table_id": entry.table_id,
                "reg_id": registry.reg_id,
                "caption": entry.caption or "",
                "chapter_path": " > ".join(entry.chapter_path),
                "page_start": entry.page_start,
                "page_end": entry.page_end,
                "is_cross_page": entry.is_cross_page,
                "row_count": entry.row_count,
                "col_count": entry.col_count,
                "col_headers": ", ".join(entry.col_headers),
                "content_preview": entry.merged_markdown[:500],
            })

        # 写入索引
        table = self._get_table()
        if table is None:
            self._create_table(all_records)
        else:
            table.add(all_records)

        logger.info(f"[TableLanceDB] 已索引 {len(all_records)} 个表格")
        return len(all_records)

    def search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[TableSearchResult]:
        """语义搜索表格

        Args:
            query: 搜索查询
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制

        Returns:
            TableSearchResult 列表
        """
        table = self._get_table()
        if table is None:
            logger.warning("表格向量索引表不存在")
            return []

        query_vector = self.embedder.embed_query(query)
        search_query = table.search(query_vector).limit(limit * 2)

        try:
            results_df = search_query.to_pandas()
        except Exception as e:
            logger.warning(f"TableLanceDB 搜索错误: {e}")
            return []

        if results_df.empty:
            return []

        results = []
        for _, row in results_df.iterrows():
            # 规程过滤
            if row["reg_id"] != reg_id:
                continue

            # 章节范围过滤
            if chapter_scope and chapter_scope not in row["chapter_path"]:
                continue

            chapter_path = row["chapter_path"].split(" > ") if row["chapter_path"] else []
            col_headers = row["col_headers"].split(", ") if row["col_headers"] else []

            # 确定匹配类型
            query_lower = query.lower()
            caption = row["caption"] or ""
            content = row["content_preview"]

            caption_match = query_lower in caption.lower()
            content_match = query_lower in content.lower()

            if caption_match and content_match:
                match_type = "both"
            elif caption_match:
                match_type = "caption"
            else:
                match_type = "content"

            results.append(TableSearchResult(
                table_id=row["table_id"],
                caption=row["caption"] if row["caption"] else None,
                reg_id=reg_id,
                page_start=int(row["page_start"]),
                page_end=int(row["page_end"]),
                chapter_path=chapter_path,
                is_cross_page=bool(row["is_cross_page"]),
                row_count=int(row["row_count"]),
                col_count=int(row["col_count"]),
                col_headers=col_headers,
                snippet=row["content_preview"],
                score=1 - row["_distance"],
                match_type=match_type,
            ))

            if len(results) >= limit:
                break

        return results

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有表格向量

        Args:
            reg_id: 规程标识
        """
        table = self._get_table()
        if table is None:
            return

        try:
            table.delete(f"reg_id = '{reg_id}'")
            logger.info(f"[TableLanceDB] 已删除规程 {reg_id} 的表格向量索引")
        except Exception as e:
            logger.warning(f"TableLanceDB 删除向量索引失败: {e}")

    def get_table_count(self, reg_id: str) -> int:
        """获取规程的表格向量数量

        Args:
            reg_id: 规程标识

        Returns:
            索引的表格数量
        """
        table = self._get_table()
        if table is None:
            return 0

        try:
            results_df = table.search([0.0] * self.embedding_dimension).limit(10000).to_pandas()
            return len(results_df[results_df["reg_id"] == reg_id])
        except Exception:
            return 0

    def close(self) -> None:
        """关闭连接"""
        self._db = None
        self._table = None
