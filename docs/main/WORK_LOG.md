# GridCode 工作日志

## 2025-12-28 设计阶段完成

### 会话概述
完成 GridCode 项目的整体设计方案，包括架构设计、数据模型、MCP 工具定义和实施计划。

### 主要成果

1. **架构设计**
   - 确定四层架构：存储层 → 索引层 → 工具层 → 推理层
   - 推理层采用三框架并行实现策略（Claude Agent SDK / Pydantic AI / LangGraph）

2. **数据模型设计**
   - `PageDocument`: 页面存储模型，支持一页多表
   - `ContentBlock`: 内容块模型（文本/表格/标题/列表）
   - `TableMeta`: 表格元数据，支持跨页标记
   - `Annotation`: 注释模型（注1、方案A 等）

3. **MCP 工具定义**
   - `get_toc`: 获取规程目录树
   - `smart_search`: 混合检索（关键词+语义）
   - `read_page_range`: 读取连续页面（自动跨页拼接）

4. **技术选型**
   - 文档解析：Docling（支持 PDF/DOCX，保留 provenance）
   - 关键词索引：SQLite FTS5
   - 语义索引：LanceDB
   - MCP Server：FastMCP + SSE 传输

### 设计决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 存储单位 | 页面级 | 保持物理结构，便于引用定位 |
| 存储格式 | JSON + Markdown | JSON 无损结构，Markdown 供 LLM 阅读 |
| 推理框架 | 三框架并行 | Claude SDK 最优体验 + Pydantic AI/LangGraph 企业灵活性 |
| 输入格式 | 仅 DOCX/PDF | 用户保证输入格式，无需转换 |

### 生成文件
- `docs/main/DESIGN_DOCUMENT.md` - 完整设计方案
- `README.md` - 英文版项目说明
- `README_CN.md` - 中文版项目说明
- `CLAUDE.md` - 项目开发指南（Claude Code 配置）

### 下一步工作
- Phase 1: 集成 Docling，实现文档解析和页面级存储
- 验证 Docling 对安规表格的解析效果（一页多表场景）

### 待确认事项
- [ ] 需要真实安规文档验证 Docling 解析效果
- [ ] 确认注释格式（注1 vs 注① vs (注一)）
- [ ] 确认是否需要处理图片/公式
