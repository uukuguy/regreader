# 章节导出功能修复

## 问题描述

原有的章节导出功能（`export_chapter`）是按**页面**导出的，会导出章节所在页面的**所有内容**，而不仅仅是指定章节的内容。

**问题示例**：
- 导出章节 "2.1.4" 时，如果该章节从第10页开始到第15页结束
- 原实现会导出第10-15页的**完整内容**
- 这意味着如果第15页还包含其他章节（如 "2.1.5"）的内容，也会被错误地包含进来

## 解决方案

### 核心改进

使用 `ContentBlock.chapter_node_id` 字段进行**精确过滤**，只导出属于指定章节的内容块。

### 实现细节

#### 1. 新增方法

**`_collect_chapter_blocks()`**
- 替代原有的 `_collect_chapter_pages()`
- 基于 `chapter_node_id` 精确过滤内容块
- 返回：`(内容块列表, 涉及的页码集合)`

**`_collect_descendant_node_ids()`**
- 递归收集所有子孙节点ID
- 支持 `include_children` 参数

**`_build_markdown_from_blocks()`**
- 从内容块列表构建 Markdown
- 支持页码标记、YAML frontmatter 等配置

**`_calculate_stats_from_blocks()`**
- 从内容块计算统计信息
- 统计页数、块数、表格数等

#### 2. 修改方法

**`export_chapter()`**
- 调用新的 `_collect_chapter_blocks()` 方法
- 使用 `_build_markdown_from_blocks()` 生成内容
- 保持向后兼容的 API

#### 3. 页码提取逻辑

修复了 `block_id` 的页码提取逻辑：
- `block_id` 格式：`{reg_id}_{page_num}_{block_num}`
- 例如：`angui_2024_10_5` → 页码是倒数第二个部分 `10`
- 使用 `parts[-2]` 而不是 `parts[1]` 来提取页码

## 测试验证

创建了完整的单元测试套件（`tests/services/test_export_chapter.py`）：

1. **test_collect_chapter_blocks_without_children**
   - 验证不包含子章节时的内容块收集

2. **test_collect_chapter_blocks_with_children**
   - 验证包含子章节时的内容块收集
   - 确保不包含其他章节的内容

3. **test_collect_descendant_node_ids**
   - 验证子孙节点ID的递归收集

4. **test_build_markdown_from_blocks**
   - 验证从内容块构建 Markdown 的正确性
   - 验证页码标记的正确插入

5. **test_calculate_stats_from_blocks**
   - 验证统计信息的正确计算

**测试结果**：✅ 5/5 通过

## 向后兼容性

- 保留了原有的 `_collect_chapter_pages()` 方法（标记为已废弃）
- `export_chapter()` 的 API 保持不变
- 所有配置选项（`ExportConfig`）继续有效

## 使用示例

```python
from regreader.services.export_service import ExportService
from regreader.storage.models import ExportConfig

service = ExportService()

# 导出单个章节（不包含子章节）
result = service.export_chapter(
    reg_id="angui_2024",
    section_number="2.1.4",
    include_children=False,
)

# 导出章节及其所有子章节
result = service.export_chapter(
    reg_id="angui_2024",
    section_number="2.1",
    include_children=True,
    config=ExportConfig(
        include_page_markers=True,
        include_yaml_frontmatter=True,
    ),
)

print(f"导出成功: {result.output_path}")
print(f"统计: {result.stats}")
```

## CLI 使用

```bash
# 导出指定章节（只包含该章节内容）
regreader export-chapter angui_2024 "2.1.4" -o output.md

# 导出章节及其子章节
regreader export-chapter angui_2024 "2.1" --include-children -o output.md
```

## 技术要点

### 1. 内容块关联

每个 `ContentBlock` 都有 `chapter_node_id` 字段，指向其所属的章节节点：

```python
class ContentBlock(BaseModel):
    block_id: str
    block_type: Literal["text", "table", "heading", "list", "section_content"]
    content_markdown: str
    chapter_node_id: str | None  # 关键字段
    ...
```

### 2. 章节树遍历

使用 `DocumentStructure` 的章节树结构：

```python
class ChapterNode(BaseModel):
    node_id: str
    section_number: str
    title: str
    level: int
    page_num: int
    parent_id: str | None
    children_ids: list[str]  # 子节点ID列表
    ...
```

### 3. 精确过滤算法

```python
# 收集目标章节节点ID
target_node_ids = {chapter_node.node_id}
if include_children:
    target_node_ids.update(self._collect_descendant_node_ids(chapter_node, doc_structure))

# 遍历页面范围，过滤匹配的内容块
for page_num in range(start_page, end_page + 1):
    page = self.page_store.load_page(reg_id, page_num)
    for block in page.content_blocks:
        if block.chapter_node_id in target_node_ids:
            blocks.append(block)
```

## 性能考虑

- **优化点**：只加载必要的页面范围（`start_page` 到 `end_page`）
- **内存效率**：逐页加载和过滤，不需要一次性加载所有页面
- **时间复杂度**：O(n * m)，其中 n 是页面数，m 是每页的内容块数

## 后续优化建议

1. **缓存优化**
   - 缓存 `DocumentStructure` 避免重复加载
   - 缓存子孙节点ID集合

2. **并行加载**
   - 使用异步IO并行加载多个页面
   - 适用于大型文档的章节导出

3. **增量导出**
   - 支持只导出修改过的章节
   - 添加版本控制和差异比较

4. **注释支持**
   - 当前版本暂不支持注释汇总
   - 需要从页面加载注释并关联到内容块

## 相关文件

- `src/regreader/services/export_service.py` - 导出服务实现
- `src/regreader/storage/models.py` - 数据模型定义
- `tests/services/test_export_chapter.py` - 单元测试
- `docs/dev/CHAPTER_EXPORT_FIX.md` - 本文档

## 修改日期

2026-01-26
