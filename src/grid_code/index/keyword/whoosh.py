"""Whoosh 关键词索引

实现基于 Whoosh 的关键词检索。
https://github.com/mchaput/whoosh
"""

import json
from pathlib import Path

from loguru import logger

from grid_code.config import get_settings
from grid_code.index.base import BaseKeywordIndex
from grid_code.storage.models import PageDocument, SearchResult


class WhooshIndex(BaseKeywordIndex):
    """Whoosh 全文索引

    Whoosh 是纯 Python 实现的全文搜索库。
    """

    def __init__(self, index_path: Path | None = None):
        """
        初始化 Whoosh 索引

        Args:
            index_path: 索引存储路径，默认使用配置中的路径
        """
        settings = get_settings()
        self.index_path = index_path or (settings.index_dir / "whoosh")
        self.index_path.mkdir(parents=True, exist_ok=True)

        self._index = None
        self._schema = None
        self._init_index()

    @property
    def name(self) -> str:
        return "Whoosh"

    def _init_index(self):
        """初始化 Whoosh 索引"""
        try:
            from whoosh import index
            from whoosh.analysis import ChineseAnalyzer
            from whoosh.fields import ID, NUMERIC, TEXT, Schema
        except ImportError:
            logger.warning("Whoosh 未安装，请运行: pip install whoosh")
            return

        # 使用中文分析器
        analyzer = ChineseAnalyzer()

        # 定义 schema
        self._schema = Schema(
            content=TEXT(stored=True, analyzer=analyzer),
            reg_id=ID(stored=True),
            page_num=NUMERIC(stored=True),
            chapter_path=TEXT(stored=True),
            block_id=ID(stored=True),
        )

        # 创建或打开索引
        if index.exists_in(str(self.index_path)):
            self._index = index.open_dir(str(self.index_path))
        else:
            self._index = index.create_in(str(self.index_path), self._schema)

        logger.debug("Whoosh 索引初始化完成")

    def index_page(self, page: PageDocument) -> None:
        """索引单个页面"""
        if self._index is None:
            logger.warning("Whoosh 索引未初始化")
            return

        writer = self._index.writer()
        chapter_path_json = json.dumps(page.chapter_path, ensure_ascii=False)

        try:
            for block in page.content_blocks:
                content = block.content_markdown.strip()
                if not content:
                    continue

                writer.add_document(
                    content=content,
                    reg_id=page.reg_id,
                    page_num=page.page_num,
                    chapter_path=chapter_path_json,
                    block_id=block.block_id,
                )
            writer.commit()
        except Exception as e:
            logger.warning(f"Whoosh 索引写入错误: {e}")
            writer.cancel()

    def index_pages(self, pages: list[PageDocument]) -> None:
        """批量索引页面"""
        if self._index is None:
            logger.warning("Whoosh 索引未初始化")
            return

        logger.info(f"[Whoosh] 开始索引 {len(pages)} 页...")

        writer = self._index.writer()

        try:
            for page in pages:
                chapter_path_json = json.dumps(page.chapter_path, ensure_ascii=False)

                for block in page.content_blocks:
                    content = block.content_markdown.strip()
                    if not content:
                        continue

                    writer.add_document(
                        content=content,
                        reg_id=page.reg_id,
                        page_num=page.page_num,
                        chapter_path=chapter_path_json,
                        block_id=block.block_id,
                    )

            writer.commit()
            logger.info("[Whoosh] 索引构建完成")
        except Exception as e:
            logger.warning(f"Whoosh 批量索引错误: {e}")
            writer.cancel()

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """全文搜索"""
        if self._index is None:
            logger.warning("Whoosh 索引未初始化")
            return []

        try:
            from whoosh.qparser import MultifieldParser, QueryParser
            from whoosh.query import And, Term
        except ImportError:
            return []

        with self._index.searcher() as searcher:
            # 构建查询
            parser = QueryParser("content", self._index.schema)

            try:
                parsed_query = parser.parse(query)
            except Exception as e:
                logger.warning(f"Whoosh 查询解析错误: {e}")
                return []

            # 添加过滤条件
            if reg_id:
                reg_filter = Term("reg_id", reg_id)
                parsed_query = And([parsed_query, reg_filter])

            # 执行搜索
            try:
                search_results = searcher.search(parsed_query, limit=limit * 2)
            except Exception as e:
                logger.warning(f"Whoosh 搜索错误: {e}")
                return []

            results = []
            for hit in search_results:
                doc_chapter_path = hit.get("chapter_path", "")

                # 应用章节过滤
                if chapter_scope and chapter_scope not in doc_chapter_path:
                    continue

                chapter_path = json.loads(doc_chapter_path) if doc_chapter_path else []
                content = hit.get("content", "")

                results.append(SearchResult(
                    reg_id=hit.get("reg_id", ""),
                    page_num=hit.get("page_num", 0),
                    chapter_path=chapter_path,
                    snippet=content[:200] + ("..." if len(content) > 200 else ""),
                    score=hit.score,
                    block_id=hit.get("block_id"),
                ))

                if len(results) >= limit:
                    break

            return results

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有索引"""
        if self._index is None:
            return

        try:
            from whoosh.query import Term
        except ImportError:
            return

        writer = self._index.writer()
        try:
            writer.delete_by_term("reg_id", reg_id)
            writer.commit()
            logger.info(f"[Whoosh] 已删除规程 {reg_id} 的索引")
        except Exception as e:
            logger.warning(f"Whoosh 删除失败: {e}")
            writer.cancel()

    def close(self) -> None:
        """关闭索引"""
        if self._index:
            self._index.close()
            self._index = None
