# GridCode Development Guide

## Project Overview

GridCode is an intelligent retrieval agent for power system safety regulations, using a **Page-Based Agentic Search** architecture.

**Core Design Principles**:
- Store documents by page, not arbitrary chunks
- LLM dynamically "flips through" pages, rather than one-shot vector matching
- Three parallel framework implementations (Claude Agent SDK / Pydantic AI / LangGraph)
- All agents access page data through MCP protocol (PageStore is controlled by MCP Server)

## Project Structure

```
src/grid_code/
├── parser/           # Docling parsing layer
│   ├── docling_parser.py      # Document parser with OCR support
│   ├── page_extractor.py      # Page content extraction
│   └── table_registry_builder.py  # Cross-page table handling
├── storage/          # Page storage + Pydantic models
│   ├── models.py             # Core data models (PageDocument, ContentBlock, etc.)
│   └── page_store.py         # Page persistence layer
├── index/            # Pluggable index architecture
│   ├── base.py               # Abstract base classes
│   ├── hybrid_search.py      # RRF-based hybrid retrieval
│   ├── table_search.py       # Table-specific search
│   ├── keyword/              # Keyword indexes (FTS5/Tantivy/Whoosh)
│   │   ├── fts5.py           # SQLite FTS5 (default)
│   │   ├── tantivy.py        # Tantivy (optional)
│   │   └── whoosh.py         # Whoosh (optional)
│   └── vector/               # Vector indexes (LanceDB/Qdrant)
│       ├── lancedb.py        # LanceDB (default)
│       └── qdrant.py         # Qdrant (optional)
├── embedding/        # Embedding model abstraction
│   ├── base.py               # Abstract embedding interface
│   ├── sentence_transformer.py   # SentenceTransformer backend
│   └── flag.py               # FlagEmbedding backend
├── mcp/              # FastMCP Server + Client
│   ├── server.py             # MCP server creation
│   ├── tools.py              # Core tool implementations
│   ├── tool_metadata.py      # Tool descriptions and metadata
│   └── client.py             # MCP client for agents
├── agents/           # Three agent implementations
│   ├── base.py               # Abstract agent base class
│   ├── claude_agent.py       # Claude Agent SDK implementation
│   ├── pydantic_agent.py     # Pydantic AI implementation
│   ├── langgraph_agent.py    # LangGraph implementation
│   ├── memory.py             # Conversation history management
│   ├── display.py            # Status display callbacks
│   └── mcp_connection.py     # MCP connection configuration
├── services/         # Business services
│   └── check_service.py      # Document check service
├── config.py         # Global configuration (pydantic-settings)
├── exceptions.py     # Custom exception hierarchy
└── cli.py            # Typer CLI interface
```

## Tech Stack Constraints

| Component | Technology | Requirements |
|-----------|------------|--------------|
| Python | 3.12+ | Use modern type hint syntax |
| Document Parser | Docling | OCR + table structure extraction |
| Keyword Index | SQLite FTS5 (default) | Built-in |
| Keyword Index | Tantivy (optional) | `pip install grid-code[tantivy]` |
| Keyword Index | Whoosh (optional) | `pip install grid-code[whoosh]` |
| Vector Index | LanceDB (default) | Arrow-based columnar storage |
| Vector Index | Qdrant (optional) | `pip install grid-code[qdrant]` |
| Embedding | SentenceTransformer (default) | BGE-small-zh-v1.5 |
| Embedding | FlagEmbedding (optional) | `pip install grid-code[flag]` |
| MCP Server | FastMCP | stdio/SSE transport |
| Data Models | Pydantic v2 | BaseModel |
| CLI | Typer + Rich | Colorful output |
| Agent Framework | Claude SDK / Pydantic AI / LangGraph | Triple implementation |

## Code Standards

### Type Annotations
- All functions must have type annotations
- Use `list[str]` instead of `List[str]` (Python 3.12+ syntax)
- Use `str | None` instead of `Optional[str]`

### Pydantic Models
- All data models inherit from `BaseModel`
- Use `model_dump()` instead of deprecated `dict()`
- Use `Field()` to add field descriptions

### Async
- MCP Server and Agent layer use `async/await`
- Index layer can be synchronous (SQLite/LanceDB operations are fast)

### Error Handling
- Use custom exception classes defined in `src/grid_code/exceptions.py`
- Use `loguru` for logging

## Key Data Models

```python
# Core models in storage/models.py

# Page-level models
PageDocument          # Single page document (core storage unit)
ContentBlock          # Content block (text/table/heading/list/section_content)
TableMeta             # Table metadata (cross-page marker, cells)
Annotation            # Page annotations (Note 1, Option A, etc.)

# Structure models
DocumentStructure     # Complete chapter tree structure
ChapterNode           # Chapter node with parent/children relationships
TableRegistry         # O(1) table lookup registry

# Search models
SearchResult          # Search result with score and source
TocTree / TocItem     # Table of contents hierarchy
```

## MCP Tool Interface

### Core Tools (Phase 0)

```python
# Basic retrieval tools
get_toc(reg_id: str) -> TocTree
smart_search(query, reg_id, chapter_scope, limit, block_types, section_number) -> list[SearchResult]
read_page_range(reg_id, start_page, end_page) -> PageContent
```

### Multi-hop Tools (Phase 1)

```python
# Cross-reference and annotation tools
lookup_annotation(reg_id, annotation_id, page_hint) -> AnnotationContent
search_tables(query, reg_id, mode, limit) -> list[TableSearchResult]
resolve_reference(reg_id, reference_text) -> ResolvedReference
```

### Context Tools (Phase 2)

```python
# Extended context retrieval
search_annotations(reg_id, query) -> list[Annotation]
get_table_by_id(reg_id, table_id) -> Table
get_block_with_context(reg_id, block_id, before, after) -> BlockContext
```

### Discovery Tools (Phase 3)

```python
# Semantic exploration
find_similar_content(reg_id, query, limit) -> list[SimilarContent]
compare_sections(reg_id, section1, section2) -> ComparisonResult
```

### Navigation Tools

```python
# Structure navigation
get_tool_guide() -> ToolGuide
get_chapter_structure(reg_id, section_number) -> ChapterStructure
read_chapter_content(reg_id, section_number) -> ChapterContent
```

## Development Constraints

### Required
- All MCP tool returns must include `source` field (reg_id + page_num)
- Cross-page tables must set `continues_to_next: true`
- Agent implementations must inherit from abstract base class in `agents/base.py`
- Index implementations must inherit from abstract base class in `index/base.py`
- Embedding implementations must inherit from abstract base class in `embedding/base.py`
- All agents must access page data through MCP protocol

### Prohibited
- Do not directly manipulate raw PDF/DOCX files in the index layer
- Do not hardcode regulation IDs; read from configuration
- Do not perform complex reasoning in MCP tools (reasoning belongs to Agent layer)
- Agents must not bypass MCP Server to access PageStore directly

### Index Layer Extension Guidelines
When adding a new index backend:
1. Inherit from `BaseKeywordIndex` or `BaseVectorIndex`
2. Implement all abstract methods
3. Export in `keyword/__init__.py` or `vector/__init__.py`
4. Register in the factory method in `hybrid_search.py`
5. Add optional dependency in `pyproject.toml`

### Embedding Layer Extension Guidelines
When adding a new embedding backend:
1. Inherit from `BaseEmbedding` in `embedding/base.py`
2. Implement `embed_query()` and `embed_documents()` methods
3. Export in `embedding/__init__.py`
4. Add optional dependency in `pyproject.toml`

## CLI Commands Reference

### Document Ingestion
```bash
gridcode ingest --file document.pdf --reg-id angui_2024
gridcode ingest --dir docs/ --format pdf
```

### MCP Server
```bash
gridcode serve --transport sse --port 8080   # SSE mode
gridcode serve --transport stdio             # stdio mode
```

### Search
```bash
gridcode search "母线失压" -r angui_2024 --chapter "第六章"
gridcode search "处理方法" --types text,table --limit 20
```

### Agent Chat
```bash
gridcode chat -r angui_2024 --agent pydantic  # Interactive mode
gridcode ask "母线失压如何处理?" -r angui_2024  # Single query
gridcode ask "..." --json                      # JSON output
```

### MCP Tools (CLI interface)
```bash
# Basic tools
gridcode toc angui_2024 --level 3 --expand
gridcode read-pages -r angui_2024 -s 10 -e 15
gridcode read-chapter -r angui_2024 -s "2.1.4.1.6"

# Multi-hop tools
gridcode lookup-annotation -r angui_2024 "注1" --page 45
gridcode search-tables "母线失压" -r angui_2024 --mode hybrid
gridcode resolve-reference -r angui_2024 "见第六章"

# Context tools
gridcode get-table angui_2024 table_001
gridcode get-block-context block_001 -r angui_2024

# Discovery tools
gridcode find-similar -r angui_2024 --query "故障处理"
gridcode compare-sections "2.1.4" "2.1.5" -r angui_2024
```

### Utility Commands
```bash
gridcode list                     # List all regulations
gridcode inspect angui_2024 10    # Inspect page data
gridcode delete angui_2024        # Delete regulation
gridcode mcp-tools --live         # List MCP tools
gridcode version                  # Show version
```

## Configuration

Configuration via environment variables (`GRIDCODE_*`) or `.env` file:

```bash
# Storage paths
GRIDCODE_DATA_DIR=./data/storage
GRIDCODE_PAGES_DIR=./data/storage/pages
GRIDCODE_INDEX_DIR=./data/storage/index

# Embedding
GRIDCODE_EMBEDDING_BACKEND=sentence_transformer  # or flag
GRIDCODE_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
GRIDCODE_EMBEDDING_DIMENSION=512

# MCP
GRIDCODE_MCP_HOST=127.0.0.1
GRIDCODE_MCP_PORT=8080
GRIDCODE_MCP_TRANSPORT=stdio  # or sse

# LLM (supports multiple backends)
GRIDCODE_LLM_MODEL_NAME=claude-sonnet-4-20250514
GRIDCODE_LLM_API_KEY=your-api-key
GRIDCODE_LLM_BASE_URL=https://api.anthropic.com

# Ollama backend (auto-detected, no additional config needed)
# GRIDCODE_LLM_BASE_URL=http://localhost:11434  # /v1 suffix auto-added
# GRIDCODE_LLM_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0
# GRIDCODE_OLLAMA_DISABLE_STREAMING=false  # set to true for some models

# Compatible with OPENAI_* environment variables (via validation_alias)
# OPENAI_BASE_URL=http://localhost:11434/v1
# OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# Index backends
GRIDCODE_KEYWORD_INDEX_BACKEND=fts5   # fts5, tantivy, whoosh
GRIDCODE_VECTOR_INDEX_BACKEND=lancedb # lancedb, qdrant

# Search weights
GRIDCODE_FTS_WEIGHT=0.4
GRIDCODE_VECTOR_WEIGHT=0.6
GRIDCODE_SEARCH_TOP_K=10

# LLM API Timing & Observability
GRIDCODE_TIMING_BACKEND=httpx        # httpx (CLI display) or otel (production monitoring)
GRIDCODE_OTEL_EXPORTER_TYPE=console  # console, otlp, jaeger, zipkin
GRIDCODE_OTEL_SERVICE_NAME=gridcode-agent
GRIDCODE_OTEL_ENDPOINT=http://localhost:4317  # For OTLP/Jaeger/Zipkin exporters
```

## Testing Standards

- Unit tests go in `tests/` directory
- Use `pytest` framework
- Mock external dependencies (LLM API, file system)
- Run tests: `pytest -xvs`

## Exception Hierarchy

```python
GridCodeError (base)
├── ParserError              # Document parsing error
├── StorageError             # Storage operation error
├── IndexError               # Index operation error
├── RegulationNotFoundError  # Regulation not found
├── PageNotFoundError        # Page not found
├── InvalidPageRangeError    # Invalid page range
├── ChapterNotFoundError     # Chapter not found
├── AnnotationNotFoundError  # Annotation not found
├── TableNotFoundError       # Table not found
└── ReferenceResolutionError # Cross-reference resolution error
```

## Documentation Paths

| Document | Path |
|----------|------|
| Design Document | `docs/dev/DESIGN_DOCUMENT.md` |
| Work Log | `docs/dev/WORK_LOG.md` |
| Preliminary Design | `docs/PreliminaryDesign/` |
| Embedding Architecture | `docs/dev/EMBEDDING_ARCHITECTURE.md` |
| MCP Tools Design | `docs/dev/MCP_TOOLS_DESIGN.md` |

## Git Branch Strategy

- `main`: Stable release
- `dev`: Development branch
- `feature/*`: Feature development
- `fix/*`: Bug fixes
