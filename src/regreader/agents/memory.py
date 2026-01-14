"""Agent 记忆系统

实现简单的会话级记忆，用于：
1. 缓存目录查询结果，避免重复调用 get_toc
2. 记忆高相关性搜索结果，供迭代推理使用
3. 记忆阅读的页面内容摘要
"""

from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ContentChunk:
    """内容片段

    Attributes:
        content: 内容文本
        source: 来源（如 angui_2024 P85）
        relevance_score: 相关性评分 (0-1)
        chunk_type: 类型: search_result, page_content, table
        metadata: 额外元数据
    """

    content: str
    source: str
    relevance_score: float
    chunk_type: str
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentMemory:
    """Agent 记忆状态

    会话级记忆，用于优化多轮工具调用效率。

    Attributes:
        toc_cache: 目录缓存 (reg_id -> TocTree dict)
        known_chapters: 已知章节范围（用于缩小搜索范围）
        relevant_chunks: 相关内容记忆（按相关性排序）
        current_query: 当前查询上下文
        max_chunks: 最大记忆容量
        min_relevance: 最小相关性阈值
    """

    toc_cache: dict[str, dict] = field(default_factory=dict)
    known_chapters: list[str] = field(default_factory=list)
    relevant_chunks: list[ContentChunk] = field(default_factory=list)
    current_query: str = ""
    max_chunks: int = 10
    min_relevance: float = 0.5

    def cache_toc(self, reg_id: str, toc: dict) -> None:
        """缓存目录

        Args:
            reg_id: 规程 ID
            toc: TocTree 字典
        """
        self.toc_cache[reg_id] = toc
        logger.debug(f"[Memory] 缓存目录: {reg_id}")

    def get_cached_toc(self, reg_id: str) -> dict | None:
        """获取缓存的目录

        Args:
            reg_id: 规程 ID

        Returns:
            缓存的 TocTree 字典，不存在返回 None
        """
        return self.toc_cache.get(reg_id)

    def has_cached_toc(self, reg_id: str) -> bool:
        """检查目录是否已缓存

        Args:
            reg_id: 规程 ID

        Returns:
            是否已缓存
        """
        return reg_id in self.toc_cache

    def add_chunk(self, chunk: ContentChunk) -> None:
        """添加内容片段

        保持按相关性排序，超过容量时移除低分内容。

        Args:
            chunk: 内容片段
        """
        # 过滤低相关性内容
        if chunk.relevance_score < self.min_relevance:
            logger.debug(
                f"[Memory] 跳过低相关性内容: score={chunk.relevance_score:.2f} < {self.min_relevance}"
            )
            return

        # 检查是否已存在相同来源的内容（避免重复）
        for existing in self.relevant_chunks:
            if existing.source == chunk.source and existing.chunk_type == chunk.chunk_type:
                # 如果新内容评分更高，替换旧内容
                if chunk.relevance_score > existing.relevance_score:
                    self.relevant_chunks.remove(existing)
                    break
                else:
                    logger.debug(f"[Memory] 跳过重复内容: {chunk.source}")
                    return

        self.relevant_chunks.append(chunk)

        # 按相关性降序排序
        self.relevant_chunks.sort(key=lambda x: x.relevance_score, reverse=True)

        # 保持最大容量
        if len(self.relevant_chunks) > self.max_chunks:
            removed = self.relevant_chunks[self.max_chunks :]
            self.relevant_chunks = self.relevant_chunks[: self.max_chunks]
            logger.debug(f"[Memory] 移除低分内容: {len(removed)} 条")

        logger.debug(
            f"[Memory] 添加内容: {chunk.source} ({chunk.chunk_type}, score={chunk.relevance_score:.2f})"
        )

    def add_search_results(self, results: list[dict]) -> None:
        """从搜索结果中提取并添加高相关性内容

        Args:
            results: smart_search 返回的结果列表
        """
        for item in results:
            score = item.get("score", 0)
            if score < self.min_relevance:
                continue

            content = item.get("content") or item.get("text") or item.get("snippet") or ""
            source = item.get("source", "")

            if content and source:
                chunk = ContentChunk(
                    content=content[:300],  # 截断长内容
                    source=source,
                    relevance_score=score,
                    chunk_type="search_result",
                    metadata={
                        "chapter_id": item.get("chapter_id"),
                        "page_num": item.get("page_num"),
                    },
                )
                self.add_chunk(chunk)

    def add_page_content(self, content: str, source: str, relevance: float = 0.8) -> None:
        """添加页面内容摘要

        Args:
            content: 页面内容
            source: 来源（如 angui_2024 P85）
            relevance: 相关性评分（默认 0.8）
        """
        if not content:
            return

        chunk = ContentChunk(
            content=content[:500],  # 只保留前500字符
            source=source,
            relevance_score=relevance,
            chunk_type="page_content",
        )
        self.add_chunk(chunk)

    def get_memory_context(self) -> str:
        """生成记忆上下文，用于注入系统提示词

        Returns:
            格式化的记忆上下文字符串
        """
        if not self.relevant_chunks:
            return ""

        lines = ["# 已获取的相关信息"]
        lines.append("（以下是之前搜索和阅读获得的内容摘要，可直接引用，无需重复搜索）\n")

        for i, chunk in enumerate(self.relevant_chunks[:5], 1):
            lines.append(f"## [{i}] {chunk.source}")
            lines.append(chunk.content[:500])
            lines.append("")

        return "\n".join(lines)

    def get_toc_cache_hint(self) -> str:
        """生成目录缓存提示，告知 LLM 哪些目录已缓存

        Returns:
            目录缓存提示字符串
        """
        if not self.toc_cache:
            return ""

        cached_regs = ", ".join(self.toc_cache.keys())
        return f"\n# 已缓存目录\n以下规程目录已获取: {cached_regs}\n无需再次调用 get_toc()，可直接使用 smart_search() 搜索。"

    def clear_query_context(self) -> None:
        """清除当前查询上下文（保留目录缓存）"""
        self.relevant_chunks = []
        self.current_query = ""
        self.known_chapters = []
        logger.debug("[Memory] 清除查询上下文（保留目录缓存）")

    def reset(self) -> None:
        """完全重置记忆"""
        self.toc_cache = {}
        self.known_chapters = []
        self.relevant_chunks = []
        self.current_query = ""
        logger.debug("[Memory] 完全重置")

    def get_stats(self) -> dict:
        """获取记忆统计信息

        Returns:
            包含统计信息的字典
        """
        return {
            "cached_tocs": list(self.toc_cache.keys()),
            "chunk_count": len(self.relevant_chunks),
            "known_chapters": self.known_chapters,
            "current_query": self.current_query,
        }

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"AgentMemory(tocs={stats['cached_tocs']}, "
            f"chunks={stats['chunk_count']}, "
            f"chapters={len(stats['known_chapters'])})"
        )
