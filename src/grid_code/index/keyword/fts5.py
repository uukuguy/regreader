"""SQLite FTS5 关键词索引

实现基于 SQLite FTS5 的关键词检索。
支持块类型过滤和章节号精确匹配。
"""

import json
import re
import sqlite3
from pathlib import Path

from loguru import logger

from grid_code.config import get_settings
from grid_code.index.base import BaseKeywordIndex
from grid_code.storage.models import DocumentStructure, PageDocument, SearchResult

# 当前模式版本号（用于模式迁移）
SCHEMA_VERSION = 2


class FTS5Index(BaseKeywordIndex):
    """SQLite FTS5 全文索引

    支持：
    - 块类型过滤 (block_types)
    - 章节号精确匹配 (section_number)
    - 章节范围限定 (chapter_scope)
    """

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
    def name(self) -> str:
        return "FTS5"

    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """初始化数据库表（支持模式迁移）"""
        cursor = self.conn.cursor()

        # 检查模式版本
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)
        cursor.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        current_version = row[0] if row else 0

        if current_version < SCHEMA_VERSION:
            logger.info(f"升级 FTS5 模式: v{current_version} -> v{SCHEMA_VERSION}")
            # 删除旧表（FTS5 虚拟表无法修改列）
            cursor.execute("DROP TABLE IF EXISTS page_index")
            cursor.execute("DROP TABLE IF EXISTS page_meta")

        # 创建 FTS5 虚拟表（包含新字段）
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS page_index USING fts5(
                content,
                reg_id UNINDEXED,
                page_num UNINDEXED,
                chapter_path UNINDEXED,
                block_id UNINDEXED,
                block_type UNINDEXED,
                chapter_node_id UNINDEXED,
                section_number UNINDEXED,
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
                block_type TEXT,
                chapter_path TEXT,
                chapter_node_id TEXT,
                section_number TEXT,
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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_page_meta_block_type
            ON page_meta(reg_id, block_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_page_meta_section
            ON page_meta(reg_id, section_number)
        """)

        # 更新模式版本
        if current_version < SCHEMA_VERSION:
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

        self.conn.commit()
        logger.debug("FTS5 数据库初始化完成")

    def index_page(
        self,
        page: PageDocument,
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """索引单个页面

        Args:
            page: PageDocument 对象
            doc_structure: 文档结构（可选，用于获取 section_number）
        """
        cursor = self.conn.cursor()

        for block in page.content_blocks:
            content = block.content_markdown.strip()
            if not content:
                continue

            # 获取章节编号
            section_number = None
            if block.chapter_node_id and doc_structure:
                node = doc_structure.all_nodes.get(block.chapter_node_id)
                if node:
                    section_number = node.section_number

            # 使用块级章节路径，如果没有则使用页面级
            chapter_path = block.chapter_path if block.chapter_path else page.chapter_path
            chapter_path_json = json.dumps(chapter_path, ensure_ascii=False)

            cursor.execute("""
                INSERT INTO page_index
                (content, reg_id, page_num, chapter_path, block_id,
                 block_type, chapter_node_id, section_number)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                content,
                page.reg_id,
                page.page_num,
                chapter_path_json,
                block.block_id,
                block.block_type,
                block.chapter_node_id,
                section_number,
            ))

            preview = content[:200] if len(content) > 200 else content
            cursor.execute("""
                INSERT OR REPLACE INTO page_meta
                (reg_id, page_num, block_id, block_type, chapter_path,
                 chapter_node_id, section_number, content_preview)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                page.reg_id,
                page.page_num,
                block.block_id,
                block.block_type,
                chapter_path_json,
                block.chapter_node_id,
                section_number,
                preview,
            ))

        self.conn.commit()

    def index_pages(
        self,
        pages: list[PageDocument],
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """批量索引页面

        Args:
            pages: PageDocument 列表
            doc_structure: 文档结构（可选）
        """
        logger.info(f"[FTS5] 开始索引 {len(pages)} 页...")
        for page in pages:
            self.index_page(page, doc_structure)
        logger.info("[FTS5] 索引构建完成")

    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[SearchResult]:
        """全文搜索

        Args:
            query: 搜索查询
            reg_id: 限定规程（可选）
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制
            block_types: 限定块类型列表（可选）
            section_number: 精确匹配章节号（可选）

        Returns:
            SearchResult 列表
        """
        cursor = self.conn.cursor()

        sql = """
            SELECT
                page_index.content,
                page_index.reg_id,
                page_index.page_num,
                page_index.chapter_path,
                page_index.block_id,
                page_index.block_type,
                page_index.chapter_node_id,
                page_index.section_number,
                bm25(page_index) as score
            FROM page_index
            WHERE page_index MATCH ?
        """
        params: list = [self._prepare_query(query)]

        if reg_id:
            sql += " AND page_index.reg_id = ?"
            params.append(reg_id)

        if chapter_scope:
            sql += " AND page_index.chapter_path LIKE ?"
            params.append(f"%{chapter_scope}%")

        # 块类型过滤
        if block_types:
            placeholders = ','.join('?' for _ in block_types)
            sql += f" AND page_index.block_type IN ({placeholders})"
            params.extend(block_types)

        # 章节号精确匹配
        if section_number:
            sql += " AND page_index.section_number = ?"
            params.append(section_number)

        sql += " ORDER BY score LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 搜索错误: {e}")
            return []

        results = []
        for row in rows:
            chapter_path = json.loads(row["chapter_path"]) if row["chapter_path"] else []
            content = row["content"]
            snippet = self._extract_snippet(content, query)

            results.append(SearchResult(
                reg_id=row["reg_id"],
                page_num=row["page_num"],
                chapter_path=chapter_path,
                snippet=snippet,
                score=abs(row["score"]),
                block_id=row["block_id"],
            ))

        return results

    def _prepare_query(self, query: str) -> str:
        """准备 FTS5 查询字符串"""
        cleaned = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', query)
        terms = cleaned.split()
        if len(terms) > 1:
            return " OR ".join(terms)
        return cleaned

    def _extract_snippet(self, content: str, query: str, context_len: int = 100) -> str:
        """从内容中提取包含查询词的片段"""
        query_terms = query.split()
        content_lower = content.lower()

        match_pos = -1
        for term in query_terms:
            pos = content_lower.find(term.lower())
            if pos != -1:
                if match_pos == -1 or pos < match_pos:
                    match_pos = pos

        if match_pos == -1:
            return content[:context_len * 2] + ("..." if len(content) > context_len * 2 else "")

        start = max(0, match_pos - context_len)
        end = min(len(content), match_pos + context_len)

        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet

    def delete_regulation(self, reg_id: str) -> None:
        """删除规程的所有索引"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM page_index WHERE reg_id = ?", (reg_id,))
        cursor.execute("DELETE FROM page_meta WHERE reg_id = ?", (reg_id,))
        self.conn.commit()
        logger.info(f"[FTS5] 已删除规程 {reg_id} 的索引")

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
