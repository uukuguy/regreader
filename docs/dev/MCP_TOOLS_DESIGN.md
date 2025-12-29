# GridCode MCP工具集扩展设计方案

## 目标

设计并实施支持智能体"翻书"多步推理的MCP工具集，使Agent能够灵活、快速、准确地进行多跳检索，构建回答规程问题的有效上下文。

---

## 现有工具 (7个)

| 工具 | 功能 | 文件位置 |
|------|------|----------|
| `get_toc` | 获取目录树 | tools.py:44 |
| `smart_search` | 混合检索 | tools.py:60 |
| `read_page_range` | 读取页面范围 | tools.py:114 |
| `list_regulations` | 列出所有规程 | tools.py:162 |
| `get_chapter_structure` | 获取章节结构 | tools.py:172 |
| `get_page_chapter_info` | 获取页面章节信息 | tools.py:221 |
| `read_chapter_content` | 读取章节内容 | tools.py:278 |

---

## 新增工具 (8个)

### Phase 1: 核心多跳工具 (P0)

#### 1. `lookup_annotation` - 注释查找
```python
def lookup_annotation(
    reg_id: str,
    annotation_id: str,       # 如 "注1", "方案A"
    page_hint: int | None = None,
) -> dict
```
- **用途**: 查找表格单元格中的"见注1"等引用
- **返回**: annotation_id, content, page_num, related_blocks, source
- **实现**: 遍历页面annotations列表，支持变体匹配（注1/注①/注一）

#### 2. `search_tables` - 表格搜索
```python
def search_tables(
    query: str,
    reg_id: str,
    chapter_scope: str | None = None,
    search_cells: bool = True,
    limit: int = 10,
) -> list[dict]
```
- **用途**: 按标题或单元格内容搜索表格
- **返回**: table_id, caption, page_num, row_count, col_count, col_headers, is_truncated, match_type, source
- **实现**: 利用 `smart_search(block_types=["table"])` + TableMeta二次过滤

#### 3. `resolve_reference` - 交叉引用解析
```python
def resolve_reference(
    reg_id: str,
    reference_text: str,      # 如 "见第六章", "参见表6-2", "见2.1.4"
) -> dict
```
- **用途**: 解析并解决"见第X章"、"参见表Y"等交叉引用
- **返回**: reference_type, parsed_target, resolved, target_location, preview, source
- **实现**: 正则模式匹配 + 调用相应查找逻辑

### Phase 2: 上下文工具 (P1)

#### 4. `search_annotations` - 注释搜索
```python
def search_annotations(
    reg_id: str,
    pattern: str | None = None,
    annotation_type: str | None = None,  # "note"(注x) / "plan"(方案x)
) -> list[dict]
```
- **用途**: 搜索所有匹配的注释
- **返回**: 注释列表 (annotation_id, content截断, page_num, source)

#### 5. `get_table_by_id` - 获取完整表格
```python
def get_table_by_id(
    reg_id: str,
    table_id: str,
    include_merged: bool = True,
) -> dict
```
- **用途**: 按ID获取完整表格（含跨页合并）
- **返回**: 完整表格数据 + markdown + 相关注释

#### 6. `get_block_with_context` - 获取块上下文
```python
def get_block_with_context(
    reg_id: str,
    block_id: str,
    context_blocks: int = 2,
) -> dict
```
- **用途**: 读取指定块及其前后上下文
- **返回**: target_block, before_blocks, after_blocks, page_annotations

### Phase 3: 发现工具 (P2)

#### 7. `find_similar_content` - 相似内容发现
```python
def find_similar_content(
    reg_id: str,
    query_text: str | None = None,
    source_block_id: str | None = None,
    limit: int = 5,
    exclude_same_page: bool = True,
) -> list[dict]
```
- **用途**: 发现语义相似的内容
- **实现**: 直接使用向量索引

#### 8. `compare_sections` - 章节比较
```python
def compare_sections(
    reg_id: str,
    section_a: str,
    section_b: str,
    include_tables: bool = True,
) -> dict
```
- **用途**: 并排比较两个章节
- **实现**: 调用 `read_chapter_content` + 结构分析

---

## 多跳推理模式示例

### 模式1: 表格查找 + 注释追踪
```
Query: "110kV母线失压怎么处理?"

1. get_toc() → 锁定"第六章 事故处理"
2. search_tables("母线失压", chapter_scope="第六章") → 表6-2, P85
3. get_table_by_id("table_xxx") → 发现单元格含"见注1"
4. lookup_annotation("注1", page_hint=85) → 获取注释内容
5. 生成答案 + 来源引用
```

### 模式2: 交叉引用跟踪
```
Query: "发电机保护整定值规定?"

1. smart_search("发电机保护整定值") → P42, "应符合第3章规定"
2. resolve_reference("第3章相关规定") → section_number="3", page_range=[30,45]
3. read_chapter_content("3") → 获取完整章节
4. 生成多来源答案
```

### 模式3: 章节比较
```
Query: "比较一类和二类电压等级的维护要求"

1. smart_search("一类电压等级 维护") → section_number="4.1.1"
2. smart_search("二类电压等级 维护") → section_number="4.1.2"
3. compare_sections("4.1.1", "4.1.2") → 并排比较
4. 生成结构化比较答案
```

---

## 实现顺序

### Step 1: 新增异常类型
**文件**: `src/grid_code/exceptions.py`
```python
class AnnotationNotFoundError(GridCodeError): ...
class TableNotFoundError(GridCodeError): ...
class ReferenceResolutionError(GridCodeError): ...
```

### Step 2: 实现Phase 1工具 (P0)
**文件**: `src/grid_code/mcp/tools.py`
- 添加 `lookup_annotation()` 方法
- 添加 `search_tables()` 方法
- 添加 `resolve_reference()` 方法 + `ReferenceResolver` 辅助类

### Step 3: 注册MCP工具
**文件**: `src/grid_code/mcp/server.py`
- 为每个新工具添加 `@mcp.tool()` 装饰器函数
- 遵循现有错误处理模式

### Step 4: 实现Phase 2工具 (P1)
**文件**: `src/grid_code/mcp/tools.py`
- 添加 `search_annotations()` 方法
- 添加 `get_table_by_id()` 方法
- 添加 `get_block_with_context()` 方法

### Step 5: 实现Phase 3工具 (P2)
**文件**: `src/grid_code/mcp/tools.py`
- 添加 `find_similar_content()` 方法
- 添加 `compare_sections()` 方法

### Step 6: 更新系统提示词
**文件**: `src/grid_code/agents/prompts.py`
- 添加新工具说明
- 添加多跳推理协议指南

---

## 关键文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/exceptions.py` | 新增3个异常类 |
| `src/grid_code/mcp/tools.py` | 新增8个工具方法 + ReferenceResolver类 |
| `src/grid_code/mcp/server.py` | 注册8个新MCP工具 |
| `src/grid_code/agents/prompts.py` | 更新系统提示词 |

---

## 设计约束

1. **保持页面哲学**: 所有工具通过页面访问数据，不引入独立索引
2. **统一错误处理**: 使用 `try-except GridCodeError` + `{"error": str(e)}` 模式
3. **来源追溯**: 所有返回结果必须包含 `source` 字段
4. **异步兼容**: 工具方法保持同步（与现有一致），MCP层可异步包装
5. **向后兼容**: 现有工具接口不变

---

## 测试计划

每个工具实现后进行单元测试：
- `tests/dev/test_lookup_annotation.py`
- `tests/dev/test_search_tables.py`
- `tests/dev/test_resolve_reference.py`

集成测试：
- `tests/dev/test_multi_hop_patterns.py` - 测试完整的多跳推理流程
