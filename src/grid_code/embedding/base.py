"""嵌入模型抽象基类

定义嵌入模型的统一接口，支持非对称嵌入（query/document）。
"""

from abc import ABC, abstractmethod
from enum import Enum


class EmbedType(Enum):
    """嵌入类型枚举

    用于区分查询嵌入和文档嵌入，支持非对称模型（如 BGE）。
    """

    QUERY = "query"  # 查询嵌入（检索时使用）
    DOCUMENT = "document"  # 文档嵌入（索引时使用）


class BaseEmbedder(ABC):
    """嵌入模型抽象基类

    所有嵌入模型实现（SentenceTransformer、FlagEmbedding、OpenAI 等）必须继承此类。

    设计要点：
    - 支持非对称嵌入（query vs document）
    - 支持单条和批量嵌入
    - 延迟加载模型
    - 自动归一化输出

    示例:
        embedder = create_embedder()

        # 索引时使用文档嵌入
        doc_vectors = embedder.embed_documents(texts)

        # 检索时使用查询嵌入
        query_vector = embedder.embed_query(query)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """嵌入模型后端名称（如 SentenceTransformer、FlagEmbedding）"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """底层模型标识（HuggingFace 模型名或路径）"""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """嵌入向量维度"""
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        pass

    @property
    def is_api_based(self) -> bool:
        """是否是 API 类后端（OpenAI/Cohere）

        API 类后端不需要本地加载模型，但需要网络请求。
        """
        return False

    @abstractmethod
    def load(self) -> None:
        """显式加载模型

        对于本地模型，会下载并加载到内存。
        对于 API 类后端，可能只是验证连接。
        调用 embed 时会自动加载，此方法用于提前预热。
        """
        pass

    @abstractmethod
    def embed(
        self,
        text: str,
        embed_type: EmbedType = EmbedType.DOCUMENT,
    ) -> list[float]:
        """生成单条文本的嵌入向量

        Args:
            text: 待嵌入的文本
            embed_type: 嵌入类型（QUERY 用于检索，DOCUMENT 用于索引）

        Returns:
            归一化的嵌入向量
        """
        pass

    @abstractmethod
    def embed_batch(
        self,
        texts: list[str],
        embed_type: EmbedType = EmbedType.DOCUMENT,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """批量生成嵌入向量

        Args:
            texts: 待嵌入的文本列表
            embed_type: 嵌入类型
            batch_size: 批处理大小

        Returns:
            嵌入向量列表
        """
        pass

    # ==================== 语法糖方法 ====================

    def embed_query(self, text: str) -> list[float]:
        """生成查询嵌入

        对于非对称模型（如 BGE），会自动添加查询指令前缀。
        """
        return self.embed(text, EmbedType.QUERY)

    def embed_queries(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """批量生成查询嵌入"""
        return self.embed_batch(texts, EmbedType.QUERY, batch_size)

    def embed_document(self, text: str) -> list[float]:
        """生成文档嵌入

        用于索引时生成文档向量。
        """
        return self.embed(text, EmbedType.DOCUMENT)

    def embed_documents(
        self, texts: list[str], batch_size: int = 32
    ) -> list[list[float]]:
        """批量生成文档嵌入"""
        return self.embed_batch(texts, EmbedType.DOCUMENT, batch_size)
