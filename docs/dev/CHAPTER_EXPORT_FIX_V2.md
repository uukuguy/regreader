# 章节导出功能修复 V2

## 问题描述

原有的章节导出功能存在两个问题：

1. **按页导出**：导出章节所在页面的所有内容，而不仅仅是指定章节的内容
2. **block_id 格式错误假设**：代码假设 `block_id` 格式为 `{reg_id}_{page_num}_{block_num}`，但实际格式是 `{block_type}_{hash}`

## 解决方案

### 核心改进

1. **内容块与页码关联**：修改 `_collect_chapter_blocks()` 返回 `(ContentBlock, page_num)` 元组列表
2. **双重过滤策略**：
   - 优先使用 `chapter_node_id` 精确匹配
   - 降级使用 `chapter_path` 路径匹配（用于 `chapter_node_id` 为 None 的情况）

### 实现细节

#### 1. 修改的方法签名

```python
# 修改前
def _collect_chapter_blocks(...) -> tuple[list[ContentBlock], set[int]]:
    ...

# 修改后
def _collect_chapter_blocks(...) -> tuple[list[tuple[ContentBlock, int]], set[int]]:
    ...
```

#### 2. 新增降级方案

```python
def _block_belongs_to_chapter(
    self,
    block: ContentBlock,
    chapter_node: ChapterNode,
    doc_structure: DocumentStructure,
    include_children: bool,
) -> bool:
    """检查内容块是否属于指定章节（降级方案）"""
    if not block.chapter_path:
        return False

    target_section = chapter_node.section_number

    for path_item in block.chapter_path:
        if path_item.startswith(target_section):
            if include_children:
                return True
            else:
                return path_item.startswith(f"{target_section} ") or path_item == target_section

    return False
```

#### 3. 修改的辅助方法

**`_build_markdown_from_blocks()`**
- 参数改为 `blocks_with_pages: list[tuple[ContentBlock, int]]`
- 直接使用元组中的页码，无需从 `block_id` 提取

**`_calculate_stats_from_blocks()`**
- 参数改为 `blocks_with_pages: list[tuple[ContentBlock, int]]`
- 从元组中提取页码统计

## 测试验证

### 单元测试

所有测试通过 ✅ (5/5)：
- `test_collect_chapter_blocks_without_children`
- `test_collect_chapter_blocks_with_children`
- `test_collect_descendant_node_ids`
- `test_build_markdown_from_blocks`
- `test_calculate_stats_from_blocks`

### 实际导出测试

```bash
make export-chapter REG_ID=wengui_2023 CHAPTER=6.1.1.2
```

**结果**：
- ✅ 导出成功
- ✅ 只包含指定章节内容
- ✅ 页码范围准确（84-86页）
- ✅ 统计信息正确（3页，11块，3表格）

## 使用示例

```python
from regreader.services.export_service import ExportService

service = ExportService()

# 导出单个章节
result = service.export_chapter(
    reg_id="wengui_2023",
    section_number="6.1.1.2",
    include_children=False,
)

print(f"导出成功: {result.output_path}")
print(f"统计: {result.stats}")
```

## 技术要点

### 1. 双重过滤策略

```python
for block in page.content_blocks:
    # 策略1: 精确匹配（优先）
    if block.chapter_node_id is not None:
        if block.chapter_node_id in target_node_ids:
            blocks_with_pages.append((block, page_num))
    else:
        # 策略2: 路径匹配（降级）
        if self._block_belongs_to_chapter(block, chapter_node, doc_structure, include_children):
            blocks_with_pages.append((block, page_num))
```

### 2. 页码关联

不再依赖 `block_id` 格式，而是在收集时直接关联页码：

```python
blocks_with_pages: list[tuple[ContentBlock, int]] = []
for page_num in range(start_page, end_page + 1):
    page = self.page_store.load_page(reg_id, page_num)
    for block in page.content_blocks:
        if matches:
            blocks_with_pages.append((block, page_num))  # 直接关联页码
```

## 向后兼容性

- ✅ `export_chapter()` API 保持不变
- ✅ 所有配置选项继续有效
- ✅ 保留了原有的 `_collect_chapter_pages()` 方法

## 相关文件

- `src/regreader/services/export_service.py` - 核心实现
- `tests/services/test_export_chapter.py` - 单元测试
- `docs/dev/CHAPTER_EXPORT_FIX.md` - V1 文档
- `docs/dev/CHAPTER_EXPORT_FIX_V2.md` - 本文档（V2）

## 修改日期

2026-01-26
