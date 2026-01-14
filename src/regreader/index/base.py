"""索引抽象基类

定义关键词检索器和语义检索器的统一接口。
"""

from abc import ABC, abstractmethod

from regreader.storage.models import DocumentStructure, PageDocument, SearchResult


class BaseKeywordIndex(ABC):
    """关键词检索器抽象基类

    所有关键词检索实现（FTS5、Tantivy、Whoosh）必须继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """检索器名称"""
        pass

    @abstractmethod
    def index_page(
        self,
        page: PageDocument,
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """
        索引单个页面

        Args:
            page: PageDocument 对象
            doc_structure: 文档结构（可选，用于获取 section_number）
        """
        pass

    @abstractmethod
    def index_pages(
        self,
        pages: list[PageDocument],
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """
        批量索引页面

        Args:
            pages: PageDocument 列表
            doc_structure: 文档结构（可选）
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[SearchResult]:
        """
        执行关键词搜索

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
        pass

    @abstractmethod
    def delete_regulation(self, reg_id: str) -> None:
        """
        删除规程的所有索引

        Args:
            reg_id: 规程标识
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭连接/释放资源"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class BaseVectorIndex(ABC):
    """语义检索器抽象基类

    所有语义检索实现（LanceDB、Qdrant）必须继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """检索器名称"""
        pass

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """嵌入向量维度"""
        pass

    @abstractmethod
    def index_page(
        self,
        page: PageDocument,
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """
        索引单个页面

        Args:
            page: PageDocument 对象
            doc_structure: 文档结构（可选，用于获取 section_number）
        """
        pass

    @abstractmethod
    def index_pages(
        self,
        pages: list[PageDocument],
        doc_structure: DocumentStructure | None = None
    ) -> None:
        """
        批量索引页面

        Args:
            pages: PageDocument 列表
            doc_structure: 文档结构（可选）
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        reg_id: str | None = None,
        chapter_scope: str | None = None,
        limit: int = 10,
        block_types: list[str] | None = None,
        section_number: str | None = None,
    ) -> list[SearchResult]:
        """
        执行语义搜索

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
        pass

    @abstractmethod
    def delete_regulation(self, reg_id: str) -> None:
        """
        删除规程的所有向量

        Args:
            reg_id: 规程标识
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭连接/释放资源"""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
