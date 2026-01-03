"""GridCode 配置管理

使用 Pydantic Settings 管理配置，支持环境变量和配置文件。
"""

import os
from pathlib import Path

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GridCodeSettings(BaseSettings):
    """GridCode 全局配置"""

    model_config = SettingsConfigDict(
        env_prefix="GRIDCODE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # 存储路径配置
    data_dir: Path = Field(
        default=Path("./data/storage"),
        description="数据存储目录",
    )
    pages_dir: Path = Field(
        default=Path("./data/storage/pages"),
        description="页面 JSON 存储目录",
    )
    index_dir: Path = Field(
        default=Path("./data/storage/index"),
        description="索引文件目录",
    )

    # FTS5 索引配置
    fts_db_name: str = Field(
        default="pages.db",
        description="FTS5 数据库文件名",
    )

    # LanceDB 配置
    lancedb_name: str = Field(
        default="vectors",
        description="LanceDB 数据库目录名",
    )

    # 嵌入模型配置
    embedding_backend: str = Field(
        default="sentence_transformer",
        description="嵌入模型后端: sentence_transformer, flag",
    )
    embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="句向量嵌入模型（HuggingFace 模型名）",
    )
    embedding_dimension: int = Field(
        default=512,
        description="嵌入向量维度",
    )
    embedding_query_instruction: str | None = Field(
        default=None,
        description="查询嵌入前缀（可选，BGE 模型自动设置）",
    )
    embedding_use_fp16: bool = Field(
        default=True,
        description="是否使用 FP16 加速（FlagEmbedding 专用）",
    )
    embedding_device: str | None = Field(
        default=None,
        description="嵌入模型运行设备（如 cuda:0，默认自动选择）",
    )
    embedding_local_files_only: bool = Field(
        default=True,
        description="仅使用本地缓存的模型（离线模式，避免网络请求）",
    )
    # API 类后端预留（未来扩展）
    embedding_api_key: str | None = Field(
        default=None,
        description="嵌入 API 密钥（OpenAI/Cohere 等 API 后端）",
    )
    embedding_api_base: str | None = Field(
        default=None,
        description="嵌入 API 端点（自定义 API 服务器）",
    )

    # MCP Server 配置
    mcp_host: str = Field(
        default="127.0.0.1",
        description="MCP Server 监听地址",
    )
    mcp_port: int = Field(
        default=8080,
        description="MCP Server 监听端口",
    )

    # MCP 客户端模式配置
    use_mcp_mode: bool = Field(
        default=False,
        description="是否默认使用 MCP 模式访问数据（通过 MCP Server）",
    )
    mcp_transport: str = Field(
        default="stdio",
        description="MCP 传输方式: stdio（自动启动子进程）, sse（连接外部服务）",
    )
    mcp_server_url: str | None = Field(
        default=None,
        description="MCP SSE 服务器 URL（SSE 模式时使用，如 http://localhost:8080/sse）",
    )

    # LLM 统一配置入口
    llm_base_url: str = Field(
        default="https://api.anthropic.com",
        description="LLM API 端点",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "LLM_BASE_URL"),
    )
    llm_api_key: str = Field(
        default="",
        description="LLM API 密钥",
        validation_alias=AliasChoices("OPENAI_API_KEY", "LLM_API_KEY"),
    )
    llm_model_name: str = Field(
        default="claude-sonnet-4-20250514",
        description="LLM 模型名称（如 claude-sonnet-4-20250514, gpt-4o, gemini-pro）",
        validation_alias=AliasChoices("OPENAI_MODEL_NAME", "LLM_MODEL_NAME"),
    )

    # Anthropic/Claude 专用配置（用于 ClaudeAgent）
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API 密钥",
        validation_alias="ANTHROPIC_API_KEY",
    )
    anthropic_base_url: str = Field(
        default="",
        description="Anthropic API 端点（留空使用官方端点）",
        validation_alias="ANTHROPIC_BASE_URL",
    )
    anthropic_model_name: str = Field(
        default="",
        description="Anthropic 模型名称（留空使用 SDK 默认值，如 claude-sonnet-4-5-20250929）",
        validation_alias="ANTHROPIC_MODEL_NAME",
    )

    # Agent 配置
    prompt_mode: Literal["full", "optimized", "simple"] = Field(
        default="optimized",
        description="Agent 提示词模式: full（完整版）, optimized（优化版，默认）, simple（最简版）",
    )
    enable_agent_memory: bool = Field(
        default=False,
        description="是否启用 Agent 记忆系统（目录缓存 + 相关内容记忆）",
    )

    # MCP 工具集配置
    enable_advanced_tools: bool = Field(
        default=False,
        description="是否启用高级分析工具（find_similar_content, compare_sections）",
    )

    # 索引后端配置
    keyword_index_backend: str = Field(
        default="fts5",
        description="关键词索引后端: fts5, tantivy, whoosh",
    )
    vector_index_backend: str = Field(
        default="lancedb",
        description="向量索引后端: lancedb, qdrant",
    )

    # Qdrant 配置
    qdrant_url: str | None = Field(
        default=None,
        description="Qdrant 服务器 URL（服务器模式）",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API Key（服务器模式）",
    )

    # 检索配置
    search_top_k: int = Field(
        default=10,
        description="混合检索返回的最大结果数",
    )
    fts_weight: float = Field(
        default=0.4,
        description="关键词检索权重（0-1）",
    )
    vector_weight: float = Field(
        default=0.6,
        description="语义检索权重（0-1）",
    )

    # 表格索引配置
    table_fts_db_name: str = Field(
        default="tables.db",
        description="表格 FTS5 数据库文件名",
    )
    table_lancedb_name: str = Field(
        default="table_vectors",
        description="表格 LanceDB 数据库目录名",
    )
    table_search_mode: str = Field(
        default="hybrid",
        description="表格搜索默认模式: keyword, semantic, hybrid",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    @property
    def fts_db_path(self) -> Path:
        """FTS5 数据库完整路径"""
        return self.index_dir / self.fts_db_name

    @property
    def lancedb_path(self) -> Path:
        """LanceDB 数据库完整路径"""
        return self.index_dir / self.lancedb_name

    @property
    def table_fts_db_path(self) -> Path:
        """表格 FTS5 数据库完整路径"""
        return self.index_dir / self.table_fts_db_name

    @property
    def table_lancedb_path(self) -> Path:
        """表格 LanceDB 数据库完整路径"""
        return self.index_dir / self.table_lancedb_name

    def get_llm_provider(self) -> str:
        """根据模型名称推断 LLM 提供商

        Returns:
            提供商名称: anthropic, openai, google
        """
        model = self.llm_model_name.lower()
        # Anthropic Claude
        if "claude" in model or "sonnet" in model or "opus" in model or "haiku" in model:
            return "anthropic"
        # OpenAI
        elif "gpt" in model or "o1" in model or "o3" in model:
            return "openai"
        # Google Gemini
        elif "gemini" in model:
            return "google"
        # 国产模型（使用 OpenAI 兼容接口）
        elif "glm" in model or "deepseek" in model or "qwen" in model or "yi" in model:
            return "openai"
        return "openai"  # 默认使用 OpenAI 兼容接口


# 全局配置实例（延迟初始化）
_settings: GridCodeSettings | None = None


def get_settings() -> GridCodeSettings:
    """获取全局配置实例"""
    global _settings
    if _settings is None:
        _settings = GridCodeSettings()
    return _settings


def reset_settings():
    """重置全局配置（主要用于测试）"""
    global _settings
    _settings = None
