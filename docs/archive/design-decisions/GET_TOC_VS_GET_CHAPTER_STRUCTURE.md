# get_toc vs get_chapter_structure 工具对比分析

> 文档创建日期: 2026-01-02
> 版本: 1.0
> 分支: dev

## 概述

`get_toc` 和 `get_chapter_structure` 是 RegReader 系统中两个用于获取规程结构信息的 MCP 工具。虽然它们都返回章节相关信息，但在设计意图、数据结构和使用场景上有明显区别。

---

## 核心区别速览

| 维度 | `get_toc` | `get_chapter_structure` |
|------|-----------|------------------------|
| **定位** | 面向用户的目录浏览 | 面向开发者的结构查询 |
| **设计哲学** | "快速浏览，了解大局" | "深入分析，获取细节" |
| **数据源** | `TocTree` 模型 | `DocumentStructure` 模型 |
| **返回内容** | 完整目录树（嵌套结构） | 根节点列表 + 统计信息（扁平） |
| **数据结构** | 层级嵌套 | 扁平化根节点数组 |
| **优先级** | 高（1）- 通常作为起点 | 中（2）- 深入分析时使用 |
| **CLI 展示** | 层级树形结构（Rich Tree） | 扁平表格（Rich Table） |
| **前置要求** | 无 | 建议先调用 `get_toc` |
| **后续工具** | `smart_search`, `read_chapter_content` | `read_chapter_content` |
| **典型用户** | 终端用户、Agent 初探索 | Agent 深度分析、系统内部调用 |

---

## 函数签名对比

### `get_toc`

**文件位置**: `src/regreader/mcp/tools.py`

```python
def get_toc(self, reg_id: str) -> dict:
    """获取规程目录树

    Args:
        reg_id: 规程标识（如 'angui_2024'）

    Returns:
        目录树结构，包含标题、页码范围等信息
    """
    toc = self.page_store.load_toc(reg_id)
    return toc.model_dump()
```

**实现特点**:
- ✅ **最简单的实现** - 直接加载预存的 `TocTree` 模型
- ✅ **无额外逻辑** - 一行代码加载，一行代码序列化
- ✅ **性能高** - 直接返回缓存数据

### `get_chapter_structure`

**文件位置**: `src/regreader/mcp/tools.py`

```python
def get_chapter_structure(self, reg_id: str) -> dict:
    """获取完整章节结构

    Args:
        reg_id: 规程标识

    Returns:
        章节结构信息，包含:
        - reg_id: 规程标识
        - total_chapters: 章节总数
        - root_nodes: 顶级章节列表
    """
    # 1. 检查规程是否存在
    if not self.page_store.exists(reg_id):
        raise RegulationNotFoundError(reg_id)

    # 2. 加载文档结构
    doc_structure = self.page_store.load_document_structure(reg_id)

    # 3. 向后兼容处理
    if doc_structure is None:
        return {
            "reg_id": reg_id,
            "total_chapters": 0,
            "root_nodes": [],
            "message": "文档结构未生成，请重新入库以生成章节结构",
        }

    # 4. 提取根节点信息
    root_nodes = []
    for node_id in doc_structure.root_node_ids:
        node = doc_structure.all_nodes.get(node_id)
        if node:
            root_nodes.append({
                "node_id": node.node_id,
                "section_number": node.section_number,
                "title": node.title,
                "level": node.level,
                "page_num": node.page_num,
                "children_count": len(node.children_ids),
                "has_direct_content": node.has_direct_content,
            })

    return {
        "reg_id": reg_id,
        "total_chapters": len(doc_structure.all_nodes),
        "root_nodes": root_nodes,
    }
```

**实现特点**:
- ✅ **显式错误处理** - 检查规程是否存在
- ✅ **向后兼容** - 处理文档结构未生成的情况
- ✅ **丰富元数据** - 提取节点 ID、子节点数量等详细信息
- ✅ **统计信息** - 返回总章节数

---

## 返回数据结构对比

### `get_toc` 返回示例

```json
{
  "reg_id": "angui_2024",
  "title": "国家电网有限公司电力安全工作规程",
  "items": [
    {
      "section_number": "1",
      "title": "总则",
      "page_range": [1, 10],
      "children": [
        {
          "section_number": "1.1",
          "title": "适用范围",
          "page_range": [5, 7],
          "children": [...]
        },
        {
          "section_number": "1.2",
          "title": "引用标准",
          "page_range": [7, 10],
          "children": [...]
        }
      ]
    },
    {
      "section_number": "2",
      "title": "基本规定",
      "page_range": [11, 50],
      "children": [...]
    }
  ]
}
```

**数据特点**:
- 🌳 **嵌套树状结构** - `children` 字段递归包含子章节
- 📄 **页码范围** - 提供 `page_range` 便于定位
- 📚 **完整层级** - 从根节点到叶子节点的完整路径

### `get_chapter_structure` 返回示例

```json
{
  "reg_id": "angui_2024",
  "total_chapters": 156,
  "root_nodes": [
    {
      "node_id": "abc12345",
      "section_number": "1.1",
      "title": "适用范围",
      "level": 1,
      "page_num": 5,
      "children_count": 3,
      "has_direct_content": true
    },
    {
      "node_id": "def67890",
      "section_number": "1.2",
      "title": "引用标准",
      "level": 1,
      "page_num": 7,
      "children_count": 0,
      "has_direct_content": true
    },
    {
      "node_id": "ghi13579",
      "section_number": "2.1",
      "title": "一般规定",
      "level": 1,
      "page_num": 11,
      "children_count": 8,
      "has_direct_content": false
    }
  ]
}
```

**数据特点**:
- 📊 **扁平化结构** - 只返回根节点列表，无嵌套
- 🔢 **统计信息** - 提供 `total_chapters` 和 `children_count`
- 🆔 **节点标识** - 包含 `node_id` 用于后续查询
- 🏷️ **元数据丰富** - `level`, `has_direct_content` 等分析字段

---

## 使用场景详解

### `get_toc` 适用场景 ✅

#### 1. 首次浏览规程
**场景**: Agent 或用户第一次接触某个规程文档

```python
# Agent 工作流
toc = get_toc("angui_2024")
print(f"规程标题: {toc['title']}")
print(f"主要章节: {[item['title'] for item in toc['items']]}")
# 输出: ['总则', '基本规定', '高压配电装置', ...]
```

#### 2. 确定搜索范围
**场景**: 用户询问"母线失压相关内容"，Agent 需要确定搜索范围

```python
# 先获取目录
toc = get_toc("angui_2024")
# 发现"第六章 倒闸操作"可能相关
# 使用章节范围限定搜索
results = smart_search(
    query="母线失压",
    reg_id="angui_2024",
    chapter_scope="第六章"
)
```

#### 3. 文档导航
**场景**: CLI 用户需要可视化的目录树

```bash
regreader toc angui_2024 --expand --level 3
```

输出效果:
```
📚 国家电网有限公司电力安全工作规程
  📖 1. 总则 (第1-10页)
    📑 1.1 适用范围 (第5-7页)
    📑 1.2 引用标准 (第7-10页)
  📖 2. 基本规定 (第11-50页)
    📑 2.1 一般规定 (第11-15页)
    ...
```

#### 4. 用户交互
**场景**: 向最终用户展示规程结构

```python
# Agent 响应
toc = get_toc("angui_2024")
response = f"""
该规程包含以下主要章节：
{format_toc_for_user(toc)}

您想查看哪个章节的内容？
"""
```

### `get_chapter_structure` 适用场景 ✅

#### 1. 编程接口
**场景**: 需要访问章节的详细元数据

```python
# 获取章节结构
structure = get_chapter_structure("angui_2024")

# 遍历根节点
for node in structure["root_nodes"]:
    if node["children_count"] > 0:
        # 有子章节的根节点
        print(f"章节 {node['section_number']} 包含 {node['children_count']} 个子节点")
        # 可以根据 node_id 进一步查询详细内容
```

#### 2. 章节分析
**场景**: 统计章节数量、层级分布

```python
structure = get_chapter_structure("angui_2024")

print(f"总章节数: {structure['total_chapters']}")
print(f"顶级章节数: {len(structure['root_nodes'])}")

# 分析层级分布
levels = [node["level"] for node in structure["root_nodes"]]
print(f"层级分布: {Counter(levels)}")
```

#### 3. 批量操作
**场景**: 遍历所有根节点，读取章节内容

```python
structure = get_chapter_structure("angui_2024")

for node in structure["root_nodes"]:
    # 读取每个根节点的内容
    content = read_chapter_content(
        reg_id="angui_2024",
        section_number=node["section_number"]
    )
    # 处理内容...
```

#### 4. 验证文档结构
**场景**: 检查文档是否正确入库

```python
structure = get_chapter_structure("angui_2024")

if structure["total_chapters"] == 0:
    print("警告: 文档结构未生成")
    print(structure.get("message"))
else:
    print(f"✓ 文档结构正常，共 {structure['total_chapters']} 个章节")
```

---

## CLI 命令对比

### `toc` 命令

**文件位置**: `src/regreader/cli.py` (第 638-849 行)

**命令签名**:
```bash
regreader toc <reg_id> [OPTIONS]

Options:
  -o, --output PATH    JSON 输出文件路径
  -e, --expand         展开所有层级
  -l, --level INT      显示的最大层级深度 (默认: 3)
```

**特点**:

1. **Rich 树形展示**
   - 使用 `rich.tree.Tree` 创建可视化层级结构
   - 自动折叠超过 `--level` 限制的深层节点

2. **智能分组**
   - 按章节编号前缀自动分组（1.x, 2.x, 3.x...）
   - 一级章节显示完整标题（"1. 总则"）

3. **颜色编码**
   ```python
   层级图标与颜色:
   📚 根节点   - bold cyan
   📖 章       - bold green
   📑 节       - yellow
   📄 条       - white
   📝 款       - dim
   •  项       - dim
   ```

4. **折叠提示**
   - 显示 `+N` 表示有 N 个子节点被折叠
   - 例: `📑 2.1 一般规定 (+8)` 表示有 8 个子节点未展开

**使用示例**:
```bash
# 默认显示 3 层
regreader toc angui_2024

# 展开所有层级
regreader toc angui_2024 --expand

# 只显示 2 层
regreader toc angui_2024 --level 2

# 导出为 JSON
regreader toc angui_2024 --output toc.json
```

### `chapter-structure` 命令

**文件位置**: `src/regreader/cli.py` (第 888-935 行)

**命令签名**:
```bash
regreader chapter-structure <reg_id> [OPTIONS]

Options:
  -o, --output PATH    JSON 输出文件路径
```

**特点**:

1. **简单表格展示**
   - 使用 `rich.table.Table` 显示根节点列表
   - 只展示一层（根节点），无嵌套

2. **关键信息列**
   ```
   列名:
   - 节点ID (node_id)
   - 章节号 (section_number)
   - 标题 (title)
   - 级别 (level)
   - 页码 (page_num)
   - 子节点数 (children_count)
   ```

3. **统计信息**
   - 在表格标题中显示总章节节点数
   - 例: `章节结构 (共 156 个节点)`

4. **无层级展示**
   - 仅显示根节点的扁平列表
   - 适合快速查看顶级结构

**使用示例**:
```bash
# 显示章节结构
regreader chapter-structure angui_2024

# 导出为 JSON
regreader chapter-structure angui_2024 --output structure.json
```

**示例输出**:
```
┌──────────┬─────────┬──────────────┬──────┬──────┬────────────┐
│ 节点ID   │ 章节号  │ 标题         │ 级别 │ 页码 │ 子节点数   │
├──────────┼─────────┼──────────────┼──────┼──────┼────────────┤
│ abc12345 │ 1.1     │ 适用范围     │  1   │  5   │     3      │
│ def67890 │ 1.2     │ 引用标准     │  1   │  7   │     0      │
│ ghi13579 │ 2.1     │ 一般规定     │  1   │  11  │     8      │
└──────────┴─────────┴──────────────┴──────┴──────┴────────────┘
```

---

## 推荐工作流

### 工作流 1: 首次探索规程

```
┌─────────────┐
│   get_toc   │ ← 起点：了解规程整体结构
└──────┬──────┘
       │
       ↓
┌─────────────┐
│smart_search │ ← 在确定的章节范围内搜索
└──────┬──────┘
       │
       ↓
┌─────────────┐
│read_page_   │ ← 读取相关页面详细内容
│   range     │
└─────────────┘
```

**示例代码**:
```python
# 1. 获取目录
toc = get_toc("angui_2024")
print("主要章节:", [item["title"] for item in toc["items"]])

# 2. 用户选择章节，执行搜索
results = smart_search(
    query="母线失压",
    reg_id="angui_2024",
    chapter_scope="第六章"
)

# 3. 读取相关页面
for result in results[:3]:
    pages = read_page_range(
        reg_id="angui_2024",
        start_page=result["page_num"],
        end_page=result["page_num"] + 2
    )
```

### 工作流 2: 深度章节分析

```
┌─────────────┐
│   get_toc   │ ← 起点：了解大局
└──────┬──────┘
       │
       ↓
┌─────────────┐
│get_chapter_ │ ← 获取详细章节元数据
│  structure  │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│read_chapter_│ ← 读取特定章节完整内容
│   content   │
└─────────────┘
```

**示例代码**:
```python
# 1. 获取目录（确认章节存在）
toc = get_toc("angui_2024")

# 2. 获取章节结构（获取详细元数据）
structure = get_chapter_structure("angui_2024")

# 3. 遍历根节点，读取内容
for node in structure["root_nodes"]:
    if node["children_count"] > 5:  # 只处理复杂章节
        content = read_chapter_content(
            reg_id="angui_2024",
            section_number=node["section_number"]
        )
        # 分析章节内容...
```

### 工作流 3: 查找特定章节

```
┌─────────────┐
│   get_toc   │ ← 起点：确认章节编号
└──────┬──────┘
       │
       ↓
  (用户确定章节)
       │
       ↓
┌─────────────┐
│get_chapter_ │ ← 可选：验证章节是否有子节点
│  structure  │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│read_chapter_│ ← 直接读取目标章节
│   content   │
└─────────────┘
```

**示例代码**:
```python
# 用户询问: "2.1.4 条的内容是什么？"

# 1. 获取目录确认章节存在
toc = get_toc("angui_2024")

# 2. 可选：检查章节结构
structure = get_chapter_structure("angui_2024")
target_node = next(
    (n for n in structure["root_nodes"] if n["section_number"] == "2.1.4"),
    None
)

if target_node and target_node["children_count"] > 0:
    print(f"注意: 该章节包含 {target_node['children_count']} 个子节点")

# 3. 读取章节内容
content = read_chapter_content(
    reg_id="angui_2024",
    section_number="2.1.4"
)
```

---

## 工具元数据

### `get_toc` 元数据

**文件位置**: `src/regreader/mcp/tool_metadata.py`

```python
TOOL_METADATA["get_toc"] = ToolMetadata(
    name="get_toc",
    brief="获取规程目录树",
    description="""
获取规程的完整目录树结构，包含章节标题、编号、页码范围等信息。
这是探索规程内容的推荐起点。
""",
    category=ToolCategory.BASE,
    phase=0,
    priority=1,  # 高优先级
    prerequisites=[],  # 无前置要求
    next_tools=["smart_search", "read_chapter_content", "get_chapter_structure"],
    use_cases=[
        "了解规程整体结构",
        "确定搜索范围",
        "查看章节层级关系",
        "定位特定章节的页码范围"
    ],
    cli_command="toc",
    expected_params={
        "reg_id": "string - 规程标识，如 'angui_2024'"
    },
    example_usage="""
    # 获取规程目录树
    toc = get_toc("angui_2024")

    # 查看主要章节
    for item in toc["items"]:
        print(f"{item['section_number']}. {item['title']}")
    """
)
```

### `get_chapter_structure` 元数据

**文件位置**: `src/regreader/mcp/tool_metadata.py`

```python
TOOL_METADATA["get_chapter_structure"] = ToolMetadata(
    name="get_chapter_structure",
    brief="获取完整章节结构",
    description="""
获取文档的章节结构信息，包括总章节数和根节点详细信息。
返回的根节点包含 node_id、children_count 等元数据，适合进行章节分析。
""",
    category=ToolCategory.BASE,
    phase=0,
    priority=2,  # 中优先级
    prerequisites=["get_toc"],  # 建议先调用 get_toc
    next_tools=["read_chapter_content"],
    use_cases=[
        "获取章节统计信息",
        "分析章节层级分布",
        "批量处理章节内容",
        "验证文档结构是否完整"
    ],
    cli_command="chapter-structure",
    expected_params={
        "reg_id": "string - 规程标识，如 'angui_2024'"
    },
    example_usage="""
    # 获取章节结构
    structure = get_chapter_structure("angui_2024")

    # 查看统计信息
    print(f"总章节数: {structure['total_chapters']}")
    print(f"根节点数: {len(structure['root_nodes'])}")

    # 遍历根节点
    for node in structure["root_nodes"]:
        print(f"{node['section_number']} - {node['title']} ({node['children_count']} 个子节点)")
    """
)
```

---

## 数据模型对比

### `TocTree` 模型 (用于 `get_toc`)

**文件位置**: `src/regreader/storage/models.py`

```python
class TocItem(BaseModel):
    """目录项"""
    section_number: str
    title: str
    page_range: tuple[int, int]
    level: int
    children: list["TocItem"] = Field(default_factory=list)

class TocTree(BaseModel):
    """目录树"""
    reg_id: str
    title: str = ""
    items: list[TocItem] = Field(default_factory=list)
```

**特点**:
- 📊 **递归结构** - `TocItem.children` 支持无限嵌套
- 📄 **页码范围** - `page_range` 元组表示起止页
- 🌳 **树状组织** - 自然表达章节层级关系

### `DocumentStructure` 模型 (用于 `get_chapter_structure`)

**文件位置**: `src/regreader/storage/models.py`

```python
class ChapterNode(BaseModel):
    """章节节点"""
    node_id: str
    section_number: str
    title: str
    level: int
    page_num: int
    parent_id: str | None = None
    children_ids: list[str] = Field(default_factory=list)
    content_block_ids: list[str] = Field(default_factory=list)
    has_direct_content: bool = False

class DocumentStructure(BaseModel):
    """文档结构"""
    reg_id: str
    all_nodes: dict[str, ChapterNode] = Field(default_factory=dict)
    root_node_ids: list[str] = Field(default_factory=list)

    def get_chapter_path(self, node_id: str) -> list[str]:
        """获取章节完整路径"""
        ...

    def get_node_by_section_number(self, section_num: str) -> ChapterNode | None:
        """按编号查找节点"""
        ...
```

**特点**:
- 🆔 **ID 引用** - 使用 `node_id` 和 `children_ids` 建立关系
- 📊 **图结构** - `all_nodes` 字典支持快速查找
- 🔗 **双向关系** - 同时维护 `parent_id` 和 `children_ids`
- 📝 **内容关联** - `content_block_ids` 链接到具体内容块

---

## 关键洞察

### 设计哲学差异

**`get_toc` - "广度优先"**
```
目标: 让用户快速了解"有什么"
策略: 展示完整的层级结构，像翻阅纸质书目录
优势: 直观、易理解、适合人类阅读
```

**`get_chapter_structure` - "元数据优先"**
```
目标: 让程序准确获取"在哪里"、"有多少"
策略: 提供结构化的元数据，支持编程操作
优势: 机器友好、支持分析、适合批量处理
```

### 渐进式信息披露

这两个工具体现了"渐进式信息披露"（Progressive Disclosure）设计原则：

```
第 1 层: get_toc
  ↓ 返回: 目录树，了解大局

第 2 层: get_chapter_structure
  ↓ 返回: 章节元数据，深入分析

第 3 层: read_chapter_content
  ↓ 返回: 完整章节内容，详细阅读
```

**优势**:
- ✅ 避免初始信息过载
- ✅ 让 Agent 逐步深入
- ✅ 减少不必要的数据传输
- ✅ 提高响应速度

### 何时使用哪个工具？

**决策树**:
```
需要获取规程结构信息？
├─ 是为了给用户展示目录？
│  └─ 使用 get_toc ✓
│
├─ 是为了确定搜索范围？
│  └─ 使用 get_toc ✓
│
├─ 需要遍历所有章节？
│  ├─ 只需要顶级章节？
│  │  └─ 使用 get_chapter_structure ✓
│  └─ 需要所有层级？
│     └─ 先用 get_toc，再按需深入 ✓
│
├─ 需要章节的 node_id？
│  └─ 使用 get_chapter_structure ✓
│
└─ 需要统计章节数量？
   └─ 使用 get_chapter_structure ✓
```

---

## 性能对比

| 指标 | `get_toc` | `get_chapter_structure` |
|------|-----------|------------------------|
| **数据加载** | 直接加载 TocTree | 加载 DocumentStructure + 遍历 |
| **数据量** | 中等（嵌套结构） | 小（仅根节点） |
| **响应速度** | 快 | 快 |
| **内存占用** | 中等 | 小 |
| **适合频繁调用** | ✅ 是 | ✅ 是 |

**性能建议**:
- 两个工具性能都很好，可以频繁调用
- 如果只需要根节点信息，`get_chapter_structure` 返回数据更小
- 如果需要完整目录树，`get_toc` 一次返回所有信息，避免多次调用

---

## 常见问题 FAQ

### Q1: 为什么要有两个工具？直接用一个不行吗？

**A**: 单一职责原则（SRP）。两个工具服务于不同的场景：

- `get_toc`: 面向展示，关注"可读性"
- `get_chapter_structure`: 面向分析，关注"可操作性"

强行合并会导致返回数据复杂，增加使用难度。

### Q2: `get_chapter_structure` 为什么只返回根节点？

**A**: 设计权衡：

1. **渐进式披露**: 避免返回过多数据
2. **常见用例**: 大多数场景只需要根节点
3. **扩展性**: 需要子节点时，可以调用 `read_chapter_content`

### Q3: CLI 的 `toc` 命令和 MCP 的 `get_toc` 工具有区别吗？

**A**: 有区别：

- **MCP `get_toc`**: 返回原始 JSON 数据
- **CLI `toc`**: 额外加载 `DocumentStructure`，进行美化展示（颜色、图标、分组）

CLI 命令提供了更丰富的用户体验。

### Q4: 什么时候应该先调用 `get_toc`，再调用 `get_chapter_structure`？

**A**: 推荐工作流：

```python
# ✅ 推荐：先了解大局，再深入分析
toc = get_toc("angui_2024")
# 用户确认要分析某些章节
structure = get_chapter_structure("angui_2024")

# ❌ 不推荐：直接深入，可能遗漏重要信息
structure = get_chapter_structure("angui_2024")
```

### Q5: 返回的 `node_id` 有什么用？

**A**: `node_id` 是章节节点的唯一标识，可以用于：

1. 快速查找节点（O(1) 查找）
2. 建立节点之间的关系（父子、兄弟）
3. 关联内容块到章节
4. 未来可能扩展的节点级操作

---

## 总结

### 核心要点

1. **`get_toc`** = "快速浏览工具" - 完整目录树，适合人类阅读
2. **`get_chapter_structure`** = "深度分析工具" - 章节元数据，适合编程操作

### 使用建议

- ✅ **首次探索规程**: 先用 `get_toc`
- ✅ **需要可视化展示**: 用 `get_toc`
- ✅ **需要章节统计**: 用 `get_chapter_structure`
- ✅ **需要 node_id**: 用 `get_chapter_structure`
- ✅ **批量处理章节**: 用 `get_chapter_structure`

### 推荐工作流

```
探索 → 搜索 → 阅读
 ↓       ↓       ↓
get_toc → smart_search → read_page_range

分析 → 查询 → 阅读
 ↓       ↓       ↓
get_toc → get_chapter_structure → read_chapter_content
```

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/regreader/mcp/tools.py` | 工具实现代码 |
| `src/regreader/mcp/tool_metadata.py` | 工具元数据定义 |
| `src/regreader/cli.py` | CLI 命令实现（行 638-935） |
| `src/regreader/storage/models.py` | TocTree 和 DocumentStructure 数据模型 |
| `src/regreader/storage/page_store.py` | 数据加载逻辑 |

---

## 更新历史

| 日期 | 版本 | 变更说明 |
|------|------|----------|
| 2026-01-02 | 1.0 | 初始版本，详细对比分析 |
