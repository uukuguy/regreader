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
| **Context Overload** | Single agent with all tools (~4000 tokens) | Specialized subagents (~800 tokens each) |
| **Scalability** | Context grows with task complexity | Orchestrator routes to relevant experts only |

## Design Philosophy

Inspired by how Claude Code searches codebases, GridCode treats regulations as "books to browse" rather than "vectors to match":

```
┌─────────────────────────────────────────────────────────────┐
│                    Business Layer (CLI/API)                  │
├─────────────────────────────────────────────────────────────┤
│                    Reasoning Layer                           │
│     Claude Agent SDK  |  Pydantic AI  |  LangGraph           │
├─────────────────────────────────────────────────────────────┤
│                    Orchestrator Layer                        │
│        QueryAnalyzer → Router → ResultAggregator             │
│        (Context: ~800 tokens per orchestrator)               │
├─────────────────────────────────────────────────────────────┤
│                    Subagents Layer                           │
│   SEARCH | TABLE | REFERENCE | DISCOVERY (Each ~600 tokens) │
├─────────────────────────────────────────────────────────────┤
│                    Infrastructure Layer                      │
│   FileContext | EventBus | SecurityGuard | SkillLoader       │
├─────────────────────────────────────────────────────────────┤
│                    Tool Layer (MCP Server)                   │
│        get_toc()  |  smart_search()  |  read_page_range()    │
├─────────────────────────────────────────────────────────────┤
│                    Index Layer (Pluggable)                   │
│  Keyword: FTS5 / Tantivy / Whoosh                            │
│  Vector:  LanceDB / Qdrant                                   │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                             │
│         Docling JSON (structure) + Markdown (reading)        │
└─────────────────────────────────────────────────────────────┘
```

### Core Principles

1. **Page as Unit**: Store documents by physical pages, not arbitrary chunks. This preserves document structure and enables precise citation.

2. **Hybrid Retrieval**: Combine FTS5 keyword search (for device names, fault codes) with vector search (for symptom descriptions).

3. **Agentic Reasoning**: The LLM decides when to fetch more context—reading adjacent pages for truncated tables, following "see Note 3" references, or drilling into appendices.

4. **Context Isolation**: Use specialized subagents for different tasks (search, table extraction, reference resolution), reducing context from ~4000 to ~800 tokens per orchestrator.

5. **Orchestrator Pattern**: Central coordinator analyzes intent, routes to relevant subagents, and aggregates results—enabling efficient multi-hop reasoning.

6. **Multi-Framework**: Three agent implementations sharing the same MCP tools:
   - **Claude Agent SDK**: Optimal for Claude models with native MCP support
   - **Pydantic AI**: Type-safe, model-agnostic, production-ready
   - **LangGraph**: Complex workflow orchestration

7. **Unified MCP Access**: All agents access page data through MCP protocol—the PageStore is controlled internally by the MCP Server, ensuring consistent data access patterns.

8. **Bash+FS Paradigm**: File-based communication for agent coordination, with infrastructure layer providing FileContext, EventBus, SecurityGuard, and SkillLoader.

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

GridCode provides three agent implementations, each supporting both standard and orchestrator modes:

### Standard Mode vs Orchestrator Mode

**Standard Mode**: Single agent with all MCP tools (~4000 tokens context)
- Best for: Simple, single-hop queries
- Context: Includes all tool descriptions and full protocol

**Orchestrator Mode**: Specialized subagents coordinated by orchestrator (~800 tokens per orchestrator)
- Best for: Complex, multi-hop queries requiring multiple tool types
- Context: Each subagent only sees relevant tools
- Benefits: Reduced context, better focus, parallel execution

### Claude Agent SDK (Recommended for Claude models)

Uses the official Claude Agent SDK with native MCP support:

```bash
# Set API key
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# Standard mode
gridcode chat --agent claude --reg-id angui_2024

# Orchestrator mode (context-efficient)
gridcode chat --agent claude --reg-id angui_2024 --orchestrator
gridcode chat-claude-orch --reg-id angui_2024  # Shortcut
```

### Pydantic AI Agent (Multi-model support)

Type-safe agent supporting multiple LLM providers:

```bash
# For Anthropic models
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# For OpenAI models
export GRIDCODE_OPENAI_API_KEY="your-api-key"

# Standard mode
gridcode chat --agent pydantic --reg-id angui_2024

# Orchestrator mode
gridcode chat --agent pydantic --reg-id angui_2024 -o  # -o is short for --orchestrator
gridcode chat-pydantic-orch --reg-id angui_2024  # Shortcut
```

### LangGraph Agent (Complex workflows)

For advanced workflow orchestration:

```bash
export GRIDCODE_ANTHROPIC_API_KEY="your-api-key"

# Standard mode
gridcode chat --agent langgraph --reg-id angui_2024

# Orchestrator mode
gridcode chat --agent langgraph --reg-id angui_2024 --orchestrator
gridcode chat-langgraph-orch --reg-id angui_2024  # Shortcut
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

All agents access page data through MCP protocol, with optional orchestrator mode for context efficiency:

```
┌─────────────────────────────────────────────────────────────┐
│                 Agent Layer (3 Frameworks)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │ ClaudeAgent  │  │ LangGraph    │  │ Pydantic      │      │
│  │ (SDK MCP)    │  │ Agent        │  │ AI Agent      │      │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘      │
│         │                 │                   │              │
│         │                 │                   │              │
│         ▼                 ▼                   ▼              │
│   ┌─────────────────────────────────────────────────┐       │
│   │  Optional: Orchestrator Layer                   │       │
│   │  QueryAnalyzer → SubagentRouter → Aggregator    │       │
│   │  (Context isolation: ~800 tokens per orch)      │       │
│   └─────────────────────────────────────────────────┘       │
│         │                 │                   │              │
│         │                 ▼                   │              │
│         │         GridCodeMCPClient           │              │
└─────────┼─────────────────┬───────────────────┼──────────────┘
          │                 │                   │
          │   stdio         │   stdio           │   stdio
          ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│              GridCode MCP Server (16+ tools)                 │
│   get_toc | smart_search | read_page_range | ...            │
└─────────────────────────────────────────────────────────────┘
```

## Project Status

Architecture evolution complete through Phase 6:

- [x] Phase 1: Docling integration, page-level storage
- [x] Phase 2: FTS5 + LanceDB indexing (with pluggable backends)
- [x] Phase 3: MCP Server with SSE transport (16+ tools)
- [x] Phase 4: Three agent implementations (Claude SDK, Pydantic AI, LangGraph)
- [x] Phase 5: Subagents architecture with orchestrator layer
- [x] Phase 6: Bash+FS paradigm with infrastructure layer
- [x] LLM API timing & observability (httpx + OpenTelemetry)
- [x] Multi-regulation search with smart selection
- [ ] End-to-end testing with real regulation documents
- [ ] Performance benchmarking across index backends
- [ ] Exec-Subagent: Script execution with sandboxing
- [ ] Validator-Subagent: Result validation and quality assurance

**Latest Features**:
- Context isolation: Reduced from ~4000 to ~800 tokens per orchestrator
- Infrastructure layer: FileContext, EventBus, SecurityGuard, SkillLoader
- RegSearch-Subagent: Domain expert integrating SEARCH/TABLE/REFERENCE/DISCOVERY
- Modular Makefile: Organized commands in `makefiles/*.mk`
- Comprehensive testing: `tests/bash-fs-paradiam/` with 5 test suites

## References

[Docling Documentation - Examples](https://docling-project.github.io/docling/examples/)

## License

MIT
