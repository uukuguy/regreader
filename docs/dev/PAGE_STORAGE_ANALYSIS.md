# GridCode 页面存储数据结构与页号检索机制分析报告

## 一、核心数据模型

### 1. PageDocument - 单页文档（核心存储单位）

**文件位置**: `src/grid_code/storage/models.py:57-93`

```python
class PageDocument(BaseModel):
    reg_id: str                              # 规程标识（如 'angui_2024'）
    page_num: int                            # 页码（从 1 开始）
    chapter_path: list[str]                  # 章节路径（如 ['第六章', '事故处理']）
    content_blocks: list[ContentBlock]       # 按阅读顺序排列的内容块
    content_markdown: str                    # 页面完整 Markdown 内容
    continues_from_prev: bool                # 是否从上一页延续（跨页标记）
    continues_to_next: bool                  # 是否延续到下一页（跨页标记）
    annotations: list[Annotation]            # 页脚注释列表
```

**关键特性**：
- 每页独立存储为 JSON 文件
- 提供 `source` 属性返回引用格式：`"{reg_id} P{page_num}"`
- 支持跨页内容标记（`continues_from_prev` / `continues_to_next`）
- 便捷方法：`get_tables()` 和 `get_headings()` 获取特定类型内容块

### 2. ContentBlock - 内容块

**文件位置**: `src/grid_code/storage/models.py:42-54`

```python
class ContentBlock(BaseModel):
    block_id: str                            # 内容块唯一标识
    block_type: Literal["text", "table", "heading", "list"]
    order_in_page: int                       # 在页面中的顺序（从 0 开始）
    content_markdown: str                    # Markdown 格式内容
    table_meta: TableMeta | None             # 表格元数据（仅 table 类型）
    heading_level: int | None                # 标题级别（1-6，仅 heading 类型）
```

**内容块类型**：
- `text`: 普通文本段落
- `table`: 表格（含元数据）
- `heading`: 标题（1-6级）
- `list`: 列表

### 3. TableMeta - 表格元数据

**文件位置**: `src/grid_code/storage/models.py:21-31`

```python
class TableMeta(BaseModel):
    table_id: str                            # 表格唯一标识
    caption: str | None                      # 表格标题（如 '表6-2 母线故障处置'）
    is_truncated: bool                       # *** 关键：是否被截断（跨页）***
    row_headers: list[str]                   # 行标题列表
    col_headers: list[str]                   # 列标题列表
    row_count: int                           # 行数
    col_count: int                           # 列数
    cells: list[TableCell]                   # 单元格数据
```

**跨页表格处理**：
- `is_truncated=True` 标记表格被截断，需要拼接下一页
- 配合 PageDocument 的 `continues_to_next` 标记使用

### 4. PageContent - 页面范围读取结果

**文件位置**: `src/grid_code/storage/models.py:131-146`

```python
class PageContent(BaseModel):
    reg_id: str                              # 规程标识
    start_page: int                          # 起始页码
    end_page: int                            # 结束页码
    content_markdown: str                    # 合并后的 Markdown 内容
    pages: list[PageDocument]                # 原始页面列表
    has_merged_tables: bool                  # 是否包含合并的跨页表格
```

**用途**：
- 读取多页时的返回结果
- 自动处理跨页表格拼接
- 提供 `source` 属性返回引用格式：`"{reg_id} P{start}-P{end}"`

---

## 二、物理存储结构

### 存储目录配置

**配置文件**: `src/grid_code/config.py`

```python
class GridCodeSettings(BaseSettings):
    pages_dir: Path = Field(
        default=Path("./data/pages"),
        description="页面 JSON 存储目录"
    )
```

### 实际存储目录结构

```
./data/pages/
├── angui_2024/                          # 规程目录（reg_id）
│   ├── page_0001.json                   # 页码 1 的页面数据
│   ├── page_0002.json                   # 页码 2 的页面数据
│   ├── page_0072.json                   # 页码 72 的页面数据
│   ├── ...
│   ├── info.json                        # 规程元信息
│   └── toc.json                         # 目录树
└── other_regulation/
```

### 页面文件命名规则

**实现位置**: `src/grid_code/storage/page_store.py:40-42`

```python
def _get_page_path(self, reg_id: str, page_num: int) -> Path:
    """获取页面文件路径"""
    return self._get_reg_dir(reg_id) / f"page_{page_num:04d}.json"
```

**规则**: `page_{page_num:04d}.json`（4位零填充）

**示例**：
- 页码 1 → `page_0001.json`
- 页码 72 → `page_0072.json`
- 页码 150 → `page_0150.json`

---

## 三、页号检索实现

### 1. 单页查询：PageStore.load_page()

**文件位置**: `src/grid_code/storage/page_store.py:112-137`

**实现流程**：

```python
def load_page(self, reg_id: str, page_num: int) -> PageDocument:
    # 步骤 1: 验证规程存在
    reg_dir = self._get_reg_dir(reg_id)
    # → ./data/pages/angui_2024

    if not reg_dir.exists():
        raise RegulationNotFoundError(reg_id)

    # 步骤 2: 构造页面文件路径
    page_path = self._get_page_path(reg_id, page_num)
    # → ./data/pages/angui_2024/page_0072.json

    # 步骤 3: 检查文件是否存在
    if not page_path.exists():
        raise PageNotFoundError(reg_id, page_num)

    # 步骤 4: 读取并解析 JSON
    with open(page_path, encoding="utf-8") as f:
        data = json.load(f)
        return PageDocument.model_validate(data)
```

**关键特性**：
- **零索引查询**：直接通过页码构造文件路径，无需查询数据库或索引
- **O(1) 时间复杂度**：文件系统直接访问
- **异常处理**：规程不存在 / 页面不存在分别抛出不同异常

### 2. 范围查询：PageStore.load_page_range()

**文件位置**: `src/grid_code/storage/page_store.py:139-180`

**实现流程**：

```python
def load_page_range(self, reg_id: str, start_page: int, end_page: int) -> PageContent:
    pages = []

    # 步骤 1: 逐页加载
    for page_num in range(start_page, end_page + 1):
        try:
            page = self.load_page(reg_id, page_num)  # 递归调用单页查询
            pages.append(page)
        except PageNotFoundError:
            logger.warning(f"页面不存在，跳过")
            continue

    # 步骤 2: 自动合并跨页表格
    merged_markdown, has_merged_tables = self._merge_pages(pages)

    # 步骤 3: 返回合并结果
    return PageContent(
        reg_id=reg_id,
        start_page=start_page,
        end_page=end_page,
        content_markdown=merged_markdown,  # 已拼接跨页表格
        pages=pages,                       # 原始页面列表
        has_merged_tables=has_merged_tables,
    )
```

### 3. 跨页表格处理：_merge_pages()

**文件位置**: `src/grid_code/storage/page_store.py:182-242`

**核心逻辑**：

```python
def _merge_pages(self, pages: list[PageDocument]) -> tuple[str, bool]:
    """合并多页内容，处理跨页表格"""

    pending_table: list[str] | None = None
    parts = []
    has_merged_tables = False

    for page in pages:
        # 检查当前页是否延续自上一页
        if page.continues_from_prev and pending_table is not None:
            # 拼接表格数据行（跳过表头）
            for block in page.content_blocks:
                if block.block_type == "table":
                    table_lines = block.content_markdown.split("\n")
                    # 提取数据行（跳过前两行表头）
                    data_lines = [
                        line for line in table_lines[2:]
                        if line.strip() and line.startswith("|")
                    ]
                    pending_table.extend(data_lines)  # 拼接行
                    has_merged_tables = True
                    break

        # 检查当前页是否延续到下一页
        if page.continues_to_next:
            for block in page.content_blocks:
                if block.block_type == "table" and block.table_meta.is_truncated:
                    # 保存当前表格，等待下一页拼接
                    pending_table = block.content_markdown.split("\n")

    return "\n".join(parts), has_merged_tables
```

**跨页表格处理示例**：

假设表格跨越第 72-74 页：

```
第 72 页：
  continues_to_next = true
  table_meta.is_truncated = true
  content = "| 项目 | 值 |\n|------|-----|\n| 数据1 | A |\n| 数据2 | B |"

第 73 页：
  continues_from_prev = true
  continues_to_next = true
  content = "| 项目 | 值 |\n|------|-----|\n| 数据3 | C |\n| 数据4 | D |"

第 74 页：
  continues_from_prev = true
  content = "| 项目 | 值 |\n|------|-----|\n| 数据5 | E |"

合并结果：
  "| 项目 | 值 |\n|------|-----|\n| 数据1 | A |\n| 数据2 | B |\n| 数据3 | C |\n| 数据4 | D |\n| 数据5 | E |"
```

---

## 四、MCP 工具层实现

### GridCodeTools.read_page_range()

**文件位置**: `src/grid_code/mcp/tools.py:96-142`

```python
def read_page_range(self, reg_id: str, start_page: int, end_page: int) -> dict:
    """读取连续页面的完整内容

    自动处理跨页表格拼接。
    """
    # 验证页码范围
    if start_page > end_page:
        raise InvalidPageRangeError(start_page, end_page)
    if start_page < 1:
        raise InvalidPageRangeError(start_page, end_page)

    # 限制单次读取的页数（最多 10 页）
    max_pages = 10
    if end_page - start_page + 1 > max_pages:
        end_page = start_page + max_pages - 1

    # 调用存储层
    page_content = self.page_store.load_page_range(reg_id, start_page, end_page)

    return {
        "content_markdown": page_content.content_markdown,
        "source": page_content.source,
        "start_page": page_content.start_page,
        "end_page": page_content.end_page,
        "has_merged_tables": page_content.has_merged_tables,
        "page_count": len(page_content.pages),
    }
```

**关键特性**：
- **页数限制**：单次最多读取 10 页（防止内存溢出）
- **自动截断**：超过限制时自动调整 `end_page`
- **返回格式**：标准化 dict 格式，供 MCP Server 返回

### MCP Server 注册

**文件位置**: `src/grid_code/mcp/server.py`

```python
@mcp.tool()
def read_page_range(reg_id: str, start_page: int, end_page: int) -> dict:
    """读取连续页面的完整 Markdown 内容。

    自动处理跨页表格的拼接。当搜索结果显示表格可能跨页时，
    应读取相邻页面以获取完整信息。

    单次最多读取 10 页。
    """
    try:
        return tools.read_page_range(reg_id, start_page, end_page)
    except GridCodeError as e:
        return {"error": str(e)}
```

---

## 五、页号检索完整流程

### 调用流程图

```
Agent 调用 read_page_range(reg_id="angui_2024", start_page=72, end_page=75)
    ↓
MCP Server 接收工具调用
    ↓
GridCodeTools.read_page_range()
    ├─ 验证页码范围（1 ≤ start ≤ end）
    ├─ 限制页数（最多 10 页）
    └─ 调用 page_store.load_page_range()
          ↓
PageStore.load_page_range()
    ├─ 循环加载页面：
    │   ├─ load_page(72) → ./data/pages/angui_2024/page_0072.json
    │   ├─ load_page(73) → ./data/pages/angui_2024/page_0073.json
    │   ├─ load_page(74) → ./data/pages/angui_2024/page_0074.json
    │   └─ load_page(75) → ./data/pages/angui_2024/page_0075.json
    ↓
    ├─ 检测跨页表格：
    │   ├─ 第 72 页：continues_to_next=true, is_truncated=true
    │   ├─ 第 73 页：continues_from_prev=true
    │   ├─ 第 74 页：continues_from_prev=true
    │   └─ 第 75 页：continues_from_prev=false
    ↓
    ├─ 自动拼接跨页表格（_merge_pages）
    │   ├─ 第 72 页表格数据（包含表头和数据）
    │   ├─ + 第 73 页表格数据行（只取数据行）
    │   ├─ + 第 74 页表格数据行（只取数据行）
    │   └─ = 完整的跨页表格
    ↓
返回 PageContent：
    {
        "content_markdown": "合并后的完整内容...",
        "source": "angui_2024 P72-P75",
        "pages": [PageDocument(72), PageDocument(73), ...],
        "has_merged_tables": true
    }
```

---

## 六、索引与页号的关联

### 1. 关键词索引（FTS5）

**文件位置**: `src/grid_code/index/keyword/fts5.py`

**存储结构**：

```sql
CREATE VIRTUAL TABLE page_index USING fts5(
    content,
    reg_id UNINDEXED,      -- 规程标识
    page_num UNINDEXED,    -- *** 页码索引字段 ***
    chapter_path UNINDEXED,
    block_id UNINDEXED,
    tokenize='unicode61'
)
```

**检索返回**：

```python
def search(self, query: str, ...) -> list[SearchResult]:
    sql = """
        SELECT
            page_index.reg_id,
            page_index.page_num,           -- 返回页码
            page_index.chapter_path,
            page_index.block_id,
            bm25(page_index) as score
        FROM page_index
        WHERE page_index MATCH ?
    """

    return [
        SearchResult(
            reg_id=row["reg_id"],
            page_num=row["page_num"],      # 直接使用存储的页码
            ...
        )
        for row in rows
    ]
```

### 2. 向量索引（LanceDB）

**文件位置**: `src/grid_code/index/vector/lancedb.py`

**索引记录**：

```python
def index_page(self, page: PageDocument) -> None:
    records = []
    for block in page.content_blocks:
        records.append({
            "vector": self._embed_text(block.content_markdown),
            "reg_id": page.reg_id,
            "page_num": page.page_num,    # 存储页码
            "block_id": block.block_id,
            "content": content[:500],
        })
    table.add(records)
```

**检索返回**：

```python
def search(self, query: str, ...) -> list[SearchResult]:
    results = table.search(query_vector).limit(limit).to_list()

    return [
        SearchResult(
            page_num=row["page_num"],      # 向量结果中包含页码
            ...
        )
        for row in results
    ]
```

---

## 七、核心设计特点总结

### 1. 按页号存储的优势

| 特点 | 说明 |
|------|------|
| **零索引查询** | 页号直接对应文件系统查询，无需索引中间步骤 |
| **O(1) 访问** | 页面检索时间复杂度为常数级 |
| **简单可靠** | 文件系统天然支持，无需额外数据库 |
| **易于调试** | 直接打开 JSON 文件即可查看页面内容 |
| **并行友好** | 多页读取可并行执行（当前实现为串行） |

### 2. 数据流向

```
PDF 文档
    ↓ (Docling 解析)
PageDocument 对象列表
    ↓ (page_store.save_pages)
./data/pages/{reg_id}/page_XXXX.json 文件
    ↓ (索引构建)
FTS5 + LanceDB 索引（含 page_num 字段）
    ↓ (智能检索)
SearchResult（含 page_num）
    ↓ (read_page_range)
PageContent（自动拼接跨页表格）
    ↓ (MCP 工具)
Agent 接收完整页面内容
```

### 3. 跨页表格处理机制

| 标记字段 | 位置 | 作用 |
|---------|------|------|
| `continues_from_prev` | PageDocument | 标记当前页是否延续自上一页 |
| `continues_to_next` | PageDocument | 标记当前页是否延续到下一页 |
| `is_truncated` | TableMeta | 标记表格是否被截断（跨页） |

**拼接规则**：
1. 第一页：保留完整内容（包括表头和分隔行）
2. 后续页：只提取数据行（跳过表头的前两行）
3. 合并方式：将所有数据行拼接到第一页表格后

### 4. 异常处理

**文件位置**: `src/grid_code/exceptions.py`

| 异常类 | 触发条件 | 使用场景 |
|--------|---------|---------|
| `RegulationNotFoundError` | 规程目录不存在 | 任何需要访问规程的操作 |
| `PageNotFoundError` | 页面文件不存在 | 单页或范围查询时 |
| `InvalidPageRangeError` | 页码范围无效 | start > end 或 start < 1 |

---

## 八、实际数据示例

### 单页 JSON 文件示例

**文件**: `./data/pages/angui_2024/page_0001.json`

```json
{
  "reg_id": "angui_2024",
  "page_num": 1,
  "chapter_path": [],
  "content_blocks": [
    {
      "block_id": "text_71730adb",
      "block_type": "text",
      "order_in_page": 0,
      "content_markdown": "2024 年国调直调安全自动装置 调度运行管理规定（第二版）",
      "table_meta": null,
      "heading_level": null
    }
  ],
  "content_markdown": "2024 年国调直调安全自动装置 调度运行管理规定（第二版）\n\n国家电力调度控制中心 2024 年 7 月\n",
  "continues_from_prev": false,
  "continues_to_next": false,
  "annotations": []
}
```

### 规程元信息

**文件**: `./data/pages/angui_2024/info.json`

```json
{
  "reg_id": "angui_2024",
  "title": "angui_2024",
  "source_file": "2024年国调直调安全自动装置调度运行管理规定（第二版）.pdf",
  "total_pages": 150,
  "indexed_at": "2025-12-28T20:06:43.465494"
}
```

---

## 九、关键文件路径汇总

| 组件 | 文件路径 |
|------|---------|
| 数据模型 | `src/grid_code/storage/models.py` |
| 页面存储 | `src/grid_code/storage/page_store.py` |
| MCP 工具 | `src/grid_code/mcp/tools.py` |
| MCP Server | `src/grid_code/mcp/server.py` |
| FTS5 索引 | `src/grid_code/index/keyword/fts5.py` |
| LanceDB 索引 | `src/grid_code/index/vector/lancedb.py` |
| 异常定义 | `src/grid_code/exceptions.py` |
| 配置文件 | `src/grid_code/config.py` |

---

## 十、使用示例

### Agent 典型调用流程

```python
# 1. Agent 通过 MCP 调用 smart_search 检索相关页面
results = smart_search(
    query="母线失压处理",
    reg_id="angui_2024",
    limit=5
)
# 返回：[
#   {"page_num": 72, "source": "angui_2024 P72", ...},
#   {"page_num": 73, "source": "angui_2024 P73", ...},
# ]

# 2. Agent 发现可能存在跨页表格，读取相邻页面
page_content = read_page_range(
    reg_id="angui_2024",
    start_page=72,
    end_page=75
)
# 返回：{
#   "content_markdown": "完整内容（已拼接跨页表格）",
#   "source": "angui_2024 P72-P75",
#   "has_merged_tables": true,
#   "page_count": 4
# }

# 3. Agent 基于完整内容进行推理和回答
```

---

## 结论

GridCode 的页面存储与检索机制具有以下核心特点：

1. **直接页号访问**：页号直接映射到文件路径，实现 O(1) 访问
2. **自动跨页处理**：通过标记字段自动检测和拼接跨页表格
3. **多层次索引**：FTS5 和 LanceDB 索引都存储页码，支持混合检索
4. **完整元数据**：章节路径、内容块 ID、表格元数据完整保留
5. **简单可靠**：基于文件系统，无需复杂数据库依赖

这种设计非常适合"LLM 翻页式阅读"的场景，让 Agent 能够像人类一样快速定位和阅读规程页面。
