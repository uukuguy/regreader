"""Tantivy 关键词索引

实现基于 tantivy-py 的关键词检索。
https://github.com/quickwit-oss/tantivy-py
"""

import json
from pathlib import Path

from loguru import logger

from regreader.core.config import get_settings
from regreader.index.base import BaseKeywordIndex
from regreader.storage.models import PageDocument, SearchResult


class TantivyIndex(BaseKeywordIndex):
    """Tantivy 全文索引

    Tantivy 是 Rust 编写的高性能全文搜索引擎库。
    """

    def __init__(self, index_path: Path | None = None):
        """
        初始化 Tantivy 索引

        Args:
            index_path: 索引存储路径，默认使用配置中的路径
        """
        settings = get_settings()
        self.index_path = index_path or (settings.index_dir / "tantivy")
        self.index_path.mkdir(parents=True, exist_ok=True)

        self._index = None
        self._writer = None
        self._init_index()

    @property
    def name(self) -> str:
        return "Tantivy"

    def _init_index(self):
        """初始化 Tantivy 索引"""
        try:
            import tantivy
        except ImportError:
            logger.warning("tantivy-py 未安装，请运行: pip install tantivy")
            return

        # 定义 schema
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("content", stored=True, tokenizer_name="default")
        schema_builder.add_text_field("reg_id", stored=True)
        schema_builder.add_integer_field("page_num", stored=True)
        schema_builder.add_text_field("chapter_path", stored=True)
        schema_builder.add_text_field("block_id", stored=True)
        schema = schema_builder.build()

        # 创建或打开索引
        try:
            self._index = tantivy.Index(schema, path=str(self.index_path))
        except Exception:
            # 索引已存在，尝试打开
            self._index = tantivy.Index(schema, path=str(self.index_path), reuse=True)

        logger.debug("Tantivy 索引初始化完成")

    def _get_writer(self):
        """获取索引写入器"""
        if self._writer is None and self._index is not None:
            self._writer = self._index.writer()
        return self._writer

    def index_page(self, page: PageDocument) -> None:
        """索引单个页面"""
        if self._index is None:
            logger.warning("Tantivy 索引未初始化")
            return

        writer = self._get_writer()
        if writer is None:
            return

        chapter_path_json = json.dumps(page.chapter_path, ensure_ascii=False)

        for block in page.content_blocks:
            content = block.content_markdown.strip()
            if not content:
                continue

            writer.add_document({
                "content": content,
                "reg_id": page.reg_id,
                "page_num": page.page_num,
                "chapter_path": chapter_path_json,
                "block_id": block.block_id,
            })

        writer.commit()

    def index_pages(self, pages: list[PageDocument]) -> None:
        """批量索引页面"""
        if self._index is None:
            logger.warning("Tantivy 索引未初始化")
            return

        logger.info(f"[Tantivy] 开始索引 {len(pages)} 页...")

        writer = self._get_writer()
        if writer is None:
            return

        for page in pages:
            chapter_path_json = json.dumps(page.chapter_path, ensure_ascii=False)

            for block in page.content_blocks:
                content = block.content_markdown.strip()
                if not content:
                    continue

                writer.add_document({
                    "content": content,
                    "reg_id": page.reg_id,
                    "page_num": page.page_num,
                    "chapter_path": chapter_path_json,
                    "block_id": block.block_id,
                })

        writer.commit()
        logger.info("[Tantivy] 索引构建完成")

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """全文搜索"""
        if self._index is None:
            logger.warning("Tantivy 索引未初始化")
            return []

        try:
            import tantivy
        except ImportError:
            return []

        searcher = self._index.searcher()

        # 构建查询
        query_parser = tantivy.QueryParser.for_index(self._index, ["content"])

        # 如果指定了 reg_id，添加过滤条件
        if reg_id:
            query_str = f"({query}) AND reg_id:{reg_id}"
        else:
            query_str = query

        try:
            parsed_query = query_parser.parse_query(query_str)
        except Exception as e:
            logger.warning(f"Tantivy 查询解析错误: {e}")
            # 回退到简单查询
            parsed_query = query_parser.parse_query(query)

        # 执行搜索
        try:
            search_result = searcher.search(parsed_query, limit)
        except Exception as e:
            logger.warning(f"Tantivy 搜索错误: {e}")
            return []

        results = []
        for score, doc_address in search_result.hits:
            doc = searcher.doc(doc_address)

            doc_reg_id = doc.get_first("reg_id")
            doc_chapter_path = doc.get_first("chapter_path")

            # 应用章节过滤
            if chapter_scope and chapter_scope not in (doc_chapter_path or ""):
                continue

            chapter_path = json.loads(doc_chapter_path) if doc_chapter_path else []
            content = doc.get_first("content") or ""

            results.append(SearchResult(
                reg_id=doc_reg_id or "",
                page_num=doc.get_first("page_num") or 0,
                chapter_path=chapter_path,
                snippet=content[:200] + ("..." if len(content) > 200 else ""),
                score=score,
                block_id=doc.get_first("block_id"),
            ))

        return results

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有索引"""
        if self._index is None:
            return

        writer = self._get_writer()
        if writer is None:
            return

        try:
            import tantivy
            # 使用术语查询删除
            query_parser = tantivy.QueryParser.for_index(self._index, ["reg_id"])
            delete_query = query_parser.parse_query(f"reg_id:{reg_id}")
            writer.delete_documents(delete_query)
            writer.commit()
            logger.info(f"[Tantivy] 已删除规程 {reg_id} 的索引")
        except Exception as e:
            logger.warning(f"Tantivy 删除失败: {e}")

    def close(self) -> None:
        """关闭索引"""
        if self._writer:
            try:
                self._writer.commit()
            except Exception:
                pass
            self._writer = None
        self._index = None
