"""MCP 工具定义

定义 GridCode 的三个核心 MCP 工具：
1. get_toc - 获取规程目录
2. smart_search - 智能检索
3. read_page_range - 读取页面范围
"""

from grid_code.exceptions import InvalidPageRangeError, RegulationNotFoundError
from grid_code.index import HybridSearch
from grid_code.storage import PageStore
from grid_code.storage.models import PageContent, SearchResult, TocTree


class GridCodeTools:
    """GridCode MCP 工具集"""

    def __init__(
        self,
        page_store: PageStore | None = None,
        hybrid_search: HybridSearch | None = None,
    ):
        """
        初始化工具集

        Args:
            page_store: 页面存储实例
            hybrid_search: 混合检索实例
        """
        self.page_store = page_store or PageStore()
        self.hybrid_search = hybrid_search or HybridSearch()

    def get_toc(self, reg_id: str) -> dict:
        """
        获取规程目录树

        Args:
            reg_id: 规程标识（如 'angui_2024'）

        Returns:
            目录树结构，包含标题、页码范围等信息

        Raises:
            RegulationNotFoundError: 规程不存在
        """
        toc = self.page_store.load_toc(reg_id)
        return toc.model_dump()

    def smart_search(
        self,
        query: str,
        reg_id: str,
        chapter_scope: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        智能混合检索（关键词 + 语义）

        Args:
            query: 搜索查询（如 "母线失压"）
            reg_id: 规程标识
            chapter_scope: 限定章节范围（可选，如 "第六章"）
            limit: 返回结果数量限制

        Returns:
            搜索结果列表，每个结果包含:
            - page_num: 页码
            - chapter_path: 章节路径
            - snippet: 匹配片段
            - score: 相关性分数
            - source: 来源引用
        """
        # 验证规程存在
        if not self.page_store.exists(reg_id):
            raise RegulationNotFoundError(reg_id)

        results = self.hybrid_search.search(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter_scope,
            limit=limit,
        )

        return [
            {
                "page_num": r.page_num,
                "chapter_path": r.chapter_path,
                "snippet": r.snippet,
                "score": r.score,
                "source": r.source,
                "block_id": r.block_id,
            }
            for r in results
        ]

    def read_page_range(
        self,
        reg_id: str,
        start_page: int,
        end_page: int,
    ) -> dict:
        """
        读取连续页面的完整内容

        自动处理跨页表格拼接。

        Args:
            reg_id: 规程标识
            start_page: 起始页码
            end_page: 结束页码

        Returns:
            页面内容，包含:
            - content_markdown: 合并后的 Markdown 内容
            - source: 来源引用
            - has_merged_tables: 是否包含合并的跨页表格
            - pages: 原始页面数据

        Raises:
            InvalidPageRangeError: 无效的页码范围
            RegulationNotFoundError: 规程不存在
        """
        if start_page > end_page:
            raise InvalidPageRangeError(start_page, end_page)
        if start_page < 1:
            raise InvalidPageRangeError(start_page, end_page)

        # 限制单次读取的页数
        max_pages = 10
        if end_page - start_page + 1 > max_pages:
            end_page = start_page + max_pages - 1

        page_content = self.page_store.load_page_range(reg_id, start_page, end_page)

        return {
            "content_markdown": page_content.content_markdown,
            "source": page_content.source,
            "start_page": page_content.start_page,
            "end_page": page_content.end_page,
            "has_merged_tables": page_content.has_merged_tables,
            "page_count": len(page_content.pages),
        }

    def list_regulations(self) -> list[dict]:
        """
        列出所有已入库的规程

        Returns:
            规程信息列表
        """
        regulations = self.page_store.list_regulations()
        return [r.model_dump() for r in regulations]
