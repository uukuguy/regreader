# RegReader 项目开发指南 (Internal AI Coding Reference)

## 1. 项目愿景与目标

**RegReader** 是一个针对电力系统多规程（安规、稳规、调规等）的智能检索与推理 Agent。

- **核心挑战**：安规文档存在海量复杂跨页表格、嵌套引用（如“见注1”）、多规程语义冲突。
- **设计哲学**：模仿 Claude Code 的 Agentic Search 思路。不进行复杂的预处理切片，而是将 PDF 保持为“页”结构，利用 LLM 的推理能力动态翻阅、拼接、溯源。

---

## 2. 核心设计思路 (The "RegReader" Architecture)

### 2.1 存储模型：Page-Based Retrieval

- **最小单元**：以“物理页 (Page)”为单位进行存储。
- **解析方案**：使用 `Docling` 将 PDF 转换为增强型 Markdown，记录每页的标题路径 (Chapter Path) 和表格坐标。
- **混合索引**：
    - **SQLite FTS5**: 负责精确的设备名、故障术语定位（Keyword Search）。
    - **LanceDB**: 负责模糊的现象描述定位（Semantic Search）。

### 2.2 交互协议：MCP (Model Context Protocol)

通过 MCP Server 将“翻书能力”暴露给 CC 或其他 Agent。核心工具包括：

- `list_catalog()`: 获取当前加载的规程库。
- `get_toc(reg_type)`: 获取特定规程的章节目录树及页码映射。
- `smart_search(query, scope)`: 跨规程混合检索，返回匹配片段及 `page_num`。
- `read_page_range(reg_type, start_page, end_page)`: 读取连续页面的完整 Markdown 内容。

---

## 3. 关键逻辑：Agentic Reasoning 链路

CC 在开发时应确保 Agent 遵循以下推理逻辑：

1. **意图路由**：先查目录（TOC）锁定潜在章节，避免盲目全书搜索。
2. **动态缝合**：
    - 如果表格在当前页未闭合（`is_truncated`），Agent 必须主动调用工具读取下一页。
    - 识别 Markdown 中的“注”、“方案A”等锚点，自动发起递归搜索。
3. **多规程对齐**：当安规与稳规对同一场景有不同描述时，Agent 需在 Response 中分别罗列来源。

---

## 4. 待实施任务清单 (Backlog for Claude Code)

### Phase 1: 基础设施 (Parser & Storage)

- [ ]  集成 `Docling`，实现 PDF 到 Page-Level Markdown 的转换器。
- [ ]  构建 SQLite FTS5 虚拟表，存储 `(content, page_num, chapter_path, reg_type)`。
- [ ]  实现 LanceDB 的向量化入库脚本。

### Phase 2: MCP Server 开发

- [ ]  封装 FastMCP 服务，定义 `get_toc` 和 `smart_search` 工具。
- [ ]  **重点：** 实现 `read_page_range` 的预处理逻辑，能够自动补全跨页表格的表头。

### Phase 3: 推理 Agent (Agentic Workflow)

- [ ]  编写 System Prompt，注入电力规程处理规则（严禁断章取义、强制溯源）。
- [ ]  使用 LangGraph 编排多步搜索流程。

---

## 5. 开发建议与约束

- **关于表格**：安规表格极度复杂。解析时，若 Markdown 效果不佳，优先考虑将表格导出为 JSON 结构供 Agent 读取，再由 Agent 渲染为 Markdown 给用户。
- **关于定位**：所有的 Tool 输出必须带有明确的 `Source: {reg_type} P{page_num}` 格式。
- **关于性能**：由于采用“动态翻书”模式，必须优化 FTS5 检索速度，确保第一步定位在 200ms 内完成。