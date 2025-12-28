"""SQLite FTS5 全文索引

实现基于 SQLite FTS5 的关键词检索。
"""

import json
import sqlite3
from pathlib import Path

from loguru import logger

from grid_code.config import get_settings
from grid_code.storage.models import PageDocument, SearchResult


class FTSIndex:
    """SQLite FTS5 全文索引"""

    def __init__(self, db_path: Path | None = None):
        """
        初始化 FTS 索引

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        settings = get_settings()
        self.db_path = db_path or settings.fts_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()

        # 创建 FTS5 虚拟表
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS page_index USING fts5(
                content,
                reg_id UNINDEXED,
                page_num UNINDEXED,
                chapter_path UNINDEXED,
                block_id UNINDEXED,
                tokenize='unicode61'
            )
        """)

        # 创建辅助表用于存储元数据
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS page_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reg_id TEXT NOT NULL,
                page_num INTEGER NOT NULL,
                block_id TEXT,
                chapter_path TEXT,
                content_preview TEXT,
                UNIQUE(reg_id, page_num, block_id)
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_page_meta_reg
            ON page_meta(reg_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_page_meta_page
            ON page_meta(reg_id, page_num)
        """)

        self.conn.commit()
        logger.debug("FTS5 数据库初始化完成")

    def index_page(self, page: PageDocument):
        """
        索引单个页面

        Args:
            page: PageDocument 对象
        """
        cursor = self.conn.cursor()
        chapter_path_json = json.dumps(page.chapter_path, ensure_ascii=False)

        # 索引每个内容块
        for block in page.content_blocks:
            content = block.content_markdown.strip()
            if not content:
                continue

            # 插入 FTS 索引
            cursor.execute("""
                INSERT INTO page_index (content, reg_id, page_num, chapter_path, block_id)
                VALUES (?, ?, ?, ?, ?)
            """, (content, page.reg_id, page.page_num, chapter_path_json, block.block_id))

            # 插入元数据
            preview = content[:200] if len(content) > 200 else content
            cursor.execute("""
                INSERT OR REPLACE INTO page_meta
                (reg_id, page_num, block_id, chapter_path, content_preview)
                VALUES (?, ?, ?, ?, ?)
            """, (page.reg_id, page.page_num, block.block_id, chapter_path_json, preview))

        self.conn.commit()

    def index_pages(self, pages: list[PageDocument]):
        """
        批量索引页面

        Args:
            pages: PageDocument 列表
        """
        logger.info(f"开始索引 {len(pages)} 页...")
        for page in pages:
            self.index_page(page)
        logger.info("FTS 索引构建完成")

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        全文搜索

        Args:
            query: 搜索查询
            reg_id: 限定规程（可选）
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制

        Returns:
            SearchResult 列表
        """
        cursor = self.conn.cursor()

        # 构建查询
        # FTS5 查询语法：使用 MATCH 进行全文匹配
        sql = """
            SELECT
                page_index.content,
                page_index.reg_id,
                page_index.page_num,
                page_index.chapter_path,
                page_index.block_id,
                bm25(page_index) as score
            FROM page_index
            WHERE page_index MATCH ?
        """
        params: list = [self._prepare_query(query)]

        if reg_id:
            sql += " AND page_index.reg_id = ?"
            params.append(reg_id)

        if chapter_scope:
            # 章节范围过滤（通过 chapter_path 包含指定章节）
            sql += " AND page_index.chapter_path LIKE ?"
            params.append(f"%{chapter_scope}%")

        sql += " ORDER BY score LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS 搜索错误: {e}")
            return []

        results = []
        for row in rows:
            chapter_path = json.loads(row["chapter_path"]) if row["chapter_path"] else []
            content = row["content"]

            # 提取匹配片段
            snippet = self._extract_snippet(content, query)

            results.append(SearchResult(
                reg_id=row["reg_id"],
                page_num=row["page_num"],
                chapter_path=chapter_path,
                snippet=snippet,
                score=abs(row["score"]),  # BM25 返回负分，取绝对值
                block_id=row["block_id"],
            ))

        return results

    def _prepare_query(self, query: str) -> str:
        """
        准备 FTS5 查询字符串

        Args:
            query: 原始查询

        Returns:
            FTS5 兼容的查询字符串
        """
        # 移除特殊字符，避免 FTS5 语法错误
        import re
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', query)
        # 将空格分隔的词用 OR 连接，提高召回率
        terms = cleaned.split()
        if len(terms) > 1:
            return " OR ".join(terms)
        return cleaned

    def _extract_snippet(self, content: str, query: str, context_len: int = 100) -> str:
        """
        从内容中提取包含查询词的片段

        Args:
            content: 完整内容
            query: 查询词
            context_len: 上下文长度

        Returns:
            匹配片段
        """
        query_terms = query.split()
        content_lower = content.lower()

        # 找到第一个匹配位置
        match_pos = -1
        for term in query_terms:
            pos = content_lower.find(term.lower())
            if pos != -1:
                if match_pos == -1 or pos < match_pos:
                    match_pos = pos

        if match_pos == -1:
            # 没找到匹配，返回开头部分
            return content[:context_len * 2] + ("..." if len(content) > context_len * 2 else "")

        # 提取上下文
        start = max(0, match_pos - context_len)
        end = min(len(content), match_pos + context_len)

        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def delete_regulation(self, reg_id: str):
        """
        删除规程的所有索引

        Args:
            reg_id: 规程标识
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM page_index WHERE reg_id = ?", (reg_id,))
        cursor.execute("DELETE FROM page_meta WHERE reg_id = ?", (reg_id,))
        self.conn.commit()
        logger.info(f"已删除规程 {reg_id} 的 FTS 索引")

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
