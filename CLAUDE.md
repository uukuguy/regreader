# GridCode 项目开发指南

## 项目概述

GridCode 是电力系统安规智能检索 Agent，采用 Page-Based Agentic Search 架构。

**核心设计原则**：
- 以"页"为存储单位，非任意切片
- LLM 动态"翻书"，而非一次性向量匹配
- 三框架并行实现（Claude Agent SDK / Pydantic AI / LangGraph）

## 项目结构

```
src/grid_code/
├── parser/           # Docling 解析层
├── storage/          # 页面存储 + Pydantic 模型
├── index/            # FTS5 + LanceDB 索引
├── mcp/              # FastMCP Server
├── agents/           # 三种 Agent 实现
├── config.py
└── cli.py
```

## 技术栈约束

| 组件 | 技术 | 版本要求 |
|------|------|----------|
| Python | 3.12+ | 使用现代类型提示语法 |
| 文档解析 | Docling | - |
| 关键词索引 | SQLite FTS5 | 内置 |
| 向量索引 | LanceDB | - |
| MCP Server | FastMCP | SSE 传输 |
| 数据模型 | Pydantic v2 | BaseModel |
| CLI | Typer | - |

## 代码规范

### 类型注解
- 所有函数必须有类型注解
- 使用 `list[str]` 而非 `List[str]`（Python 3.12+ 语法）
- 使用 `str | None` 而非 `Optional[str]`

### Pydantic 模型
- 所有数据模型继承 `BaseModel`
- 使用 `model_dump()` 而非已废弃的 `dict()`
- 字段使用 `Field()` 添加描述

### 异步
- MCP Server 和 Agent 层使用 `async/await`
- 索引层可同步（SQLite/LanceDB 操作快速）

### 错误处理
- 使用自定义异常类，定义于 `src/grid_code/exceptions.py`
- 日志使用 `loguru`

## 关键数据模型

```python
# storage/models.py 中的核心模型
PageDocument      # 页面文档（一页可含多个 ContentBlock）
ContentBlock      # 内容块（text/table/heading/list）
TableMeta         # 表格元数据（含跨页标记 is_truncated）
Annotation        # 页面注释（注1、方案A 等）
```

## MCP 工具接口

```python
# mcp/tools.py 中的三个核心工具
get_toc(reg_id: str) -> TocTree
smart_search(query: str, reg_id: str, chapter_scope: str | None, limit: int) -> list[SearchResult]
read_page_range(reg_id: str, start_page: int, end_page: int) -> PageContent
```

## 开发约束

### 必须遵守
- 所有 MCP 工具返回必须包含 `source` 字段（reg_id + page_num）
- 表格跨页时必须设置 `continues_to_next: true`
- Agent 实现必须继承 `agents/base.py` 中的抽象基类

### 禁止事项
- 禁止在索引层直接操作原始 PDF/DOCX 文件
- 禁止硬编码规程 ID，必须从配置读取
- 禁止在 MCP 工具中进行复杂推理（推理属于 Agent 层）

## 测试规范

- 单元测试放置于 `tests/` 目录
- 使用 `pytest` 框架
- Mock 外部依赖（LLM API、文件系统）

## 文档路径

| 文档 | 路径 |
|------|------|
| 设计方案 | `docs/main/DESIGN_DOCUMENT.md` |
| 工作日志 | `docs/main/WORK_LOG.md` |
| 初步设计 | `docs/PreliminaryDesign/` |

## Git 分支策略

- `main`: 稳定版本
- `feature/*`: 功能开发
- `fix/*`: 问题修复
