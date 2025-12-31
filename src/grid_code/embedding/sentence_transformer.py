"""SentenceTransformer 嵌入模型实现

使用 sentence-transformers 库，支持通用 HuggingFace 模型。
"""

from loguru import logger

from grid_code.embedding.base import BaseEmbedder, EmbedType


class SentenceTransformerEmbedder(BaseEmbedder):
    """SentenceTransformer 嵌入模型

    特点：
    - 通用性强，支持大部分 HuggingFace 嵌入模型
    - 支持 prompt_name 实现非对称嵌入
    - 自动归一化输出
    """

    # BGE 模型的查询前缀（中文和英文）
    DEFAULT_QUERY_PROMPTS: dict[str, str] = {
        "bge-small-zh": "为这个句子生成表示以用于检索相关文章：",
        "bge-base-zh": "为这个句子生成表示以用于检索相关文章：",
        "bge-large-zh": "为这个句子生成表示以用于检索相关文章：",
        "bge-small-en": "Represent this sentence for searching relevant passages: ",
        "bge-base-en": "Represent this sentence for searching relevant passages: ",
        "bge-large-en": "Represent this sentence for searching relevant passages: ",
    }

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        dimension: int | None = None,
        query_instruction: str | None = None,
        device: str | None = None,
    ):
        """初始化 SentenceTransformer 嵌入模型

        Args:
            model_name: HuggingFace 模型名或本地路径
            dimension: 嵌入维度（可选，自动检测）
            query_instruction: 查询前缀（可选，BGE 模型自动设置）
            device: 运行设备（可选，自动选择）
        """
        self._model_name = model_name
        self._dimension = dimension
        self._device = device
        self._model = None

        # 自动检测 BGE 模型的查询前缀
        self._query_instruction = query_instruction
        if query_instruction is None:
            self._query_instruction = self._detect_query_instruction(model_name)

    def _detect_query_instruction(self, model_name: str) -> str | None:
        """检测模型对应的查询前缀"""
        model_lower = model_name.lower()
        for key, prompt in self.DEFAULT_QUERY_PROMPTS.items():
            if key in model_lower:
                return prompt
        return None

    @property
    def name(self) -> str:
        return "SentenceTransformer"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # 延迟加载以获取维度
            self.load()
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._dimension

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """加载模型"""
        if self._model is not None:
            return

        logger.info(f"加载 SentenceTransformer 模型: {self._model_name}")
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self._model_name,
            device=self._device,
        )

        # 配置 prompts（如果有查询前缀）
        if self._query_instruction:
            self._model.prompts = {
                "query": self._query_instruction,
                "document": "",  # 文档不加前缀
            }

        logger.info(
            f"模型加载完成，维度: {self._model.get_sentence_embedding_dimension()}"
        )

    def embed(
        self,
        text: str,
        embed_type: EmbedType = EmbedType.DOCUMENT,
    ) -> list[float]:
        """生成单条嵌入"""
        if self._model is None:
            self.load()

        # 使用 prompt_name 区分查询和文档
        prompt_name = None
        if self._query_instruction and embed_type == EmbedType.QUERY:
            prompt_name = "query"

        embedding = self._model.encode(
            text,
            normalize_embeddings=True,
            prompt_name=prompt_name,
        )
        return embedding.tolist()

    def embed_batch(
        self,
        texts: list[str],
        embed_type: EmbedType = EmbedType.DOCUMENT,
        batch_size: int = 32,
    ) -> list[list[float]]:
        """批量生成嵌入"""
        if not texts:
            return []

        if self._model is None:
            self.load()

        prompt_name = None
        if self._query_instruction and embed_type == EmbedType.QUERY:
            prompt_name = "query"

        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            prompt_name=prompt_name,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
        )
        return embeddings.tolist()
