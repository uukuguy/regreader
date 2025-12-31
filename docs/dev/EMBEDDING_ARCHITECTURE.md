# 可插拔嵌入模型架构设计

## 背景

当前 GridCode 使用 `sentence-transformers` 加载 BGE 模型时产生警告：
```
WARNING  No sentence-transformers model found with name BAAI/bge-small-zh-v1.5.
Creating a new one with mean pooling.
```

用户希望支持 `FlagEmbedding`（BGE 官方库）并设计可切换的嵌入架构。

## FlagEmbedding vs sentence-transformers

| 特性 | FlagEmbedding | sentence-transformers |
|------|---------------|----------------------|
| BGE 模型支持 | 官方库，无警告 | 显示兼容警告 |
| query/corpus 分离 | `encode_queries()` / `encode_corpus()` | 仅 `encode()` |
| 查询指令 | 原生 `query_instruction_for_retrieval` | 需手动拼接 |
| FP16 加速 | 原生 `use_fp16=True` | 需额外配置 |
| 模型覆盖 | 主要 BGE 系列 | 广泛（SBERT, E5 等） |

## 设计方案

### 目录结构
```
src/grid_code/
├── embedding/                    # 新增嵌入模块
│   ├── __init__.py              # 导出 + 工厂函数
│   ├── base.py                  # BaseEmbedder 抽象基类
│   ├── sentence_transformer.py  # SentenceTransformerEmbedder
│   └── flag.py                  # FlagEmbedder
```

### 核心接口

```python
class EmbedType(Enum):
    QUERY = "query"       # 查询嵌入（检索时使用）
    DOCUMENT = "document" # 文档嵌入（索引时使用）

class BaseEmbedder(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @property
    def is_api_based(self) -> bool:
        """是否是 API 类后端（OpenAI/Cohere）"""
        return False  # 本地模型默认 False

    @abstractmethod
    def embed(self, text: str, embed_type: EmbedType) -> list[float]: ...
    @abstractmethod
    def embed_batch(self, texts: list[str], embed_type: EmbedType) -> list[list[float]]: ...

    # 语法糖
    def embed_query(self, text: str) -> list[float]: ...
    def embed_document(self, text: str) -> list[float]: ...
```

### 工厂函数
```python
def create_embedder(backend: str | None = None, ...) -> BaseEmbedder:
    """根据配置创建嵌入模型"""
    if backend == "flag":
        return FlagEmbedder(...)
    return SentenceTransformerEmbedder(...)  # 默认
```

### 配置扩展
```python
# config.py 新增
embedding_backend: str = "sentence_transformer"  # sentence_transformer | flag | openai | cohere
embedding_query_instruction: str | None = None
embedding_use_fp16: bool = True
embedding_device: str | None = None

# API 类后端预留（未来扩展）
embedding_api_key: str | None = None  # OpenAI/Cohere API Key
embedding_api_base: str | None = None  # 自定义 API 端点
```

## 实现步骤

### Step 1: 创建 embedding 模块基础
**文件**: `src/grid_code/embedding/base.py`
- 定义 `EmbedType` 枚举
- 定义 `BaseEmbedder` 抽象基类

### Step 2: 实现 SentenceTransformerEmbedder
**文件**: `src/grid_code/embedding/sentence_transformer.py`
- 自动检测 BGE 模型查询前缀
- 使用 `prompt_name` 区分 query/document

### Step 3: 实现 FlagEmbedder
**文件**: `src/grid_code/embedding/flag.py`
- 使用 `encode_queries()` / `encode_corpus()`
- 支持 FP16 加速

### Step 4: 工厂函数和模块导出
**文件**: `src/grid_code/embedding/__init__.py`
- `create_embedder()` 工厂函数
- `get_embedder()` 全局单例

### Step 5: 扩展配置
**文件**: `src/grid_code/config.py`
- 添加 `embedding_backend`、`embedding_use_fp16` 等配置

### Step 6: 重构向量索引
**文件**:
- `src/grid_code/index/vector/lancedb.py`
- `src/grid_code/index/vector/qdrant.py`
- `src/grid_code/index/table_lancedb.py`

修改点：
- 构造函数接受 `embedder: BaseEmbedder | None` 参数
- 删除重复的 `_embed_text()` / `_embed_texts()` 方法
- 索引时用 `embedder.embed_documents()`
- 搜索时用 `embedder.embed_query()`

### Step 7: 更新依赖
**文件**: `pyproject.toml`
```toml
[project.optional-dependencies]
flag = ["FlagEmbedding>=1.2.0"]
```

### Step 8: 添加测试
**文件**: `tests/dev/test_embedding.py`
- 测试两个后端的基本功能
- 测试工厂函数
- 测试配置驱动

## 关键文件

| 文件 | 操作 |
|------|------|
| `src/grid_code/embedding/base.py` | 新建 |
| `src/grid_code/embedding/sentence_transformer.py` | 新建 |
| `src/grid_code/embedding/flag.py` | 新建 |
| `src/grid_code/embedding/__init__.py` | 新建 |
| `src/grid_code/config.py` | 修改 |
| `src/grid_code/index/vector/lancedb.py` | 修改 |
| `src/grid_code/index/vector/qdrant.py` | 修改 |
| `src/grid_code/index/table_lancedb.py` | 修改 |
| `pyproject.toml` | 修改 |

## 使用示例

```bash
# 环境变量切换后端
export GRIDCODE_EMBEDDING_BACKEND=flag
```

```python
# 代码中指定
from grid_code.embedding import create_embedder

embedder = create_embedder(backend="flag")
query_vec = embedder.embed_query("工作票办理流程")
doc_vecs = embedder.embed_documents(["文档1", "文档2"])
```
