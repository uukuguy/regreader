# RegReader 页面数据对比脚本实现计划

## 任务概述

创建一个 CLI 命令 `regreader inspect`，用于对比显示指定页面在三种数据源中的原始数据：
1. FTS5 关键词索引
2. LanceDB 向量索引
3. MCP 工具 API 调用（原始 PageDocument）

**用户需求**：
- ✅ 终端显示格式化的对比结果（使用 Rich 库美化）
- ✅ 同时保存 JSON 文件供后续分析
- ✅ 高亮显示数据差异
- ✅ 集成为 CLI 命令

---

## 实现方案

### 1. 新增 CLI 命令

**文件**: `src/regreader/cli.py`

**新增命令**：
```python
@app.command()
def inspect(
    reg_id: str = typer.Argument(..., help="规程标识"),
    page_num: int = typer.Argument(..., help="页码"),
    output: Path = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
    show_vectors: bool = typer.Option(False, "--show-vectors", help="显示向量数据（默认隐藏）"),
):
    """检查指定页面在不同数据源中的原始数据"""
```

### 2. 核心实现：InspectService 类

**文件**: `src/regreader/services/inspect.py`（新建）

**类结构**：
```python
class InspectService:
    """页面数据对比服务"""

    def __init__(self):
        self.page_store = PageStore()
        self.fts_db_path = get_settings().fts_db_path
        self.lancedb_path = get_settings().lancedb_path

    def inspect_page(self, reg_id: str, page_num: int) -> InspectResult:
        """获取三种数据源的原始数据"""

    def _get_fts5_data(self, reg_id: str, page_num: int) -> list[dict]:
        """从 FTS5 索引获取数据"""

    def _get_lancedb_data(self, reg_id: str, page_num: int) -> list[dict]:
        """从 LanceDB 索引获取数据"""

    def _get_page_document(self, reg_id: str, page_num: int) -> dict:
        """从 PageStore 获取原始页面数据"""

    def _analyze_differences(self, result: InspectResult) -> DifferenceAnalysis:
        """分析三种数据源的差异"""
```

### 3. 数据模型

**文件**: `src/regreader/services/inspect.py`

```python
class FTS5Record(BaseModel):
    """FTS5 索引记录"""
    content: str
    reg_id: str
    page_num: int
    block_id: str
    chapter_path: list[str]
    content_preview: str

class VectorRecord(BaseModel):
    """向量索引记录"""
    vector: list[float]
    reg_id: str
    page_num: int
    block_id: str
    content: str
    chapter_path: str

class InspectResult(BaseModel):
    """检查结果"""
    reg_id: str
    page_num: int
    fts5_records: list[FTS5Record]
    vector_records: list[VectorRecord]
    page_document: PageDocument
    timestamp: str

class DifferenceAnalysis(BaseModel):
    """差异分析结果"""
    missing_in_fts5: list[str]          # 缺失的 block_id
    missing_in_vector: list[str]        # 缺失的 block_id
    content_mismatches: list[dict]      # 内容不匹配
    total_blocks: int                   # 总内容块数
    indexed_in_fts5: int                # FTS5 索引数
    indexed_in_vector: int              # 向量索引数
```

### 4. 终端显示格式

使用 Rich 库实现以下布局：

```
╭─────────────────────────────────────────────────────────╮
│         页面数据检查: angui_2024 P25                    │
╰─────────────────────────────────────────────────────────╯

📄 原始页面数据 (PageDocument)
┌──────────────┬────────────────────────────────────────┐
│ 字段         │ 值                                      │
├──────────────┼────────────────────────────────────────┤
│ reg_id       │ angui_2024                             │
│ page_num     │ 25                                     │
│ chapter_path │ ['第六章', '事故处理']                │
│ 内容块数量   │ 5                                      │
│ continues... │ false                                  │
└──────────────┴────────────────────────────────────────┘

📊 内容块详情
┌────┬─────────────┬───────┬──────────────────────────┐
│ #  │ Block ID    │ Type  │ Content Preview          │
├────┼─────────────┼───────┼──────────────────────────┤
│ 1  │ text_abc123 │ text  │ 母线失压处理...          │
│ 2  │ text_def456 │ text  │ 系统检查步骤...          │
│ 3  │ tabl_xyz789 │ table │ 表6-2 母线故障处置       │
└────┴─────────────┴───────┴──────────────────────────┘

🔍 FTS5 关键词索引数据
索引记录数: 5
┌─────────────┬──────────────────────────────────────┐
│ Block ID    │ Content Preview (前50字符)           │
├─────────────┼──────────────────────────────────────┤
│ text_abc123 │ 母线失压处理...                      │
│ text_def456 │ 系统检查步骤...                      │
│ tabl_xyz789 │ | 项目 | 处置措施 |...               │
└─────────────┴──────────────────────────────────────┘

🧮 LanceDB 向量索引数据
索引记录数: 5
┌─────────────┬──────────────┬──────────────────────┐
│ Block ID    │ Vector Dim   │ Content Preview      │
├─────────────┼──────────────┼──────────────────────┤
│ text_abc123 │ 512          │ 母线失压处理...      │
│ text_def456 │ 512          │ 系统检查步骤...      │
│ tabl_xyz789 │ 512          │ | 项目 | 处置...     │
└─────────────┴──────────────┴──────────────────────┘

⚠️  差异分析
✓ 所有内容块均已索引到 FTS5
✓ 所有内容块均已索引到 LanceDB
✓ 内容一致性检查通过

或（如果有差异）：
✗ FTS5 缺失内容块: text_xyz999
✗ 向量索引缺失内容块: tabl_abc888
⚠ 内容不匹配:
  - Block ID: text_abc123
    - PageDocument: "母线失压处理步骤..."
    - FTS5: "母线失压处理步骤..." ✓
    - Vector: "母线失压..." ✗ (被截断)

💾 数据已保存至: ./inspect_angui_2024_p25_20251228_153045.json
```

### 5. JSON 输出格式

**文件名**：`inspect_{reg_id}_p{page_num}_{timestamp}.json`

**结构**：
```json
{
  "inspect_result": {
    "reg_id": "angui_2024",
    "page_num": 25,
    "timestamp": "2025-12-28T15:30:45",
    "fts5_records": [...],
    "vector_records": [...],
    "page_document": {...}
  },
  "difference_analysis": {
    "missing_in_fts5": [],
    "missing_in_vector": [],
    "content_mismatches": [],
    "total_blocks": 5,
    "indexed_in_fts5": 5,
    "indexed_in_vector": 5
  }
}
```

### 6. 差异分析逻辑

**步骤**：

1. **内容块完整性检查**
   - 从 PageDocument 提取所有 block_id
   - 检查 FTS5 索引是否包含所有 block_id
   - 检查 LanceDB 索引是否包含所有 block_id
   - 列出缺失的 block_id

2. **内容一致性检查**
   - 对每个 block_id：
     - 比较 PageDocument.content_markdown
     - 比较 FTS5 的 content
     - 比较 LanceDB 的 content（注意 LanceDB 只存储前500字符）
   - 标记不一致的内容块

3. **高亮显示**
   - ✓ 绿色：数据一致
   - ✗ 红色：缺失或不一致
   - ⚠ 黄色：警告（如内容被截断）

---

## 实现步骤

### 步骤 1: 创建 InspectService 类

**文件**: `src/regreader/services/inspect.py`（新建）

**实现内容**：
1. 定义数据模型（FTS5Record, VectorRecord, InspectResult, DifferenceAnalysis）
2. 实现 `_get_fts5_data()` 方法：
   - 连接 SQLite 数据库
   - 查询 `page_meta` 表和 `page_index` 虚拟表
   - 返回记录列表
3. 实现 `_get_lancedb_data()` 方法：
   - 连接 LanceDB
   - 使用 `.where()` 过滤 reg_id 和 page_num
   - 转换为字典列表（隐藏向量数据或提供开关）
4. 实现 `_get_page_document()` 方法：
   - 调用 `PageStore.load_page()`
   - 转换为字典格式
5. 实现 `_analyze_differences()` 方法：
   - 提取所有 block_id 列表
   - 对比三个数据源
   - 生成差异报告
6. 实现 `inspect_page()` 主方法：
   - 调用上述三个获取方法
   - 调用差异分析方法
   - 返回完整结果

### 步骤 2: 创建终端显示模块

**文件**: `src/regreader/services/inspect_display.py`（新建）

**实现内容**：
1. 创建 `InspectDisplay` 类
2. 实现 `display_result()` 方法：
   - 创建标题面板
   - 创建原始页面数据表格
   - 创建内容块详情表格
   - 创建 FTS5 数据表格
   - 创建 LanceDB 数据表格
   - 创建差异分析面板
3. 使用 Rich 组件：
   - `Panel` - 标题和章节
   - `Table` - 数据展示
   - `Tree` - 层级结构（章节路径）
   - `Syntax` - JSON 格式化（如果需要）
   - 颜色标记：`[green]`, `[red]`, `[yellow]`

### 步骤 3: 实现 CLI 命令

**文件**: `src/regreader/cli.py`

**实现内容**：
1. 添加 `@app.command()` 装饰器
2. 定义参数：
   - `reg_id: str` - 必需参数
   - `page_num: int` - 必需参数
   - `--output / -o` - 可选，JSON 输出路径
   - `--show-vectors` - 可选，是否显示向量数据
3. 命令逻辑：
   - 创建 `InspectService` 实例
   - 调用 `inspect_page()`
   - 使用 `InspectDisplay` 显示结果
   - 保存 JSON 文件（如果指定 output 或使用默认路径）

### 步骤 4: 异常处理

**需要处理的异常**：
1. `RegulationNotFoundError` - 规程不存在
2. `PageNotFoundError` - 页面不存在
3. SQLite 连接错误
4. LanceDB 连接错误
5. 表不存在错误（索引未构建）

**处理方式**：
- 捕获异常并显示友好的错误消息
- 对于索引未构建的情况，提示用户先运行 `regreader ingest`

### 步骤 5: 测试

**测试场景**：
1. 正常页面 - 所有数据源都有数据
2. 新页面 - 只有 PageDocument，索引为空
3. 缺失内容块 - 某些 block_id 未被索引
4. 内容不一致 - FTS5 或 LanceDB 的内容与原始不同
5. 跨页表格 - 验证 continues_to_next 标记

---

## 关键文件路径

| 组件 | 文件路径 | 说明 |
|------|---------|------|
| CLI 命令 | `src/regreader/cli.py` | 新增 `inspect` 命令 |
| 核心服务 | `src/regreader/services/inspect.py` | 新建，数据获取和分析 |
| 显示模块 | `src/regreader/services/inspect_display.py` | 新建，终端显示格式化 |
| 数据模型 | `src/regreader/storage/models.py` | 已存在，可能需要导入 |
| 配置 | `src/regreader/config.py` | 读取索引路径配置 |

---

## 代码实现细节

### FTS5 数据查询

```python
import sqlite3
import json

def _get_fts5_data(self, reg_id: str, page_num: int) -> list[FTS5Record]:
    """从 FTS5 索引获取数据"""
    conn = sqlite3.connect(str(self.fts_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询 page_meta 表
    cursor.execute("""
        SELECT * FROM page_meta
        WHERE reg_id = ? AND page_num = ?
    """, (reg_id, page_num))

    records = []
    for row in cursor.fetchall():
        chapter_path = json.loads(row['chapter_path']) if row['chapter_path'] else []
        records.append(FTS5Record(
            content=self._get_fts_content(cursor, row['rowid']),  # 从虚拟表获取
            reg_id=row['reg_id'],
            page_num=row['page_num'],
            block_id=row['block_id'],
            chapter_path=chapter_path,
            content_preview=row['content_preview']
        ))

    conn.close()
    return records

def _get_fts_content(self, cursor, rowid: int) -> str:
    """从 FTS5 虚拟表获取完整内容"""
    cursor.execute("""
        SELECT content FROM page_index WHERE rowid = ?
    """, (rowid,))
    row = cursor.fetchone()
    return row['content'] if row else ""
```

### LanceDB 数据查询

```python
import lancedb

def _get_lancedb_data(self, reg_id: str, page_num: int, show_vectors: bool = False) -> list[VectorRecord]:
    """从 LanceDB 索引获取数据"""
    db = lancedb.connect(str(self.lancedb_path))

    try:
        table = db.open_table("page_vectors")
    except Exception as e:
        logger.warning(f"向量表不存在: {e}")
        return []

    # 查询指定页面的向量记录
    results = table.search().where(
        f"reg_id = '{reg_id}' AND page_num = {page_num}"
    ).to_pandas()

    records = []
    for _, row in results.iterrows():
        vector = row['vector'] if show_vectors else []  # 可选显示向量
        records.append(VectorRecord(
            vector=vector,
            reg_id=row['reg_id'],
            page_num=row['page_num'],
            block_id=row['block_id'],
            content=row['content'],
            chapter_path=row['chapter_path']
        ))

    return records
```

### 差异分析实现

```python
def _analyze_differences(self, result: InspectResult) -> DifferenceAnalysis:
    """分析三种数据源的差异"""

    # 1. 提取所有 block_id
    page_block_ids = {block.block_id for block in result.page_document.content_blocks}
    fts5_block_ids = {rec.block_id for rec in result.fts5_records}
    vector_block_ids = {rec.block_id for rec in result.vector_records}

    # 2. 检查缺失
    missing_in_fts5 = list(page_block_ids - fts5_block_ids)
    missing_in_vector = list(page_block_ids - vector_block_ids)

    # 3. 内容一致性检查
    content_mismatches = []
    for block in result.page_document.content_blocks:
        block_id = block.block_id
        page_content = block.content_markdown.strip()

        # FTS5 内容
        fts5_match = next((r for r in result.fts5_records if r.block_id == block_id), None)
        fts5_content = fts5_match.content.strip() if fts5_match else None

        # 向量内容
        vector_match = next((r for r in result.vector_records if r.block_id == block_id), None)
        vector_content = vector_match.content.strip() if vector_match else None

        # 对比
        if fts5_content and fts5_content != page_content:
            content_mismatches.append({
                'block_id': block_id,
                'source': 'FTS5',
                'page_content': page_content[:100],
                'indexed_content': fts5_content[:100]
            })

        if vector_content and vector_content != page_content[:500]:  # 向量索引截断到500字符
            if len(page_content) <= 500:  # 只在完整内容小于500时才算不匹配
                content_mismatches.append({
                    'block_id': block_id,
                    'source': 'LanceDB',
                    'page_content': page_content[:100],
                    'indexed_content': vector_content[:100]
                })

    return DifferenceAnalysis(
        missing_in_fts5=missing_in_fts5,
        missing_in_vector=missing_in_vector,
        content_mismatches=content_mismatches,
        total_blocks=len(page_block_ids),
        indexed_in_fts5=len(fts5_block_ids),
        indexed_in_vector=len(vector_block_ids)
    )
```

---

## 预期效果

### 命令调用示例

```bash
# 基本用法
regreader inspect angui_2024 25

# 指定输出文件
regreader inspect angui_2024 25 --output ./debug/page25.json

# 显示向量数据
regreader inspect angui_2024 25 --show-vectors
```

### 终端输出示例（正常情况）

```
╭─────────────────────────────────────────────────────────╮
│         页面数据检查: angui_2024 P25                    │
╰─────────────────────────────────────────────────────────╯

📄 原始页面数据 (PageDocument)
  规程: angui_2024
  页码: 25
  章节: 第六章 > 事故处理 > 母线故障
  内容块数量: 5

📊 内容块详情
┌────┬─────────────┬───────┬──────────────────────────┐
│ #  │ Block ID    │ Type  │ Content Preview          │
├────┼─────────────┼───────┼──────────────────────────┤
│ 1  │ text_abc123 │ text  │ 母线失压处理...          │
│ 2  │ text_def456 │ text  │ 系统检查步骤...          │
│ 3  │ tabl_xyz789 │ table │ 表6-2 母线故障处置       │
│ 4  │ text_ghi012 │ text  │ 注意事项...              │
│ 5  │ list_jkl345 │ list  │ - 第一步\n- 第二步...    │
└────┴─────────────┴───────┴──────────────────────────┘

🔍 FTS5 关键词索引 (5 条记录)
✓ 所有内容块均已索引

🧮 LanceDB 向量索引 (5 条记录)
✓ 所有内容块均已索引

✅ 数据一致性检查通过
  - 内容块完整性: ✓
  - FTS5 内容一致: ✓
  - LanceDB 内容一致: ✓

💾 数据已保存至: ./inspect_angui_2024_p25_20251228_153045.json
```

### 终端输出示例（发现差异）

```
⚠️  差异分析

✗ FTS5 缺失内容块 (1):
  - list_jkl345 (list 类型)

⚠ 向量索引内容被截断 (1):
  - tabl_xyz789: 原始 1250 字符 → 索引 500 字符

📊 索引覆盖率:
  - 原始内容块: 5
  - FTS5 索引: 4 (80%)
  - LanceDB 索引: 5 (100%)

💾 详细数据已保存至: ./inspect_angui_2024_p25_20251228_153045.json
```

---

## 注意事项

1. **向量显示控制**：
   - 默认不显示 512 维向量数据（太长）
   - 使用 `--show-vectors` 选项时才显示

2. **内容截断处理**：
   - LanceDB 只存储前 500 字符
   - 对比时需要考虑这个限制，避免误报

3. **性能考虑**：
   - FTS5 查询使用索引，速度快
   - LanceDB 使用 `.where()` 过滤，也较快
   - 单页数据量小，无需额外优化

4. **错误处理**：
   - 索引未构建时给出友好提示
   - 页面不存在时显示清晰错误信息

5. **JSON 文件位置**：
   - 默认保存到当前目录
   - 可通过 `--output` 指定路径
   - 文件名包含时间戳，避免覆盖

---

## 完成标准

✅ CLI 命令成功集成到 `regreader` 工具
✅ 终端显示美观、信息完整
✅ JSON 文件正确保存
✅ 差异分析准确、高亮清晰
✅ 异常处理完善
✅ 代码符合项目规范（类型注解、文档字符串）

---

## 备注

本实现计划将保存至 `docs/dev/INSPECT_COMMAND_PLAN.md`，开始实施前请确认计划无误。
