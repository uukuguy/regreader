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
│                    Index Layer (Pluggable)                  │
│  Keyword: FTS5 / Tantivy / Whoosh                           │
│  Vector:  LanceDB / Qdrant                                  │
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

5. **Unified MCP Access**: All agents access page data through MCP protocol—the PageStore is controlled internally by the MCP Server, ensuring consistent data access patterns.

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
| Keyword Index | SQLite FTS5 (default) | Zero-deployment, built into Python |
| Keyword Index | Tantivy (optional) | High-performance Rust engine |
| Keyword Index | Whoosh (optional) | Pure Python, Chinese tokenization support |
| Vector Index | LanceDB (default) | Lightweight, hybrid search support |
| Vector Index | Qdrant (optional) | Production-grade, distributed support |
| MCP Server | FastMCP | Official SDK, SSE transport |
| Agent Framework | Claude SDK / Pydantic AI / LangGraph | Flexibility for different deployment contexts |

## Installation

```bash
# Basic installation
pip install grid-code

# With optional index backends
pip install grid-code[tantivy]     # High-performance keyword search
pip install grid-code[whoosh]      # Chinese tokenization support
pip install grid-code[qdrant]      # Production vector database

# Install all index backends
pip install grid-code[all-indexes]
```

## Configuration

Configure index backends via environment variables:

```bash
# Select keyword index backend (fts5/tantivy/whoosh)
export GRIDCODE_KEYWORD_INDEX_BACKEND=fts5

# Select vector index backend (lancedb/qdrant)
export GRIDCODE_VECTOR_INDEX_BACKEND=lancedb

# Qdrant server configuration (if using qdrant)
export GRIDCODE_QDRANT_URL=http://localhost:6333
```

## Agent Setup

GridCode provides three agent implementations. Each agent communicates with the MCP Server through MCP protocol:

### Claude Agent SDK (Recommended for Claude models)

Uses the official Claude Agent SDK with native MCP support:

```bash
# Set API key
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# Start chat with Claude Agent
gridcode chat --agent claude --reg-id angui_2024
```

### Pydantic AI Agent (Multi-model support)

Type-safe agent supporting multiple LLM providers:

```bash
# For Anthropic models
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# For OpenAI models
export GRIDCODE_OPENAI_API_KEY="your-api-key"

# Start chat
gridcode chat --agent pydantic --reg-id angui_2024
```

### LangGraph Agent (Complex workflows)

For advanced workflow orchestration:

```bash
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

gridcode chat --agent langgraph --reg-id angui_2024
```

### Ollama Backend (Local LLM)

All agents support Ollama for local LLM deployment:

```bash
# Option 1: Use OPENAI_* environment variables (recommended)
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# Option 2: Use GRIDCODE_* environment variables
export GRIDCODE_LLM_BASE_URL=http://localhost:11434
export GRIDCODE_LLM_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# Optional: Disable streaming for certain models
export GRIDCODE_OLLAMA_DISABLE_STREAMING=false

# Start chat (works with all agents)
gridcode chat --agent pydantic --reg-id angui_2024
gridcode chat --agent langgraph --reg-id angui_2024
```

**Auto-detection**: Ollama backend is automatically detected when:
- `base_url` contains `:11434` (Ollama's default port)
- `base_url` contains `ollama` keyword

**Note**: The httpx transport fix is automatically applied for Ollama backends to resolve compatibility issues.

### Architecture Note

All agents access page data through MCP protocol:

```
┌─────────────────────────────────────────────────┐
│                 Agent Layer                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐ │
│  │ ClaudeAgent │  │ LangGraph   │  │ Pydantic │ │
│  │ (SDK MCP)   │  │ Agent       │  │ AI Agent │ │
│  └──────┬──────┘  └──────┬──────┘  └────┬─────┘ │
│         │                │               │       │
│         │         ┌──────┴───────────────┘       │
│         │         │                              │
│         │         ▼                              │
│         │  GridCodeMCPClient                     │
└─────────┼─────────┬──────────────────────────────┘
          │         │
          │  stdio  │  stdio
          ▼         ▼
┌─────────────────────────────────────────────────┐
│              GridCode MCP Server                 │
│   get_toc | smart_search | read_page_range      │
└─────────────────────────────────────────────────┘
```

## Project Status

Core implementation complete. Remaining work:

- [x] Phase 1: Docling integration, page-level storage
- [x] Phase 2: FTS5 + LanceDB indexing (with pluggable backends)
- [x] Phase 3: MCP Server with SSE transport
- [x] Phase 4-6: Three agent implementations
- [x] LLM API timing & observability (httpx + OpenTelemetry)
- [ ] End-to-end testing with real regulation documents
- [ ] Performance benchmarking across index backends

## References

[Docling Documentation - Examples](https://docling-project.github.io/docling/examples/)

## License

MIT
