# GridCode Development Guide

## Project Overview

GridCode is an intelligent retrieval agent for power system safety regulations, using a Page-Based Agentic Search architecture.

**Core Design Principles**:
- Store documents by page, not arbitrary chunks
- LLM dynamically "flips through" pages, rather than one-shot vector matching
- Three parallel framework implementations (Claude Agent SDK / Pydantic AI / LangGraph)
- All agents access page data through MCP protocol (PageStore is controlled by MCP Server)

## Project Structure

```
src/grid_code/
├── parser/           # Docling parsing layer
├── storage/          # Page storage + Pydantic models
├── index/            # Pluggable index architecture
│   ├── base.py       # Abstract base classes
│   ├── keyword/      # Keyword indexes (FTS5/Tantivy/Whoosh)
│   └── vector/       # Vector indexes (LanceDB/Qdrant)
├── mcp/              # FastMCP Server + Client
├── agents/           # Three agent implementations
├── config.py
└── cli.py
```

## Tech Stack Constraints

| Component | Technology | Requirements |
|-----------|------------|--------------|
| Python | 3.12+ | Use modern type hint syntax |
| Document Parser | Docling | - |
| Keyword Index | SQLite FTS5 (default) | Built-in |
| Keyword Index | Tantivy (optional) | pip install grid-code[tantivy] |
| Keyword Index | Whoosh (optional) | pip install grid-code[whoosh] |
| Vector Index | LanceDB (default) | - |
| Vector Index | Qdrant (optional) | pip install grid-code[qdrant] |
| MCP Server | FastMCP | SSE transport |
| Data Models | Pydantic v2 | BaseModel |
| CLI | Typer | - |

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
PageDocument      # Page document (one page may contain multiple ContentBlocks)
ContentBlock      # Content block (text/table/heading/list)
TableMeta         # Table metadata (includes cross-page marker is_truncated)
Annotation        # Page annotations (Note 1, Option A, etc.)
```

## MCP Tool Interface

```python
# Three core tools in mcp/tools.py
get_toc(reg_id: str) -> TocTree
smart_search(query: str, reg_id: str, chapter_scope: str | None, limit: int) -> list[SearchResult]
read_page_range(reg_id: str, start_page: int, end_page: int) -> PageContent
```

## Development Constraints

### Required
- All MCP tool returns must include `source` field (reg_id + page_num)
- Cross-page tables must set `continues_to_next: true`
- Agent implementations must inherit from abstract base class in `agents/base.py`
- Index implementations must inherit from abstract base class in `index/base.py`
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

## Testing Standards

- Unit tests go in `tests/` directory
- Use `pytest` framework
- Mock external dependencies (LLM API, file system)

## Documentation Paths

| Document | Path |
|----------|------|
| Design Document | `docs/main/DESIGN_DOCUMENT.md` |
| Work Log | `docs/main/WORK_LOG.md` |
| Preliminary Design | `docs/PreliminaryDesign/` |

## Git Branch Strategy

- `main`: Stable release
- `feature/*`: Feature development
- `fix/*`: Bug fixes
