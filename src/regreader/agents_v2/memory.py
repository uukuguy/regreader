"""RegReader Agent 记忆系统

扩展 agentex 的 AgentMemory，添加 RegReader 特定功能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..agentex.shared.memory import AgentMemory, MemoryItem


@dataclass
class ContentChunk:
    """内容块

    存储检索到的内容片段及其元数据。
    """

    content: str
    """内容文本"""

    source: str
    """来源标识 (reg_id:page_num)"""

    relevance_score: float = 0.0
    """相关性分数"""

    chunk_type: str = "text"
    """块类型: text, table, heading, list"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """额外元数据"""


class RegReaderMemory:
    """RegReader 扩展记忆系统

    在 agentex.AgentMemory 基础上添加:
    - TOC 缓存（避免重复调用 get_toc）
    - 已知章节跟踪
    - 相关内容块存储（按相关性排序）
    """

    def __init__(
        self,
        base_memory: AgentMemory | None = None,
        max_chunks: int = 20,
    ):
        """初始化记忆系统

        Args:
            base_memory: 底层 agentex 记忆（可选）
            max_chunks: 最大内容块数量
        """
        self._base = base_memory or AgentMemory()
        self._max_chunks = max_chunks

        # RegReader 特定存储
        self._toc_cache: dict[str, dict] = {}
        self._known_chapters: dict[str, set[str]] = {}  # reg_id -> set of chapter numbers
        self._relevant_chunks: list[ContentChunk] = []

    # ========== 委托给基础记忆 ==========

    def add(self, role: str, content: str, metadata: dict[str, Any] | None = None):
        """添加消息到历史"""
        self._base.add(role, content, metadata)

    def get_messages(self) -> list[dict[str, Any]]:
        """获取消息历史"""
        return self._base.get_messages()

    def get_history(self) -> list[MemoryItem]:
        """获取历史记录"""
        return self._base.get_history()

    def clear(self):
        """清空所有记忆"""
        self._base.clear()
        self._toc_cache.clear()
        self._known_chapters.clear()
        self._relevant_chunks.clear()

    def __len__(self) -> int:
        return len(self._base)

    def __bool__(self) -> bool:
        return bool(self._base)

    # ========== TOC 缓存 ==========

    def cache_toc(self, reg_id: str, toc: dict) -> None:
        """缓存 TOC

        Args:
            reg_id: 规程标识
            toc: TOC 数据
        """
        self._toc_cache[reg_id] = toc

    def get_cached_toc(self, reg_id: str) -> dict | None:
        """获取缓存的 TOC

        Args:
            reg_id: 规程标识

        Returns:
            TOC 数据，不存在返回 None
        """
        return self._toc_cache.get(reg_id)

    def has_cached_toc(self, reg_id: str) -> bool:
        """检查是否有缓存的 TOC"""
        return reg_id in self._toc_cache

    # ========== 已知章节跟踪 ==========

    def add_known_chapter(self, reg_id: str, chapter_number: str) -> None:
        """添加已知章节

        Args:
            reg_id: 规程标识
            chapter_number: 章节编号
        """
        if reg_id not in self._known_chapters:
            self._known_chapters[reg_id] = set()
        self._known_chapters[reg_id].add(chapter_number)

    def get_known_chapters(self, reg_id: str) -> set[str]:
        """获取已知章节列表"""
        return self._known_chapters.get(reg_id, set())

    def is_chapter_known(self, reg_id: str, chapter_number: str) -> bool:
        """检查章节是否已知"""
        return chapter_number in self._known_chapters.get(reg_id, set())

    # ========== 相关内容块 ==========

    def add_chunk(self, chunk: ContentChunk) -> None:
        """添加内容块

        按相关性分数排序存储，超出限制时移除最低分数的块。

        Args:
            chunk: 内容块
        """
        self._relevant_chunks.append(chunk)
        # 按相关性排序（降序）
        self._relevant_chunks.sort(key=lambda c: c.relevance_score, reverse=True)
        # 限制数量
        if len(self._relevant_chunks) > self._max_chunks:
            self._relevant_chunks = self._relevant_chunks[: self._max_chunks]

    def add_search_results(self, results: list[dict], reg_id: str | None = None) -> None:
        """从搜索结果添加内容块

        Args:
            results: 搜索结果列表
            reg_id: 规程标识（用于构建 source）
        """
        for result in results:
            source = result.get("source", "")
            if not source and reg_id:
                page = result.get("page_num", result.get("page", "?"))
                source = f"{reg_id}:{page}"

            chunk = ContentChunk(
                content=result.get("content", result.get("text", "")),
                source=source,
                relevance_score=result.get("score", result.get("relevance", 0.0)),
                chunk_type=result.get("type", result.get("block_type", "text")),
                metadata=result.get("metadata", {}),
            )
            self.add_chunk(chunk)

    def get_relevant_chunks(self, limit: int | None = None) -> list[ContentChunk]:
        """获取相关内容块

        Args:
            limit: 返回数量限制

        Returns:
            按相关性排序的内容块列表
        """
        if limit:
            return self._relevant_chunks[:limit]
        return list(self._relevant_chunks)

    def clear_chunks(self) -> None:
        """清空内容块（保留 TOC 缓存和已知章节）"""
        self._relevant_chunks.clear()

    # ========== 上下文生成 ==========

    def get_context(self) -> str:
        """生成记忆上下文（供提示词使用）"""
        return self._base.get_context()

    def get_toc_cache_hint(self) -> str:
        """生成 TOC 缓存提示

        Returns:
            提示文本，告知 Agent 哪些 TOC 已缓存
        """
        if not self._toc_cache:
            return ""

        cached_regs = list(self._toc_cache.keys())
        return f"已缓存 TOC: {', '.join(cached_regs)}（无需重复调用 get_toc）"

    def get_memory_context(self) -> str:
        """生成完整的记忆上下文

        Returns:
            包含对话历史、TOC 缓存提示、相关内容的上下文
        """
        parts = []

        # 对话历史
        base_context = self._base.get_context()
        if base_context:
            parts.append(base_context)

        # TOC 缓存提示
        toc_hint = self.get_toc_cache_hint()
        if toc_hint:
            parts.append(f"\n## 缓存状态\n{toc_hint}")

        # 相关内容摘要
        if self._relevant_chunks:
            chunks_summary = "\n## 已检索内容\n"
            for i, chunk in enumerate(self._relevant_chunks[:5], 1):
                preview = chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content
                chunks_summary += f"{i}. [{chunk.source}] {preview}\n"
            parts.append(chunks_summary)

        return "\n".join(parts)

    # ========== 查询级别重置 ==========

    def clear_query_context(self) -> None:
        """清空查询级别的上下文（保留 TOC 缓存）

        每次新查询时调用，清空内容块但保留 TOC 缓存。
        """
        self._relevant_chunks.clear()
