"""FlagEmbedding 嵌入模型实现

使用 FlagEmbedding 库，为 BGE 模型官方推荐，无兼容性警告。
"""

from loguru import logger

from regreader.embedding.base import BaseEmbedder, EmbedType


class FlagEmbedder(BaseEmbedder):
    """FlagEmbedding 嵌入模型

    特点：
    - BGE 模型官方库，无 sentence-transformers 兼容警告
    - 原生支持 query/document 非对称嵌入
    - 支持 FP16 加速
    """

    # 默认查询指令
    DEFAULT_INSTRUCTIONS: dict[str, str] = {
        "zh": "为这个句子生成表示以用于检索相关文章：",
        "en": "Represent this sentence for searching relevant passages: ",
    }

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        dimension: int | None = None,
        query_instruction: str | None = None,
        use_fp16: bool = True,
        devices: str | list[int] | None = None,
    ):
        """初始化 FlagEmbedding 模型

        Args:
            model_name: HuggingFace 模型名或本地路径
            dimension: 嵌入维度（可选）
            query_instruction: 查询指令（可选，自动检测语言）
            use_fp16: 是否使用 FP16（默认启用）
            devices: 运行设备（可选，如 "cuda:0" 或 [0, 1]）
        """
        self._model_name = model_name
        self._dimension = dimension
        self._use_fp16 = use_fp16
        self._devices = devices
        self._model = None

        # 自动检测查询指令
        if query_instruction is None:
            query_instruction = self._detect_instruction(model_name)
        self._query_instruction = query_instruction

    def _detect_instruction(self, model_name: str) -> str:
        """根据模型名检测语言并返回对应指令"""
        if "zh" in model_name.lower():
            return self.DEFAULT_INSTRUCTIONS["zh"]
        return self.DEFAULT_INSTRUCTIONS["en"]

    @property
    def name(self) -> str:
        return "FlagEmbedding"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self.load()
            # 通过测试嵌入获取维度
            test_embedding = self._model.encode("test")
            self._dimension = len(test_embedding)
        return self._dimension

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """加载模型"""
        if self._model is not None:
            return

        logger.info(f"加载 FlagEmbedding 模型: {self._model_name}")

        try:
            from FlagEmbedding import FlagModel

            self._model = FlagModel(
                self._model_name,
                query_instruction_for_retrieval=self._query_instruction,
                use_fp16=self._use_fp16,
                devices=self._devices,
            )
            logger.info("FlagEmbedding 模型加载完成")
        except ImportError as e:
            raise ImportError(
                "FlagEmbedding 未安装。请运行: pip install grid-code[flag]"
            ) from e

    def embed(
        self,
        text: str,
        embed_type: EmbedType = EmbedType.DOCUMENT,
    ) -> list[float]:
        """生成单条嵌入"""
        if self._model is None:
            self.load()

        if embed_type == EmbedType.QUERY:
            embedding = self._model.encode_queries([text])[0]
        else:
            embedding = self._model.encode(text)

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

        if embed_type == EmbedType.QUERY:
            embeddings = self._model.encode_queries(texts, batch_size=batch_size)
        else:
            embeddings = self._model.encode(texts, batch_size=batch_size)

        return embeddings.tolist()
