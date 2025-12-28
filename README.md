# GridCode

**Agentic Search for Power Grid Regulations**

[中文版](README_CN.md)

GridCode is an intelligent retrieval and reasoning agent for power system safety regulations (安规). Instead of traditional RAG chunking, it adopts a **page-based agentic search** approach—letting the LLM dynamically "flip through" documents, stitch cross-page tables, and trace references just like a human expert would.

## Why GridCode?

Power grid regulations present unique challenges that conventional RAG systems fail to address:

| Challenge | Traditional RAG | GridCode |
|-----------|-----------------|----------|
| **Complex Tables** | Chunks break table structure | Page-level storage preserves tables intact |
| **Cross-page Tables** | Lost context at chunk boundaries | Agent detects truncation, fetches next page |
| **Inline References** ("见注1") | Missed or orphaned | Agent traces annotations within page context |
| **Source Attribution** | Approximate chunk location | Exact page number + table ID |

## Design Philosophy

Inspired by how Claude Code searches codebases, GridCode treats regulations as "books to browse" rather than "vectors to match":

```
┌─────────────────────────────────────────────────────────────┐
│                    Reasoning Layer                          │
│     Claude Agent SDK  |  Pydantic AI  |  LangGraph          │
├─────────────────────────────────────────────────────────────┤
│                    Tool Layer (MCP Server)                  │
│        get_toc()  |  smart_search()  |  read_page_range()   │
├─────────────────────────────────────────────────────────────┤
│                    Index Layer                              │
│            SQLite FTS5 (keyword) + LanceDB (semantic)       │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                            │
│         Docling JSON (structure) + Markdown (reading)       │
└─────────────────────────────────────────────────────────────┘
```

### Core Principles

1. **Page as Unit**: Store documents by physical pages, not arbitrary chunks. This preserves document structure and enables precise citation.

2. **Hybrid Retrieval**: Combine FTS5 keyword search (for device names, fault codes) with vector search (for symptom descriptions).

3. **Agentic Reasoning**: The LLM decides when to fetch more context—reading adjacent pages for truncated tables, following "see Note 3" references, or drilling into appendices.

4. **Multi-Framework**: Three agent implementations sharing the same MCP tools:
   - **Claude Agent SDK**: Optimal for Claude models with native MCP support
   - **Pydantic AI**: Type-safe, model-agnostic, production-ready
   - **LangGraph**: Complex workflow orchestration

## Data Model

Each page is stored as a `PageDocument` containing ordered `ContentBlock`s (text, tables, headings). This handles the common case of multiple tables per page:

```python
PageDocument
├── reg_id: "angui_2024"
├── page_num: 85
├── chapter_path: ["Chapter 6", "Fault Handling", "Bus Faults"]
├── content_blocks: [
│   ├── ContentBlock(type="heading", content="6.2 Bus Fault Response")
│   ├── ContentBlock(type="table", table_meta=TableMeta(...))
│   └── ContentBlock(type="table", table_meta=TableMeta(...))  # Multiple tables OK
│   ]
├── continues_to_next: true  # Table truncated, spans to P86
└── annotations: [Annotation(id="Note 1", content="...")]
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `get_toc(reg_id)` | Return chapter tree with page ranges—agent uses this to narrow search scope |
| `smart_search(query, reg_id, chapter_scope?)` | Hybrid search returning snippets with page numbers |
| `read_page_range(reg_id, start, end)` | Fetch full markdown for pages, auto-stitching cross-page tables |

## Agent Reasoning Flow

```
User: "How to handle 110kV bus voltage loss?"
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 1. TOC Routing                    │
    │    get_toc() → Chapter 6 (P40-90) │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 2. Targeted Search                │
    │    smart_search("bus voltage      │
    │    loss", chapter="Ch6")          │
    │    → P85 Table 6-2                │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 3. Deep Reading                   │
    │    read_page_range(85, 86)        │
    │    - Detect table continues → OK  │
    │    - Find "see Note 3" → resolve  │
    └───────────────────────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │ 4. Response with Citations        │
    │    [Source: 安规2024 P85 表6-2]   │
    └───────────────────────────────────┘
```

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Document Parser | Docling | Table structure recognition, provenance (page_no) tracking |
| Keyword Index | SQLite FTS5 | Zero-deployment, built into Python |
| Vector Index | LanceDB | Lightweight, hybrid search support |
| MCP Server | FastMCP | Official SDK, SSE transport |
| Agent Framework | Claude SDK / Pydantic AI / LangGraph | Flexibility for different deployment contexts |

## Project Status

Currently in design phase. Implementation roadmap:

- [ ] Phase 1: Docling integration, page-level storage
- [ ] Phase 2: FTS5 + LanceDB indexing
- [ ] Phase 3: MCP Server with SSE transport
- [ ] Phase 4-6: Three agent implementations

## License

MIT
