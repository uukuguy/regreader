# MCP 工具分类与智能体引导系统实现计划

> 创建时间：2025-12-30
> 分支：dev

## 目标

1. **CLI 层**：添加 `mcp-tools` 命令，支持分类列出工具
2. **MCP Server 层**：增强工具描述 + 添加结构化元数据
3. **智能体层**：提供工具导航能力，帮助智能体正确选择工具

## 工具分类结构

| 分类 | 中文名 | 工具数量 | 说明 |
|------|--------|---------|------|
| base | 基础工具 | 7 | 核心查询和读取功能 |
| multi-hop | 核心多跳 | 3 | 注释查找、表格搜索、引用解析 |
| context | 上下文 | 3 | 注释搜索、表格获取、上下文扩展 |
| discovery | 发现 | 2 | 相似内容、章节比较 |
| navigation | 导航 | 1 | 工具使用指南（新增） |

---

## 方案 A：增强工具描述

### 目标
在每个工具的 description 中嵌入分类标签和使用建议。

### 描述模板
```
[分类:核心多跳] 搜索表格（按标题或单元格内容）。

使用场景：需要查找特定表格或在表格中定位信息。
前置工具：通常先用 get_toc 了解章节范围。
后续工具：找到表格后用 get_table_by_id 获取完整内容。
```

### 修改文件
- `src/regreader/mcp/server.py`：更新所有工具的 description

---

## 方案 B：工具导航工具

### 目标
新增 `get_tool_guide` MCP 工具，返回工具分类和推荐使用流程。

### 返回结构
```json
{
  "categories": [
    {"id": "base", "name": "基础工具", "description": "核心查询和读取功能", "count": 7}
  ],
  "tools_by_category": {
    "base": [
      {"name": "get_toc", "brief": "获取目录", "priority": 1}
    ]
  },
  "workflows": {
    "查找表格内容": ["get_toc", "search_tables", "get_table_by_id"],
    "理解注释引用": ["smart_search", "lookup_annotation"],
    "阅读章节": ["get_chapter_structure", "read_chapter_content"]
  },
  "tips": [
    "先用 get_toc 或 list_regulations 了解规程结构",
    "搜索结果不完整时用 get_block_with_context 扩展上下文"
  ]
}
```

### 修改文件
- `src/regreader/mcp/server.py`：添加 get_tool_guide 工具
- `src/regreader/mcp/tools.py`：实现 get_tool_guide 方法
- `src/regreader/mcp/protocol.py`：添加协议定义

---

## 方案 C：结构化元数据

### MCP 协议支持（已验证）
FastMCP `@mcp.tool()` 装饰器原生支持 `meta` 参数：
```python
@mcp.tool(
    meta={"category": "multi-hop", "phase": 1, "priority": 2},
    annotations=ToolAnnotations(readOnlyHint=True),
)
def search_tables(...): ...
```

### 元数据结构
```python
@dataclass
class ToolMetadata:
    category: str           # base, multi-hop, context, discovery
    category_name: str      # 中文分类名
    phase: int              # 0=基础, 1/2/3=对应Phase
    priority: int           # 1=高, 2=中, 3=低
    prerequisites: list[str]  # 前置工具
    next_tools: list[str]     # 后续推荐工具
    use_cases: list[str]      # 适用场景
    cli_command: str | None   # 对应 CLI 命令
```

### 完整工具元数据注册表

```python
TOOL_METADATA = {
    # === 基础工具 ===
    "get_toc": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=1,
        prerequisites=[],
        next_tools=["smart_search", "read_chapter_content"],
        use_cases=["了解规程结构", "确定搜索范围"],
        cli_command="toc",
    ),
    "smart_search": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=1,
        prerequisites=["get_toc"],
        next_tools=["read_page_range", "get_block_with_context"],
        use_cases=["查找相关内容", "混合检索"],
        cli_command="search",
    ),
    "read_page_range": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["阅读完整页面", "查看跨页表格"],
        cli_command="read-pages",
    ),
    "list_regulations": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=1,
        prerequisites=[],
        next_tools=["get_toc"],
        use_cases=["了解可用规程"],
        cli_command="list",
    ),
    "get_chapter_structure": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=2,
        prerequisites=["get_toc"],
        next_tools=["read_chapter_content"],
        use_cases=["获取章节树"],
        cli_command="chapter-structure",
    ),
    "get_page_chapter_info": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=3,
        prerequisites=[],
        next_tools=[],
        use_cases=["了解页面所属章节"],
        cli_command="page-info",
    ),
    "read_chapter_content": ToolMetadata(
        category="base", category_name="基础工具", phase=0, priority=2,
        prerequisites=["get_chapter_structure"],
        next_tools=[],
        use_cases=["阅读完整章节"],
        cli_command="read-chapter",
    ),

    # === 核心多跳 ===
    "lookup_annotation": ToolMetadata(
        category="multi-hop", category_name="核心多跳", phase=1, priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["查找注释内容", "理解表格脚注"],
        cli_command="lookup-annotation",
    ),
    "search_tables": ToolMetadata(
        category="multi-hop", category_name="核心多跳", phase=1, priority=2,
        prerequisites=["get_toc"],
        next_tools=["get_table_by_id"],
        use_cases=["查找特定表格", "表格内容搜索"],
        cli_command="search-tables",
    ),
    "resolve_reference": ToolMetadata(
        category="multi-hop", category_name="核心多跳", phase=1, priority=2,
        prerequisites=["smart_search"],
        next_tools=["read_page_range", "read_chapter_content"],
        use_cases=["解析交叉引用"],
        cli_command="resolve-reference",
    ),

    # === 上下文 ===
    "search_annotations": ToolMetadata(
        category="context", category_name="上下文", phase=2, priority=3,
        prerequisites=[],
        next_tools=["lookup_annotation"],
        use_cases=["搜索所有注释"],
        cli_command="search-annotations",
    ),
    "get_table_by_id": ToolMetadata(
        category="context", category_name="上下文", phase=2, priority=2,
        prerequisites=["search_tables"],
        next_tools=[],
        use_cases=["获取完整表格"],
        cli_command="get-table",
    ),
    "get_block_with_context": ToolMetadata(
        category="context", category_name="上下文", phase=2, priority=2,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["扩展上下文"],
        cli_command="get-block-context",
    ),

    # === 发现 ===
    "find_similar_content": ToolMetadata(
        category="discovery", category_name="发现", phase=3, priority=3,
        prerequisites=["smart_search"],
        next_tools=[],
        use_cases=["查找相似内容"],
        cli_command="find-similar",
    ),
    "compare_sections": ToolMetadata(
        category="discovery", category_name="发现", phase=3, priority=3,
        prerequisites=["get_chapter_structure"],
        next_tools=[],
        use_cases=["比较章节"],
        cli_command="compare-sections",
    ),

    # === 导航 ===
    "get_tool_guide": ToolMetadata(
        category="navigation", category_name="导航", phase=0, priority=1,
        prerequisites=[],
        next_tools=["get_toc", "list_regulations"],
        use_cases=["了解可用工具", "获取使用指南"],
        cli_command=None,
    ),
}
```

---

## CLI 命令：`mcp-tools`

### 命令定义
```python
@app.command("mcp-tools")
def mcp_tools(
    category: str | None = typer.Option(None, "--category", "-c",
        help="按分类过滤: base, multi-hop, context, discovery, navigation"),
    verbose: bool = typer.Option(False, "--verbose", "-v",
        help="显示详细信息（含工具链）"),
    list_categories: bool = typer.Option(False, "--list-categories",
        help="仅列出分类"),
):
    """列出 MCP 服务提供的所有工具"""
```

### 输出格式

#### 简明模式（默认）
```
MCP 工具列表 (16 个)

基础工具 (7)
  get_toc              获取规程目录树
  smart_search         混合检索
  read_page_range      读取页面范围
  list_regulations     列出已入库规程
  get_chapter_structure 获取章节结构
  get_page_chapter_info 获取页面章节信息
  read_chapter_content  读取章节内容

核心多跳 (3)
  lookup_annotation    查找注释内容
  search_tables        搜索表格
  resolve_reference    解析交叉引用

上下文 (3)
  search_annotations   搜索所有注释
  get_table_by_id      获取完整表格
  get_block_with_context 获取内容块上下文

发现 (2)
  find_similar_content 查找相似内容
  compare_sections     比较章节

导航 (1)
  get_tool_guide       获取工具使用指南
```

#### 详细模式 (`--verbose`)
```
核心多跳 (3)

  search_tables - 搜索表格
    CLI: search-tables
    前置: get_toc
    后续: get_table_by_id
    场景: 查找特定表格, 表格内容搜索
```

---

## 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/regreader/mcp/tool_metadata.py` | **新建** | 工具元数据定义和注册表 |
| `src/regreader/mcp/server.py` | 修改 | 1) 更新描述 2) 添加 meta 3) 添加 get_tool_guide |
| `src/regreader/mcp/tools.py` | 修改 | 实现 get_tool_guide 方法 |
| `src/regreader/mcp/protocol.py` | 修改 | 添加 get_tool_guide 协议定义 |
| `src/regreader/cli.py` | 修改 | 添加 mcp-tools 命令 |
| `src/regreader/mcp/__init__.py` | 修改 | 导出新模块 |

---

## 实现步骤

### 第一步：创建工具元数据系统
1. 新建 `src/regreader/mcp/tool_metadata.py`
2. 定义 `ToolMetadata` 数据类
3. 创建完整的 `TOOL_METADATA` 注册表

### 第二步：增强 MCP Server（方案 A + C）
1. 更新所有工具的 description，加入分类标签和使用建议
2. 为每个工具添加 `meta=TOOL_METADATA[name].to_dict()` 参数
3. 添加 `annotations=ToolAnnotations(readOnlyHint=True)` 标注

### 第三步：添加工具导航（方案 B）
1. 在 `tools.py` 实现 `get_tool_guide()` 方法
2. 在 `server.py` 注册 `get_tool_guide` MCP 工具
3. 更新 `protocol.py` 协议定义

### 第四步：添加 CLI 命令
1. 在 `cli.py` 添加 `mcp-tools` 命令
2. 实现简明和详细两种输出格式
3. 支持按分类过滤和 `--list-categories`

### 第五步：更新导出和测试
1. 更新 `mcp/__init__.py` 导出
2. 验证 MCP Client 能正确获取 meta 信息
3. 验证 get_tool_guide 返回正确数据
4. 验证 CLI 命令输出格式
