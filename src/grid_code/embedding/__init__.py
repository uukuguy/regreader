"""嵌入模型模块

提供可插拔的嵌入模型抽象，支持多种后端实现。

使用方式:
    from grid_code.embedding import create_embedder, BaseEmbedder, EmbedType

    # 根据配置创建（默认 sentence_transformer）
    embedder = create_embedder()

    # 索引时使用文档嵌入
    doc_vectors = embedder.embed_documents(texts)

    # 检索时使用查询嵌入
    query_vector = embedder.embed_query(query)

    # 指定后端
    embedder = create_embedder(backend="flag")

支持的后端:
    - sentence_transformer: 通用 HuggingFace 模型（默认）
    - flag: BGE 模型官方库，无警告
"""

from typing import TYPE_CHECKING

from grid_code.embedding.base import BaseEmbedder, EmbedType

if TYPE_CHECKING:
    from grid_code.embedding.flag import FlagEmbedder
    from grid_code.embedding.sentence_transformer import SentenceTransformerEmbedder

__all__ = [
    "BaseEmbedder",
    "EmbedType",
    "SentenceTransformerEmbedder",
    "FlagEmbedder",
    "create_embedder",
    "get_embedder",
    "reset_embedder",
]


# 延迟导入实现类
def __getattr__(name: str):
    if name == "SentenceTransformerEmbedder":
        from grid_code.embedding.sentence_transformer import SentenceTransformerEmbedder

        return SentenceTransformerEmbedder
    elif name == "FlagEmbedder":
        from grid_code.embedding.flag import FlagEmbedder

        return FlagEmbedder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def create_embedder(
    backend: str | None = None,
    model_name: str | None = None,
    dimension: int | None = None,
    **kwargs,
) -> BaseEmbedder:
    """根据配置创建嵌入模型实例

    Args:
        backend: 嵌入后端 ("sentence_transformer" | "flag")，默认从配置读取
        model_name: 模型名称，默认从配置读取
        dimension: 嵌入维度，默认从配置读取
        **kwargs: 传递给具体实现的额外参数
            - query_instruction: 查询指令前缀
            - device: 运行设备（SentenceTransformer）
            - use_fp16: 是否使用 FP16（FlagEmbedding）
            - devices: 运行设备列表（FlagEmbedding）

    Returns:
        BaseEmbedder 实例

    Examples:
        # 使用配置默认值
        embedder = create_embedder()

        # 指定后端
        embedder = create_embedder(backend="flag")

        # 完全自定义
        embedder = create_embedder(
            backend="sentence_transformer",
            model_name="BAAI/bge-large-zh-v1.5",
            dimension=1024,
        )
    """
    from grid_code.config import get_settings

    settings = get_settings()

    # 使用配置默认值
    backend = backend or getattr(settings, "embedding_backend", "sentence_transformer")
    model_name = model_name or settings.embedding_model
    dimension = dimension or settings.embedding_dimension

    # 从配置读取额外参数（如果未显式提供）
    if "query_instruction" not in kwargs:
        query_instruction = getattr(settings, "embedding_query_instruction", None)
        if query_instruction:
            kwargs["query_instruction"] = query_instruction

    if backend == "flag":
        from grid_code.embedding.flag import FlagEmbedder

        # FlagEmbedding 特有参数
        if "use_fp16" not in kwargs:
            kwargs["use_fp16"] = getattr(settings, "embedding_use_fp16", True)

        return FlagEmbedder(
            model_name=model_name,
            dimension=dimension,
            **kwargs,
        )
    else:  # 默认使用 sentence_transformer
        from grid_code.embedding.sentence_transformer import SentenceTransformerEmbedder

        # SentenceTransformer 特有参数
        if "device" not in kwargs:
            device = getattr(settings, "embedding_device", None)
            if device:
                kwargs["device"] = device

        if "local_files_only" not in kwargs:
            local_files_only = getattr(settings, "embedding_local_files_only", False)
            if local_files_only:
                kwargs["local_files_only"] = local_files_only

        return SentenceTransformerEmbedder(
            model_name=model_name,
            dimension=dimension,
            **kwargs,
        )


# 全局单例
_embedder: BaseEmbedder | None = None


def get_embedder() -> BaseEmbedder:
    """获取全局嵌入模型单例

    适用于需要在多处共享同一模型实例的场景，避免重复加载。

    Returns:
        BaseEmbedder 单例
    """
    global _embedder
    if _embedder is None:
        _embedder = create_embedder()
    return _embedder


def reset_embedder() -> None:
    """重置全局嵌入模型（主要用于测试）"""
    global _embedder
    _embedder = None
