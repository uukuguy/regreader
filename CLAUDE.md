# GridCode Development Guide

## Project Overview

GridCode is an intelligent retrieval agent for power system safety regulations, using a **Page-Based Agentic Search** architecture with **Bash+FS Subagents** paradigm.

**Core Design Principles**:
- Store documents by page, not arbitrary chunks
- LLM dynamically "flips through" pages, rather than one-shot vector matching
- **Layered architecture**: Infrastructure → Orchestrator → Subagents → MCP Tools → Storage
- **Context isolation**: Reduce agent context from ~4000 tokens to ~800 tokens through specialized subagents
- **File-based communication**: Bash+FS paradigm for agent coordination and state management
- Three parallel framework implementations (Claude Agent SDK / Pydantic AI / LangGraph)
- All agents access page data through MCP protocol (PageStore is controlled by MCP Server)

## Architecture Layers

GridCode implements a 7-layer architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Business Layer (CLI / API)                   │
├─────────────────────────────────────────────────────────────────┤
│                     Agent Framework Layer                        │
│           Claude SDK  |  Pydantic AI  |  LangGraph               │
├─────────────────────────────────────────────────────────────────┤
│                     Orchestrator Layer                           │
│   QueryAnalyzer → SubagentRouter → ResultAggregator             │
├─────────────────────────────────────────────────────────────────┤
│                     Subagents Layer (Domain Experts)             │
│   RegSearch-Subagent (SEARCH/TABLE/REFERENCE/DISCOVERY)         │
├─────────────────────────────────────────────────────────────────┤
│                     Infrastructure Layer                         │
│   FileContext | SkillLoader | EventBus | SecurityGuard          │
├─────────────────────────────────────────────────────────────────┤
│                     MCP Tool Layer                               │
│   16+ tools organized by phase (BASE/MULTI_HOP/CONTEXT/...)     │
├─────────────────────────────────────────────────────────────────┤
│                     Storage & Index Layer                        │
│   PageStore | HybridSearch | FTS5/LanceDB | Embedding           │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
grid-code/
├── coordinator/                      # Coordinator workspace (Bash+FS)
│   ├── CLAUDE.md                     # Project entry point
│   ├── plan.md                       # Task planning (runtime)
│   ├── session_state.json            # Session state (runtime)
│   └── logs/
│
├── subagents/                        # Subagent workspaces (Bash+FS)
│   ├── regsearch/                    # RegSearch-Subagent
│   │   ├── SKILL.md                  # Skill documentation
│   │   ├── scratch/                  # Temporary results
│   │   └── logs/
│   ├── exec/                         # Exec-Subagent (reserved)
│   └── validator/                    # Validator-Subagent (reserved)
│
├── shared/                           # Shared read-only resources
│   ├── data/ → data/storage/         # Symlink to storage
│   ├── docs/                         # Tool usage guides
│   └── templates/                    # Output templates
│
├── skills/                           # Skill registry (Bash+FS)
│   ├── registry.yaml                 # Skill registry
│   ├── simple_search/
│   ├── table_lookup/
│   └── cross_ref/
│
├── src/grid_code/                    # Source code
│   ├── infrastructure/               # Infrastructure layer (NEW)
│   │   ├── file_context.py           # File context manager
│   │   ├── skill_loader.py           # Skill loader
│   │   ├── event_bus.py              # Pub/sub event bus
│   │   └── security_guard.py         # Permission control
│   │
│   ├── orchestrator/                 # Orchestrator layer (NEW)
│   │   ├── coordinator.py            # Central coordinator
│   │   ├── analyzer.py               # Query intent analyzer
│   │   ├── router.py                 # Subagent router
│   │   └── aggregator.py             # Result aggregator
│   │
│   ├── subagents/                    # Subagents layer (ENHANCED)
│   │   ├── base.py                   # BaseSubagent abstract class
│   │   ├── config.py                 # SubagentConfig, SubagentType
│   │   ├── registry.py               # SubagentRegistry
│   │   ├── result.py                 # SubagentResult
│   │   ├── prompts.py                # Subagent prompts
│   │   ├── regsearch/                # RegSearch-Subagent implementation
│   │   ├── search/                   # Search component
│   │   ├── table/                    # Table component
│   │   ├── reference/                # Reference component
│   │   └── discovery/                # Discovery component
│   │
│   ├── agents/                       # Agent framework implementations
│   │   ├── claude/                   # Claude SDK implementation
│   │   │   ├── orchestrator.py       # ClaudeOrchestrator (Handoff Pattern)
│   │   │   └── subagents.py          # Claude subagent builders
│   │   ├── pydantic/                 # Pydantic AI implementation
│   │   │   ├── orchestrator.py       # PydanticOrchestrator (Delegation)
│   │   │   └── subagents.py          # Pydantic subagent builders
│   │   ├── langgraph/                # LangGraph implementation
│   │   │   ├── orchestrator.py       # LangGraphOrchestrator (Subgraph)
│   │   │   └── subgraphs.py          # LangGraph subgraph builders
│   │   ├── memory.py                 # Conversation history
│   │   ├── display.py                # Status display
│   │   └── mcp_connection.py         # MCP connection
│   │
│   ├── parser/                       # Docling parsing layer
│   │   ├── docling_parser.py
│   │   ├── page_extractor.py
│   │   └── table_registry_builder.py
│   │
│   ├── storage/                      # Page storage + Pydantic models
│   │   ├── models.py                 # PageDocument, ContentBlock, etc.
│   │   └── page_store.py             # Page persistence
│   │
│   ├── index/                        # Pluggable index architecture
│   │   ├── base.py
│   │   ├── hybrid_search.py
│   │   ├── table_search.py
│   │   ├── keyword/                  # FTS5/Tantivy/Whoosh
│   │   └── vector/                   # LanceDB/Qdrant
│   │
│   ├── embedding/                    # Embedding abstraction
│   │   ├── base.py
│   │   ├── sentence_transformer.py
│   │   └── flag.py
│   │
│   ├── mcp/                          # FastMCP Server + Client
│   │   ├── server.py
│   │   ├── tools.py
│   │   ├── tool_metadata.py
│   │   └── client.py
│   │
│   ├── services/                     # Business services
│   │   ├── check_service.py
│   │   └── metadata_service.py       # Multi-regulation metadata
│   │
│   ├── config.py                     # Global configuration
│   ├── exceptions.py                 # Custom exceptions
│   └── cli.py                        # Typer CLI
│
├── makefiles/                        # Modular Makefile (NEW)
│   ├── variables.mk                  # Common variables
│   ├── conda.mk                      # Conda environment commands
│   ├── agents.mk                     # Agent commands
│   └── mcp-tools.mk                  # MCP tool commands
│
├── tests/                            # Test suites
│   ├── bash-fs-paradiam/             # Bash+FS architecture tests
│   │   ├── test_event_bus.py
│   │   ├── test_file_context.py
│   │   ├── test_security_guard.py
│   │   ├── test_skill_loader.py
│   │   └── test_regsearch_subagent.py
│   └── ...
│
└── docs/                             # Documentation
    ├── bash-fs-paradiam/             # Bash+FS architecture docs
    │   ├── ARCHITECTURE_DESIGN.md
    │   ├── API_REFERENCE.md
    │   ├── USER_GUIDE.md
    │   ├── MAKEFILE_REFACTORING.md
    │   └── WORK_LOG.md
    ├── subagents/                    # Subagents architecture docs
    │   ├── SUBAGENTS_ARCHITECTURE.md
    │   └── WORK_LOG.md
    └── dev/                          # Development docs
        ├── DESIGN_DOCUMENT.md
        ├── WORK_LOG.md
        ├── MCP_TOOLS_DESIGN.md
        └── ...
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

## Key Components

### Infrastructure Layer

The infrastructure layer provides common facilities for file-based agent communication:

**FileContext** (`infrastructure/file_context.py`)
- File context manager with read/write isolation
- Manages workspace directories: `scratch/`, `logs/`
- Methods: `read_skill()`, `read_scratch()`, `write_scratch()`, `read_shared()`, `log()`

**SkillLoader** (`infrastructure/skill_loader.py`)
- Dynamic skill loading from `SKILL.md` and `skills/registry.yaml`
- Supports YAML frontmatter and pure Markdown formats
- Methods: `load_all()`, `get_skill()`, `get_skills_for_subagent()`

**EventBus** (`infrastructure/event_bus.py`)
- Pub/sub event bus with JSONL persistence
- 14 event types: TASK_STARTED, TASK_COMPLETED, HANDOFF_REQUEST, etc.
- Methods: `publish()`, `subscribe()`, `replay_events()`

**SecurityGuard** (`infrastructure/security_guard.py`)
- Swiss cheese defense model with 3 layers
- Directory isolation, tool control, audit logging
- Methods: `check_file_access()`, `check_tool_access()`, `audit_log()`

### Orchestrator Layer

The orchestrator layer coordinates query processing across specialized subagents:

**Coordinator** (`orchestrator/coordinator.py`)
- Central query dispatcher with session management
- Workflow: analyze → route → execute → aggregate
- Supports file-based task dispatch (Bash+FS mode)

**QueryAnalyzer** (`orchestrator/analyzer.py`)
- Intent analysis and hint extraction
- Returns `QueryIntent` with primary/secondary subagent types
- Extracts: chapter_scope, table_hint, annotation_hint, reference_text, etc.

**SubagentRouter** (`orchestrator/router.py`)
- Routes queries to appropriate subagents
- Execution modes: sequential (with context passing) or parallel

**ResultAggregator** (`orchestrator/aggregator.py`)
- Merges results from multiple subagents
- Deduplicates sources, consolidates tool calls

### Subagents Layer

**RegSearch-Subagent** (`subagents/regsearch/`)
- Domain expert for regulation retrieval
- Integrates 4 internal components: SEARCH, TABLE, REFERENCE, DISCOVERY
- Supports Bash+FS file system mode

**Internal Components**:
- SearchAgent: Document search and navigation (4 tools)
- TableAgent: Table search and extraction (3 tools)
- ReferenceAgent: Cross-reference resolution (3 tools)
- DiscoveryAgent: Semantic analysis (2 tools, optional)

### Agent Framework Implementations

**Claude SDK** (`agents/claude/`): Handoff Pattern with nested agents
**Pydantic AI** (`agents/pydantic/`): Delegation Pattern with @tool decorators
**LangGraph** (`agents/langgraph/`): Subgraph Pattern with state management

All three frameworks share:
- Unified `BaseSubagent` abstraction
- Consistent `SubagentConfig` definitions
- Standard `SubagentResult` format

## Key Data Models

```python
# Infrastructure models
@dataclass
class Skill:
    name: str
    description: str
    entry_point: str
    required_tools: list[str]
    subagents: list[str]

@dataclass
class Event:
    event_type: SubagentEvent
    subagent_id: str
    timestamp: datetime
    payload: dict[str, Any]

# Orchestrator models
@dataclass
class QueryIntent:
    primary_type: SubagentType
    secondary_types: list[SubagentType]
    confidence: float
    hints: dict[str, Any]
    requires_multi_hop: bool

@dataclass
class SessionState:
    session_id: str
    query_count: int
    current_reg_id: str | None
    accumulated_sources: list[str]

# Subagent models
@dataclass
class SubagentContext:
    query: str
    reg_id: str | None
    chapter_scope: str | None
    hints: dict[str, Any]
    max_iterations: int

@dataclass
class SubagentResult:
    content: str
    sources: list[str]
    tool_calls: list[dict]
    metadata: dict[str, Any]

# Storage models
PageDocument          # Single page document (core storage unit)
ContentBlock          # Content block (text/table/heading/list/section_content)
TableMeta             # Table metadata (cross-page marker, cells)
Annotation            # Page annotations (Note 1, Option A, etc.)
DocumentStructure     # Complete chapter tree structure
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
- Subagent implementations must inherit from `BaseSubagent` in `subagents/base.py`
- Index implementations must inherit from abstract base class in `index/base.py`
- Embedding implementations must inherit from abstract base class in `embedding/base.py`
- All agents must access page data through MCP protocol
- Infrastructure components must support both sync and async APIs
- Orchestrator must support both normal and file-based (Bash+FS) modes

### Prohibited
- Do not directly manipulate raw PDF/DOCX files in the index layer
- Do not hardcode regulation IDs; read from configuration
- Do not perform complex reasoning in MCP tools (reasoning belongs to Agent layer)
- Agents must not bypass MCP Server to access PageStore directly
- Subagents must not access files outside their allowed directories
- Do not hardcode MCP tool lists in agents; use SubagentConfig

### Architecture Extension Guidelines

**Adding a New Index Backend**:
1. Inherit from `BaseKeywordIndex` or `BaseVectorIndex`
2. Implement all abstract methods
3. Export in `keyword/__init__.py` or `vector/__init__.py`
4. Register in the factory method in `hybrid_search.py`
5. Add optional dependency in `pyproject.toml`

**Adding a New Embedding Backend**:
1. Inherit from `BaseEmbedding` in `embedding/base.py`
2. Implement `embed_query()` and `embed_documents()` methods
3. Export in `embedding/__init__.py`
4. Add optional dependency in `pyproject.toml`

**Adding a New Subagent Type**:
1. Add enum value to `SubagentType` in `subagents/config.py`
2. Create subagent directory in `subagents/`
3. Implement subagent class inheriting from `BaseSubagent`
4. Register in `SubagentRegistry`
5. Add configuration in `SUBAGENT_CONFIGS`
6. Create corresponding builders in all three agent frameworks
7. Add workspace directory in project root
8. Update Security Guard permissions

**Adding a New Skill**:
1. Create skill directory in `skills/`
2. Add `SKILL.md` with YAML frontmatter
3. Register in `skills/registry.yaml`
4. Implement entry point script/module
5. Update tests in `tests/bash-fs-paradiam/`

## CLI Commands Reference

### Document Ingestion
```bash
gridcode ingest --file document.pdf --reg-id angui_2024
gridcode ingest --dir docs/ --format pdf
gridcode enrich-metadata angui_2024  # Generate metadata with LLM
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
gridcode search "keyword" --all              # Search across all regulations
```

### Agent Chat (Standard Mode)
```bash
# Basic chat
gridcode chat -r angui_2024 --agent pydantic   # Interactive mode
gridcode ask "母线失压如何处理?" -r angui_2024   # Single query
gridcode ask "..." --json                       # JSON output

# Framework-specific commands
gridcode chat-claude -r angui_2024             # Claude SDK agent
gridcode chat-pydantic -r angui_2024           # Pydantic AI agent
gridcode chat-langgraph -r angui_2024          # LangGraph agent

# SSE mode (non-blocking)
gridcode chat-claude-sse -r angui_2024
gridcode chat-pydantic-sse -r angui_2024
gridcode chat-langgraph-sse -r angui_2024
```

### Agent Chat (Orchestrator Mode)
```bash
# Use orchestrator for context-efficient queries
gridcode chat -r angui_2024 --agent pydantic --orchestrator
gridcode chat -r angui_2024 --agent pydantic -o  # Short form
gridcode ask "..." -r angui_2024 --orchestrator

# Framework-specific orchestrator commands
gridcode chat-claude-orch -r angui_2024
gridcode chat-pydantic-orch -r angui_2024
gridcode chat-langgraph-orch -r angui_2024
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

### Makefile Commands
```bash
# Basic commands
make install                      # Install dependencies
make install-dev                  # Install with dev dependencies
make test                         # Run tests
make test-bash-fs                 # Test Bash+FS architecture
make verify-bash-fs               # Verify architecture (no pytest needed)

# Agent commands
make chat AGENT=pydantic REG=angui_2024
make ask QUERY="..." AGENT=pydantic REG=angui_2024
make chat-orch AGENT=pydantic REG=angui_2024  # Orchestrator mode

# Framework-specific shortcuts
make chat-claude REG=angui_2024
make chat-pydantic REG=angui_2024
make chat-langgraph REG=angui_2024

# MCP tool commands
make search QUERY="..." REG=angui_2024
make toc REG=angui_2024
make read-pages REG=angui_2024 START=10 END=15

# Conda commands
make conda-chat AGENT=pydantic REG=angui_2024
make conda-ask QUERY="..." AGENT=pydantic REG=angui_2024
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
| **Architecture Documents** | |
| Bash+FS Architecture Design | `docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md` |
| Bash+FS API Reference | `docs/bash-fs-paradiam/API_REFERENCE.md` |
| Bash+FS User Guide | `docs/bash-fs-paradiam/USER_GUIDE.md` |
| Bash+FS Work Log | `docs/bash-fs-paradiam/WORK_LOG.md` |
| Makefile Refactoring | `docs/bash-fs-paradiam/MAKEFILE_REFACTORING.md` |
| Subagents Architecture | `docs/subagents/SUBAGENTS_ARCHITECTURE.md` |
| Subagents Work Log | `docs/subagents/WORK_LOG.md` |
| **Development Documents** | |
| Design Document | `docs/dev/DESIGN_DOCUMENT.md` |
| Work Log | `docs/dev/WORK_LOG.md` |
| MCP Tools Design | `docs/dev/MCP_TOOLS_DESIGN.md` |
| Embedding Architecture | `docs/dev/EMBEDDING_ARCHITECTURE.md` |
| Multi-Regulation Search Design | `docs/dev/MULTI_REGULATION_SEARCH_DESIGN.md` |
| **Preliminary Design** | `docs/PreliminaryDesign/` |

## Architecture Evolution

GridCode has evolved through multiple architectural iterations:

### Phase 1: Basic Page-Based Storage (Completed)
- Docling document parsing with OCR support
- Page-level storage with ContentBlock models
- Cross-page table handling with `continues_to_next` marker

### Phase 2: Hybrid Retrieval (Completed)
- FTS5 keyword search + LanceDB vector search
- RRF-based result fusion
- Pluggable index backends (Tantivy, Whoosh, Qdrant)

### Phase 3: MCP Tool Layer (Completed)
- FastMCP server with 16+ tools
- Tool classification: BASE / MULTI_HOP / CONTEXT / DISCOVERY
- stdio and SSE transport modes

### Phase 4: Multi-Framework Agents (Completed)
- Claude Agent SDK implementation
- Pydantic AI implementation
- LangGraph implementation

### Phase 5: Subagents Architecture (Completed)
- Context isolation: ~4000 tokens → ~800 tokens per orchestrator
- 4 specialized subagents: SEARCH, TABLE, REFERENCE, DISCOVERY
- Orchestrator layer: QueryAnalyzer → SubagentRouter → ResultAggregator
- Unified abstraction across three frameworks

### Phase 6: Bash+FS Paradigm (Current)
- Infrastructure layer: FileContext, SkillLoader, EventBus, SecurityGuard
- RegSearch-Subagent as domain expert
- File-based communication for agent coordination
- Skills system with registry and SKILL.md
- Coordinator for centralized query dispatch

### Future Phases (Planned)
- Exec-Subagent: Script execution with sandboxing
- Validator-Subagent: Result validation and quality assurance
- Multi-regulation reasoning: Cross-regulation query support
- Streaming aggregation: Real-time result streaming

## Git Branch Strategy

- `main`: Stable release
- `dev`: Development branch
- `feature/*`: Feature development
- `fix/*`: Bug fixes
