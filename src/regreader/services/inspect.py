"""页面数据检查服务

对比 FTS5 索引、LanceDB 向量索引和原始 PageDocument 的数据，
用于调试和验证索引的正确性。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import lancedb
from loguru import logger
from pydantic import BaseModel, Field

from regreader.config import get_settings
from regreader.storage import PageStore
from regreader.storage.models import PageDocument


class FTS5Record(BaseModel):
    """FTS5 索引记录"""

    content: str = Field(description="索引的完整内容")
    reg_id: str = Field(description="规程标识")
    page_num: int = Field(description="页码")
    block_id: str = Field(description="内容块ID")
    chapter_path: list[str] = Field(description="章节路径")
    content_preview: str = Field(description="内容预览（前200字符）")


class VectorRecord(BaseModel):
    """向量索引记录"""

    vector: list[float] = Field(default_factory=list, description="句向量（可选显示）")
    reg_id: str = Field(description="规程标识")
    page_num: int = Field(description="页码")
    block_id: str = Field(description="内容块ID")
    content: str = Field(description="内容（前500字符）")
    chapter_path: str = Field(description="章节路径（用 '>' 连接）")


class InspectResult(BaseModel):
    """检查结果"""

    reg_id: str = Field(description="规程标识")
    page_num: int = Field(description="页码")
    fts5_records: list[FTS5Record] = Field(description="FTS5 索引记录列表")
    vector_records: list[VectorRecord] = Field(description="向量索引记录列表")
    page_document: PageDocument = Field(description="原始页面文档")
    timestamp: str = Field(description="检查时间戳")


class DifferenceAnalysis(BaseModel):
    """差异分析结果"""

    missing_in_fts5: list[str] = Field(description="FTS5 中缺失的 block_id")
    missing_in_vector: list[str] = Field(description="向量索引中缺失的 block_id")
    content_mismatches: list[dict] = Field(description="内容不匹配的记录")
    total_blocks: int = Field(description="总内容块数")
    indexed_in_fts5: int = Field(description="FTS5 索引数")
    indexed_in_vector: int = Field(description="向量索引数")


class InspectService:
    """页面数据检查服务"""

    def __init__(self):
        """初始化检查服务"""
        settings = get_settings()
        self.page_store = PageStore()
        self.fts_db_path = settings.fts_db_path
        self.lancedb_path = settings.lancedb_path

    def inspect_page(
        self, reg_id: str, page_num: int, show_vectors: bool = False
    ) -> tuple[InspectResult, DifferenceAnalysis]:
        """检查指定页面的数据

        Args:
            reg_id: 规程标识
            page_num: 页码
            show_vectors: 是否在结果中包含向量数据

        Returns:
            (检查结果, 差异分析)

        Raises:
            RegulationNotFoundError: 规程不存在
            PageNotFoundError: 页面不存在
        """
        logger.info(f"检查页面数据: {reg_id} P{page_num}")

        # 1. 获取原始页面文档
        page_document = self.page_store.load_page(reg_id, page_num)

        # 2. 获取 FTS5 索引数据
        fts5_records = self._get_fts5_data(reg_id, page_num)

        # 3. 获取 LanceDB 向量数据
        vector_records = self._get_lancedb_data(reg_id, page_num, show_vectors)

        # 4. 创建检查结果
        result = InspectResult(
            reg_id=reg_id,
            page_num=page_num,
            fts5_records=fts5_records,
            vector_records=vector_records,
            page_document=page_document,
            timestamp=datetime.now().isoformat(),
        )

        # 5. 分析差异
        analysis = self._analyze_differences(result)

        logger.info(
            f"检查完成: FTS5={len(fts5_records)}, Vector={len(vector_records)}, "
            f"Page={len(page_document.content_blocks)}"
        )

        return result, analysis

    def _get_fts5_data(self, reg_id: str, page_num: int) -> list[FTS5Record]:
        """从 FTS5 索引获取数据

        Args:
            reg_id: 规程标识
            page_num: 页码

        Returns:
            FTS5 索引记录列表
        """
        if not self.fts_db_path.exists():
            logger.warning(f"FTS5 数据库不存在: {self.fts_db_path}")
            return []

        conn = sqlite3.connect(str(self.fts_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 使用 block_id 关联 page_meta 和 page_index 表
            # 修复：不使用 rowid，改用 block_id 进行 JOIN
            cursor.execute(
                """
                SELECT
                    m.block_id,
                    m.reg_id,
                    m.page_num,
                    m.block_type,
                    m.chapter_path,
                    m.content_preview,
                    i.content
                FROM page_meta m
                LEFT JOIN page_index i ON m.block_id = i.block_id
                WHERE m.reg_id = ? AND m.page_num = ?
            """,
                (reg_id, page_num),
            )

            records = []
            for row in cursor.fetchall():
                chapter_path = json.loads(row["chapter_path"]) if row["chapter_path"] else []
                content = row["content"] or ""

                records.append(
                    FTS5Record(
                        content=content,
                        reg_id=row["reg_id"],
                        page_num=row["page_num"],
                        block_id=row["block_id"],
                        chapter_path=chapter_path,
                        content_preview=row["content_preview"] or "",
                    )
                )

            return records

        finally:
            conn.close()

    def _get_lancedb_data(
        self, reg_id: str, page_num: int, show_vectors: bool = False
    ) -> list[VectorRecord]:
        """从 LanceDB 索引获取数据

        Args:
            reg_id: 规程标识
            page_num: 页码
            show_vectors: 是否包含向量数据

        Returns:
            向量索引记录列表
        """
        if not self.lancedb_path.exists():
            logger.warning(f"LanceDB 数据库不存在: {self.lancedb_path}")
            return []

        try:
            db = lancedb.connect(str(self.lancedb_path))
            table = db.open_table("page_vectors")
        except Exception as e:
            logger.warning(f"无法打开向量表: {e}")
            return []

        try:
            # 查询指定页面的向量记录 - 使用 to_pandas() + filter
            results = table.to_pandas()

            # 过滤指定页面的数据
            results = results[
                (results["reg_id"] == reg_id) & (results["page_num"] == page_num)
            ]

            records = []
            for _, row in results.iterrows():
                vector = row["vector"].tolist() if show_vectors else []
                records.append(
                    VectorRecord(
                        vector=vector,
                        reg_id=row["reg_id"],
                        page_num=row["page_num"],
                        block_id=row["block_id"],
                        content=row["content"],
                        chapter_path=row["chapter_path"],
                    )
                )

            return records

        except Exception as e:
            logger.error(f"查询向量数据失败: {e}")
            return []

    def _analyze_differences(self, result: InspectResult) -> DifferenceAnalysis:
        """分析三种数据源的差异

        Args:
            result: 检查结果

        Returns:
            差异分析结果
        """
        # 1. 提取所有 block_id
        page_block_ids = {block.block_id for block in result.page_document.content_blocks}
        fts5_block_ids = {rec.block_id for rec in result.fts5_records}
        vector_block_ids = {rec.block_id for rec in result.vector_records}

        # 2. 检查缺失
        missing_in_fts5 = list(page_block_ids - fts5_block_ids)
        missing_in_vector = list(page_block_ids - vector_block_ids)

        # 3. 内容一致性检查
        content_mismatches = []
        for block in result.page_document.content_blocks:
            block_id = block.block_id
            page_content = block.content_markdown.strip()

            # FTS5 内容
            fts5_match = next(
                (r for r in result.fts5_records if r.block_id == block_id), None
            )
            fts5_content = fts5_match.content.strip() if fts5_match else None

            # 向量内容
            vector_match = next(
                (r for r in result.vector_records if r.block_id == block_id), None
            )
            vector_content = vector_match.content.strip() if vector_match else None

            # 对比 FTS5
            if fts5_content and fts5_content != page_content:
                content_mismatches.append(
                    {
                        "block_id": block_id,
                        "source": "FTS5",
                        "page_content": page_content[:100],
                        "indexed_content": fts5_content[:100],
                    }
                )

            # 对比向量（注意向量索引截断到 500 字符）
            if vector_content:
                expected_content = page_content[:500]
                if vector_content != expected_content:
                    # 只在完整内容小于 500 时才算不匹配
                    if len(page_content) <= 500:
                        content_mismatches.append(
                            {
                                "block_id": block_id,
                                "source": "LanceDB",
                                "page_content": page_content[:100],
                                "indexed_content": vector_content[:100],
                            }
                        )

        return DifferenceAnalysis(
            missing_in_fts5=missing_in_fts5,
            missing_in_vector=missing_in_vector,
            content_mismatches=content_mismatches,
            total_blocks=len(page_block_ids),
            indexed_in_fts5=len(fts5_block_ids),
            indexed_in_vector=len(vector_block_ids),
        )

    def save_json(
        self,
        result: InspectResult,
        analysis: DifferenceAnalysis,
        output_path: Path | None = None,
    ) -> Path:
        """保存检查结果为 JSON 文件

        Args:
            result: 检查结果
            analysis: 差异分析
            output_path: 输出文件路径（可选）

        Returns:
            实际保存的文件路径
        """
        if output_path is None:
            # 生成默认文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"inspect_{result.reg_id}_p{result.page_num}_{timestamp}.json"
            output_path = Path(filename)

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 序列化数据
        data = {
            "inspect_result": result.model_dump(),
            "difference_analysis": analysis.model_dump(),
        }

        # 保存 JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"检查结果已保存至: {output_path}")
        return output_path
