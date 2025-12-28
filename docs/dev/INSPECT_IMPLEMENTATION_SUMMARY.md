# INSPECT 命令实现总结

## 概述

成功实现 `grid-code inspect` 命令，用于对比显示指定页面在三种数据源中的原始数据：
1. FTS5 关键词索引（SQLite 全文检索）
2. LanceDB 向量索引（语义检索）
3. PageStore 原始页面文档（JSON 文件）

## 实现日期

2025-12-28

## 实现内容

### 1. 核心服务模块

**文件**：`src/grid_code/services/inspect.py`（354 行）

**类定义**：
- `FTS5Record`：FTS5 索引记录模型
- `VectorRecord`：向量索引记录模型
- `InspectResult`：检查结果模型
- `DifferenceAnalysis`：差异分析结果模型
- `InspectService`：核心服务类

**主要方法**：
```python
def inspect_page(reg_id: str, page_num: int, show_vectors: bool) -> tuple[InspectResult, DifferenceAnalysis]
    """检查指定页面的数据"""

def _get_fts5_data(reg_id: str, page_num: int) -> list[FTS5Record]
    """从 FTS5 索引获取数据"""

def _get_lancedb_data(reg_id: str, page_num: int, show_vectors: bool) -> list[VectorRecord]
    """从 LanceDB 索引获取数据"""

def _analyze_differences(result: InspectResult) -> DifferenceAnalysis
    """分析三种数据源的差异"""

def save_json(result: InspectResult, analysis: DifferenceAnalysis, output_path: Path | None) -> Path
    """保存检查结果为 JSON 文件"""
```

**差异分析逻辑**：
1. 提取所有 block_id 集合
2. 检查 FTS5 和 LanceDB 索引的完整性
3. 内容一致性对比（考虑 LanceDB 500 字符截断）
4. 生成差异报告

### 2. 显示模块

**文件**：`src/grid_code/services/inspect_display.py`（261 行）

**类定义**：
- `InspectDisplay`：Rich 格式化终端输出

**主要方法**：
```python
def display_result(result: InspectResult, analysis: DifferenceAnalysis) -> None
    """显示检查结果（Rich 格式化）"""

def _display_title(result: InspectResult) -> None
    """显示标题面板"""

def _display_page_document(result: InspectResult) -> None
    """显示原始页面数据"""

def _display_content_blocks(result: InspectResult) -> None
    """显示内容块详情表格"""

def _display_fts5_data(result: InspectResult, analysis: DifferenceAnalysis) -> None
    """显示 FTS5 索引数据"""

def _display_lancedb_data(result: InspectResult, analysis: DifferenceAnalysis) -> None
    """显示 LanceDB 向量索引数据"""

def _display_difference_analysis(analysis: DifferenceAnalysis) -> None
    """显示差异分析"""

def display_save_message(file_path: str) -> None
    """显示保存成功消息"""
```

**显示特性**：
- 美观的 Rich 标题面板
- 彩色表格展示内容块、FTS5 和 LanceDB 数据
- 差异高亮（绿色 = 正常，红色 = 缺失，黄色 = 警告）
- 索引覆盖率统计

### 3. CLI 命令集成

**文件**：`src/grid_code/cli.py`

**命令定义**：
```python
@app.command()
def inspect(
    reg_id: str = typer.Argument(..., help="规程标识"),
    page_num: int = typer.Argument(..., help="页码"),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
    show_vectors: bool = typer.Option(False, "--show-vectors", help="显示向量数据（默认隐藏）"),
):
    """检查指定页面在不同数据源中的原始数据"""
```

**异常处理**：
- `RegulationNotFoundError`：规程不存在
- `PageNotFoundError`：页面不存在
- 通用异常捕获和友好错误提示

## 使用方法

### 基本用法

```bash
# 检查页面数据
grid-code inspect angui_2024 25

# 或使用 python 模块方式
python -m grid_code.cli inspect angui_2024 25
```

### 高级用法

```bash
# 指定 JSON 输出路径
grid-code inspect angui_2024 25 --output ./debug/page25.json

# 显示向量数据（512 维）
grid-code inspect angui_2024 25 --show-vectors

# 组合使用
grid-code inspect angui_2024 25 -o ./output.json --show-vectors
```

### Makefile 快捷方式

```bash
# 使用默认参数
make inspect

# 指定规程和页码
make inspect REG_ID=angui_2024 PAGE_NUM=25

# 指定输出文件
make inspect REG_ID=angui_2024 PAGE_NUM=25 OUTPUT=./debug.json
```

## 输出示例

### 终端输出

```
╭──────────────────────────────────────────────────────────────────────────────╮
│                                                                              │
│  页面数据检查: angui_2024 P1                                                 │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯

📄 原始页面数据 (PageDocument)
  规程: angui_2024
  页码: 1
  章节: 无章节信息
  内容块数量: 2

📊 内容块详情
┏━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┃ #    ┃ Block ID        ┃ Type       ┃ Content Preview
┡━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│ 1    │ text_71730adb   │ text       │ 2024 年国调直调安全自动装置...
│ 2    │ text_6def948a   │ text       │ 国家电力调度控制中心 2024 年 7 月...
└──────┴─────────────────┴────────────┴─────────────────────────────────────────

🔍 FTS5 关键词索引 (2 条记录)
  ✓ 所有内容块均已索引

🧮 LanceDB 向量索引 (2 条记录)
  ✓ 所有内容块均已索引

⚠️  差异分析
✅ 数据一致性检查通过
  - 内容块完整性: ✓
  - FTS5 内容一致: ✓
  - LanceDB 内容一致: ✓

📊 索引覆盖率
  原始内容块: 2
  FTS5 索引: 2 (100.0%)
  LanceDB 索引: 2 (100.0%)

💾 数据已保存至: inspect_angui_2024_p1_20251228_205250.json
```

### JSON 输出格式

```json
{
  "inspect_result": {
    "reg_id": "angui_2024",
    "page_num": 25,
    "timestamp": "2025-12-28T20:52:50",
    "fts5_records": [...],
    "vector_records": [...],
    "page_document": {...}
  },
  "difference_analysis": {
    "missing_in_fts5": [],
    "missing_in_vector": ["text_xyz123", "text_abc456"],
    "content_mismatches": [],
    "total_blocks": 86,
    "indexed_in_fts5": 86,
    "indexed_in_vector": 9
  }
}
```

## 测试结果

### 测试用例 1：页面 1

**结果**：✅ 数据完全一致
- 原始内容块：2 个
- FTS5 索引：2 个（100%）
- LanceDB 索引：2 个（100%）
- 差异：无

### 测试用例 2：页面 25

**结果**：⚠️ 发现严重问题
- 原始内容块：86 个
- FTS5 索引：86 个（100%）
- **LanceDB 索引：仅 9 个（10.5%）**
- 差异：缺失 77 个内容块的向量索引

**问题分析**：
页面 25 包含大量短内容块（单个字符或简短文本），这些内容被 LanceDB 索引过滤掉了（`index_page()` 方法中 `len(content) < 10` 的过滤逻辑）。

## 技术要点

### 1. SQLite FTS5 查询

```python
# 查询 page_meta 表（包含 rowid）
cursor.execute("""
    SELECT rowid as id, * FROM page_meta
    WHERE reg_id = ? AND page_num = ?
""", (reg_id, page_num))

# 从 FTS5 虚拟表获取完整内容
cursor.execute("""
    SELECT content FROM page_index WHERE rowid = ?
""", (rowid,))
```

### 2. LanceDB 查询

```python
# 获取全表数据并过滤
results = table.to_pandas()
results = results[
    (results["reg_id"] == reg_id) & (results["page_num"] == page_num)
]
```

**注意**：不能使用 `table.search().where()` 因为 `.search()` 需要向量参数。

### 3. 差异分析算法

```python
# 1. 提取 block_id 集合
page_block_ids = {block.block_id for block in page.content_blocks}
fts5_block_ids = {rec.block_id for rec in fts5_records}
vector_block_ids = {rec.block_id for rec in vector_records}

# 2. 计算缺失
missing_in_fts5 = list(page_block_ids - fts5_block_ids)
missing_in_vector = list(page_block_ids - vector_block_ids)

# 3. 内容一致性检查（考虑 LanceDB 500 字符截断）
if vector_content != expected_content:
    if len(page_content) <= 500:  # 只在完整内容小于500时才算不匹配
        content_mismatches.append(...)
```

## 文件结构

```
src/grid_code/services/
├── __init__.py              # 空模块初始化文件
├── inspect.py               # 核心服务（354 行）
└── inspect_display.py       # Rich 显示（261 行）

src/grid_code/cli.py         # CLI 命令集成（新增 inspect 命令）
```

## 代码规范遵循

- ✅ 使用 Python 3.12+ 类型注解（`list[str]`, `str | None`）
- ✅ 使用 Pydantic v2 BaseModel
- ✅ 使用 `model_dump()` 而非 `dict()`
- ✅ 使用 `Field()` 添加字段描述
- ✅ 使用 loguru 记录日志
- ✅ 使用自定义异常类（`RegulationNotFoundError`, `PageNotFoundError`）
- ✅ 完整的文档字符串

## 已知限制

1. **LanceDB 内容截断**：向量索引只存储前 500 字符，差异分析已考虑此限制
2. **短内容过滤**：`len(content) < 10` 的内容块不会被向量索引（设计行为）
3. **向量数据显示**：默认隐藏 512 维向量数据，使用 `--show-vectors` 显示

## 后续优化建议

1. **性能优化**：对于大量页面的批量检查，可以添加并行处理
2. **增强过滤**：添加按内容类型过滤（只检查 text/table/list 等）
3. **导出格式**：支持 CSV、HTML 等其他导出格式
4. **自动修复**：发现缺失索引时自动重建
5. **历史对比**：支持对比不同时间点的索引状态

## 相关文档

- [页面存储分析文档](./PAGE_STORAGE_ANALYSIS.md)
- [Inspect 命令实现计划](./INSPECT_COMMAND_PLAN.md)
- [项目设计文档](../main/DESIGN_DOCUMENT.md)

## 总结

`grid-code inspect` 命令成功实现，提供了：
1. **数据完整性检查**：验证三种数据源的一致性
2. **直观可视化**：Rich 格式化的终端输出
3. **详细分析报告**：JSON 格式的完整数据导出
4. **问题发现能力**：在测试中成功发现了真实的索引覆盖率问题

该工具对于调试索引问题、验证数据一致性和系统维护具有重要价值。
