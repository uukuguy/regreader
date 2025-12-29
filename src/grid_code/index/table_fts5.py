"""表格专用 FTS5 关键词索引

按完整表格（TableEntry）索引，支持：
- merged_markdown 全文搜索
- caption 标题搜索
- chapter_path 章节过滤
- col_headers 列标题搜索
"""

import json
import re
import sqlite3
from pathlib import Path

from loguru import logger

from grid_code.config import get_settings
from grid_code.storage.models import TableEntry, TableRegistry, TableSearchResult

# 当前模式版本号
SCHEMA_VERSION = 1


class TableFTS5Index:
    """表格专用 FTS5 全文索引

    索引 TableEntry 的以下字段：
    - merged_markdown: 合并后的完整表格 Markdown
    - caption: 表格标题
    - col_headers_text: 列标题文本
    - chapter_path_text: 章节路径文本
    """

    def __init__(self, db_path: Path | None = None):
        """
        初始化表格 FTS5 索引

        Args:
            db_path: 数据库文件路径，默认使用配置中的路径
        """
        settings = get_settings()
        self.db_path = db_path or settings.index_dir / "tables.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def name(self) -> str:
        return "TableFTS5"

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
            logger.info(f"升级 TableFTS5 模式: v{current_version} -> v{SCHEMA_VERSION}")
            cursor.execute("DROP TABLE IF EXISTS table_index")
            cursor.execute("DROP TABLE IF EXISTS table_meta")

        # 创建 FTS5 虚拟表
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS table_index USING fts5(
                merged_markdown,
                caption,
                col_headers_text,
                chapter_path_text,
                reg_id UNINDEXED,
                table_id UNINDEXED,
                tokenize='unicode61'
            )
        """)

        # 创建元数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_meta (
                table_id TEXT PRIMARY KEY,
                reg_id TEXT NOT NULL,
                caption TEXT,
                chapter_path_json TEXT,
                page_start INTEGER,
                page_end INTEGER,
                is_cross_page INTEGER,
                row_count INTEGER,
                col_count INTEGER,
                col_headers_json TEXT,
                merged_markdown TEXT,
                created_at TEXT
            )
        """)

        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_table_meta_reg
            ON table_meta(reg_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_table_meta_page
            ON table_meta(reg_id, page_start, page_end)
        """)

        # 更新模式版本
        if current_version < SCHEMA_VERSION:
            cursor.execute("DELETE FROM schema_version")
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))

        self.conn.commit()
        logger.debug("TableFTS5 数据库初始化完成")

    def index_table(self, entry: TableEntry, reg_id: str) -> None:
        """索引单个表格

        Args:
            entry: TableEntry 对象
            reg_id: 规程标识
        """
        cursor = self.conn.cursor()

        # 准备搜索文本
        caption = entry.caption or ""
        col_headers_text = " ".join(entry.col_headers)
        chapter_path_text = " ".join(entry.chapter_path)
        merged_markdown = entry.merged_markdown

        # 插入 FTS5 虚拟表
        cursor.execute("""
            INSERT INTO table_index
            (merged_markdown, caption, col_headers_text, chapter_path_text, reg_id, table_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            merged_markdown,
            caption,
            col_headers_text,
            chapter_path_text,
            reg_id,
            entry.table_id,
        ))

        # 插入元数据表
        cursor.execute("""
            INSERT OR REPLACE INTO table_meta
            (table_id, reg_id, caption, chapter_path_json, page_start, page_end,
             is_cross_page, row_count, col_count, col_headers_json, merged_markdown, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.table_id,
            reg_id,
            caption,
            json.dumps(entry.chapter_path, ensure_ascii=False),
            entry.page_start,
            entry.page_end,
            1 if entry.is_cross_page else 0,
            entry.row_count,
            entry.col_count,
            json.dumps(entry.col_headers, ensure_ascii=False),
            merged_markdown,
            entry.created_at,
        ))

        self.conn.commit()

    def index_registry(self, registry: TableRegistry) -> int:
        """索引整个表格注册表

        Args:
            registry: TableRegistry 对象

        Returns:
            索引的表格数量
        """
        count = 0
        for table_id, entry in registry.tables.items():
            self.index_table(entry, registry.reg_id)
            count += 1

        logger.info(f"[TableFTS5] 已索引 {count} 个表格 (reg_id={registry.reg_id})")
        return count

    def search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[TableSearchResult]:
        """搜索表格

        Args:
            query: 搜索查询
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选）
            limit: 返回结果数量限制

        Returns:
            TableSearchResult 列表
        """
        cursor = self.conn.cursor()

        sql = """
            SELECT
                table_index.merged_markdown,
                table_index.caption,
                table_index.table_id,
                table_meta.chapter_path_json,
                table_meta.page_start,
                table_meta.page_end,
                table_meta.is_cross_page,
                table_meta.row_count,
                table_meta.col_count,
                table_meta.col_headers_json,
                bm25(table_index) as score
            FROM table_index
            JOIN table_meta ON table_index.table_id = table_meta.table_id
            WHERE table_index MATCH ?
              AND table_index.reg_id = ?
        """
        params: list = [self._prepare_query(query), reg_id]

        if chapter_scope:
            sql += " AND table_index.chapter_path_text LIKE ?"
            params.append(f"%{chapter_scope}%")

        sql += " ORDER BY score LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            logger.warning(f"TableFTS5 搜索错误: {e}")
            return []

        results = []
        for row in rows:
            chapter_path = json.loads(row["chapter_path_json"]) if row["chapter_path_json"] else []
            col_headers = json.loads(row["col_headers_json"]) if row["col_headers_json"] else []
            content = row["merged_markdown"]
            caption = row["caption"] or ""

            # 确定匹配类型
            query_lower = query.lower()
            caption_match = query_lower in caption.lower()
            content_match = query_lower in content.lower()

            if caption_match and content_match:
                match_type = "both"
            elif caption_match:
                match_type = "caption"
            else:
                match_type = "content"

            snippet = self._extract_snippet(content, query)

            results.append(TableSearchResult(
                table_id=row["table_id"],
                caption=row["caption"],
                reg_id=reg_id,
                page_start=row["page_start"],
                page_end=row["page_end"],
                chapter_path=chapter_path,
                is_cross_page=bool(row["is_cross_page"]),
                row_count=row["row_count"],
                col_count=row["col_count"],
                col_headers=col_headers,
                snippet=snippet,
                score=abs(row["score"]),
                match_type=match_type,
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
        """删除规程的所有表格索引

        Args:
            reg_id: 规程标识
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM table_index WHERE reg_id = ?", (reg_id,))
        cursor.execute("DELETE FROM table_meta WHERE reg_id = ?", (reg_id,))
        self.conn.commit()
        logger.info(f"[TableFTS5] 已删除规程 {reg_id} 的表格索引")

    def get_table_count(self, reg_id: str) -> int:
        """获取规程的表格索引数量

        Args:
            reg_id: 规程标识

        Returns:
            索引的表格数量
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM table_meta WHERE reg_id = ?", (reg_id,))
        row = cursor.fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
