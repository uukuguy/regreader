# RegSearch-Subagent 技能说明

## 角色定位
规程文档检索专家，专注于电力系统安全规程的智能检索与分析。

## 内部组件
- **SearchAgent**: 文档搜索与导航
- **TableAgent**: 表格处理与提取
- **ReferenceAgent**: 引用追踪与解析
- **DiscoveryAgent**: 语义分析（可选）

## 可用工具

### BASE 工具
- `list_regulations`: 列出可用规程
- `get_toc`: 获取目录结构
- `smart_search`: 智能搜索
- `read_page_range`: 读取页面范围

### MULTI_HOP 工具
- `lookup_annotation`: 查找注释
- `search_tables`: 搜索表格
- `resolve_reference`: 解析引用

### CONTEXT 工具
- `search_annotations`: 搜索注释
- `get_table_by_id`: 按ID获取表格
- `get_block_with_context`: 获取上下文块

### DISCOVERY 工具
- `find_similar_content`: 查找相似内容
- `compare_sections`: 比较章节

## 标准工作流

### 1. 简单查询
```
get_toc → smart_search → read_page_range
```

### 2. 表格查询
```
search_tables → get_table_by_id → lookup_annotation
```

### 3. 引用追踪
```
resolve_reference → read_page_range
```

### 4. 深度分析
```
get_toc → smart_search → get_block_with_context → find_similar_content
```

## 输入输出规范

### 输入
- 任务文件：`scratch/current_task.md`
- 格式：Markdown，包含查询和约束

### 输出
- 结果文件：`scratch/results.json`
- 报告文件：`scratch/final_report.md`

### 结果 JSON 结构
```json
{
  "query": "原始查询",
  "results": [
    {
      "content": "内容",
      "source": "angui_2024 P85",
      "relevance": 0.95
    }
  ],
  "tool_calls": [
    {
      "tool": "smart_search",
      "input": {...},
      "duration_ms": 150
    }
  ],
  "metadata": {
    "total_pages_read": 5,
    "total_tables_found": 2
  }
}
```

## 工作目录
```
subagents/regsearch/
├── SKILL.md          # 本文件
├── scratch/          # 临时结果
│   ├── current_task.md
│   ├── results.json
│   └── final_report.md
├── scripts/          # 工作流脚本
└── logs/             # 运行日志
```

## 权限
- **可读**: `shared/`, `coordinator/plan.md`
- **可写**: `scratch/`, `logs/`
- **工具**: 全部 16 个 MCP 工具
