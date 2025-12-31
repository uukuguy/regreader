# GridCode Makefile
# Power Grid Regulations Intelligent Retrieval Agent

.PHONY: help install install-dev install-all test test-mcp test-heading lint format check serve serve-stdio chat build clean reindex read-chapter \
	ask ask-json ask-claude ask-pydantic ask-langgraph \
	toc read-pages chapter-structure page-info lookup-annotation search-tables resolve-reference \
	search-annotations get-table get-block-context find-similar compare-sections \
	build-table-registry table-registry-stats list-cross-page-tables build-table-index \
	list-mcp search-mcp toc-mcp read-pages-mcp list-mcp-sse search-mcp-sse toc-mcp-sse read-pages-mcp-sse \
	chat-mcp-sse chat-claude-sse chat-pydantic-sse chat-langgraph-sse \
	mcp-tools mcp-tools-v mcp-tools-live mcp-verify mcp-verify-v mcp-verify-sse

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python
UV := uv
PYTEST := pytest
RUFF := ruff

# MCP Mode Configuration
# MODE: local (default), mcp-stdio, mcp-sse
MODE ?= local
MCP_URL ?= http://127.0.0.1:8080/sse

# Generate CLI flags based on MODE
ifeq ($(MODE),mcp-stdio)
    MCP_FLAGS := --mcp
else ifeq ($(MODE),mcp-sse)
    MCP_FLAGS := --mcp --mcp-transport sse --mcp-url $(MCP_URL)
else
    MCP_FLAGS :=
endif

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

#----------------------------------------------------------------------
# Help
#----------------------------------------------------------------------

help: ## Show this help message
	@echo "$(BLUE)GridCode - Power Grid Regulations Intelligent Retrieval Agent$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make install-dev              # Install with dev dependencies"
	@echo "  make test                     # Run all tests"
	@echo "  make serve                    # Start MCP server (SSE mode)"
	@echo "  make chat REG_ID=angui        # Start interactive chat"
	@echo "  make ask ASK_QUERY=\"母线失压如何处理?\"  # Single query (non-interactive)"
	@echo "  make ask-json ASK_QUERY=\"...\" # Single query with JSON output"
	@echo ""
	@echo "$(GREEN)MCP Tools Testing:$(NC)"
	@echo "  make toc                      # Get regulation TOC"
	@echo "  make read-pages START_PAGE=85 END_PAGE=87"
	@echo "  make search-tables TABLE_QUERY=\"母线失压\" TABLE_SEARCH_MODE=keyword"
	@echo "  make build-table-index        # Build table FTS5 + vector index"
	@echo "  make lookup-annotation ANNOTATION_ID=\"注1\" PAGE_NUM=85"
	@echo "  make resolve-reference REFERENCE=\"见第六章\""
	@echo "  make find-similar SIMILAR_QUERY=\"母线失压处理\""
	@echo "  make compare-sections SECTION_A=\"2.1.4\" SECTION_B=\"2.1.5\""
	@echo ""
	@echo "$(GREEN)MCP Mode Switching:$(NC)"
	@echo "  MODE=local       (default) Direct local access"
	@echo "  MODE=mcp-stdio   Via MCP Server (stdio transport)"
	@echo "  MODE=mcp-sse     Via MCP Server (SSE transport, needs 'make serve')"
	@echo ""
	@echo "  make list MODE=mcp-stdio      # List via MCP stdio"
	@echo "  make search MODE=mcp-sse QUERY=\"母线失压\"  # Search via MCP SSE"
	@echo "  make chat MODE=mcp-sse AGENT=claude      # Chat via MCP SSE"
	@echo "  make chat-claude-sse          # Chat with Claude Agent via SSE"

#----------------------------------------------------------------------
# Installation
#----------------------------------------------------------------------

install: ## Install base dependencies
	$(UV) sync

install-dev: ## Install with dev dependencies (pytest, ruff)
	$(UV) sync --extra dev

install-all: ## Install with all optional index backends
	$(UV) sync --extra dev --extra tantivy --extra whoosh --extra qdrant

install-tantivy: ## Install with Tantivy keyword index
	$(UV) sync --extra tantivy

install-whoosh: ## Install with Whoosh keyword index (Chinese tokenization)
	$(UV) sync --extra whoosh

install-qdrant: ## Install with Qdrant vector index
	$(UV) sync --extra qdrant

#----------------------------------------------------------------------
# Code Quality
#----------------------------------------------------------------------

lint: ## Run ruff linter
	$(UV) run $(RUFF) check src/grid_code tests

lint-fix: ## Run ruff linter with auto-fix
	$(UV) run $(RUFF) check --fix src/grid_code tests

format: ## Format code with ruff
	$(UV) run $(RUFF) format src/grid_code tests

format-check: ## Check code formatting without changes
	$(UV) run $(RUFF) format --check src/grid_code tests

check: lint format-check ## Run all code quality checks

#----------------------------------------------------------------------
# Testing
#----------------------------------------------------------------------

test: ## Run all tests
	$(UV) run $(PYTEST) tests/ -v

test-cov: ## Run tests with coverage report
	$(UV) run $(PYTEST) tests/ -v --cov=src/grid_code --cov-report=term-missing

test-fast: ## Run tests without slow markers
	$(UV) run $(PYTEST) tests/ -v -m "not slow"

test-mcp: ## Run MCP connection tests
	$(UV) run $(PYTEST) tests/dev/test_mcp_connection.py -xvs

test-heading: ## Run heading detection tests
	$(UV) run $(PYTHON) tests/test_heading_detection.py

#----------------------------------------------------------------------
# MCP Server
#----------------------------------------------------------------------

serve: ## Start MCP server (SSE mode, port 8080)
	$(UV) run gridcode serve --transport sse --port 8080

serve-stdio: ## Start MCP server (stdio mode, for Claude Desktop)
	$(UV) run gridcode serve --transport stdio

PORT ?= 8080
serve-port: ## Start MCP server on custom port (usage: make serve-port PORT=9000)
	$(UV) run gridcode serve --transport sse --port $(PORT)

#----------------------------------------------------------------------
# CLI Commands
#----------------------------------------------------------------------

REG_ID ?= angui_2024
AGENT ?= claude

chat: ## Start interactive chat (usage: make chat REG_ID=angui AGENT=claude MODE=mcp-sse)
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent $(AGENT) $(MCP_FLAGS)

chat-claude: ## Start chat with Claude Agent SDK
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent claude $(MCP_FLAGS)

chat-pydantic: ## Start chat with Pydantic AI Agent
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent pydantic $(MCP_FLAGS)

chat-langgraph: ## Start chat with LangGraph Agent
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent langgraph $(MCP_FLAGS)

# Single query execution (non-interactive)
# ASK_QUERY ?= 锦西电厂安控装置的具体配置
# ASK_QUERY ?= 锦西电厂安控装置的主要功能
ASK_QUERY ?= 华北电网500千伏天乐双线停运时，安控系统应采取哪些措施？
ask: ## Single query to Agent (usage: make ask ASK_QUERY="母线失压如何处理?" AGENT=claude)
	$(UV) run gridcode ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent $(AGENT) $(MCP_FLAGS)

ask-json: ## Single query with JSON output
	$(UV) run gridcode ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent $(AGENT) --json $(MCP_FLAGS)

ask-claude: ## Single query with Claude Agent
	$(UV) run gridcode ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent claude $(MCP_FLAGS)

ask-pydantic: ## Single query with Pydantic AI Agent
	$(UV) run gridcode ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent pydantic $(MCP_FLAGS)

ask-langgraph: ## Single query with LangGraph Agent
	$(UV) run gridcode ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent langgraph $(MCP_FLAGS)

list: ## List all ingested regulations
	$(UV) run gridcode $(MCP_FLAGS) list

QUERY ?= 母线失压
search: ## Search regulations (usage: make search QUERY="母线失压" REG_ID=angui)
	$(UV) run gridcode $(MCP_FLAGS) search "$(QUERY)" --reg-id $(REG_ID)

FILE ?= ./data/raw/angui_2024.pdf
ingest: ## Ingest a document (usage: make ingest FILE=/path/to/doc.docx REG_ID=angui)
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE is required. Usage: make ingest FILE=/path/to/doc.docx REG_ID=angui"; \
		exit 1; \
	fi
	$(UV) run gridcode ingest --file $(FILE) --reg-id $(REG_ID)

version: ## Show GridCode version
	$(UV) run gridcode version

PAGE_NUM ?= 7
OUTPUT ?=
inspect: ## Inspect page data across indexes (usage: make inspect REG_ID=angui PAGE_NUM=25)
	@if [ -z "$(OUTPUT)" ]; then \
		$(UV) run gridcode inspect $(REG_ID) $(PAGE_NUM); \
	else \
		$(UV) run gridcode inspect $(REG_ID) $(PAGE_NUM) --output $(OUTPUT); \
	fi

inspect-vectors: ## Inspect page data with vector display
	$(UV) run gridcode inspect $(REG_ID) $(PAGE_NUM) --show-vectors

SECTION ?=
NO_CHILDREN ?= false
read-chapter: ## Read chapter content by section number (usage: make read-chapter REG_ID=angui SECTION="2.1.4.1.6")
	@if [ -z "$(SECTION)" ]; then \
		echo "$(YELLOW)Error: SECTION is required.$(NC)"; \
		echo "Usage: make read-chapter REG_ID=angui SECTION=\"2.1.4.1.6\""; \
		exit 1; \
	fi
	@if [ "$(NO_CHILDREN)" = "true" ]; then \
		$(UV) run gridcode $(MCP_FLAGS) read-chapter --reg-id $(REG_ID) --section "$(SECTION)" --no-children; \
	else \
		$(UV) run gridcode $(MCP_FLAGS) read-chapter --reg-id $(REG_ID) --section "$(SECTION)"; \
	fi

#----------------------------------------------------------------------
# MCP Tools CLI (基础工具)
#----------------------------------------------------------------------

MAX_LEVEL ?= 3
toc: ## Get regulation TOC (usage: make toc REG_ID=angui)
	$(UV) run gridcode $(MCP_FLAGS) toc $(REG_ID) --level ${MAX_LEVEL}

START_PAGE ?= 4
END_PAGE ?= 6
read-pages: ## Read page range (usage: make read-pages REG_ID=angui START_PAGE=85 END_PAGE=87)
	$(UV) run gridcode $(MCP_FLAGS) read-pages --reg-id $(REG_ID) --start $(START_PAGE) --end $(END_PAGE)

chapter-structure: ## Get chapter structure (usage: make chapter-structure REG_ID=angui)
	$(UV) run gridcode $(MCP_FLAGS) chapter-structure $(REG_ID)

page-info: ## Get page chapter info (usage: make page-info REG_ID=angui PAGE_NUM=85)
	$(UV) run gridcode $(MCP_FLAGS) page-info --reg-id $(REG_ID) --page $(PAGE_NUM)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 1: 核心多跳工具)
#----------------------------------------------------------------------

ANNOTATION_ID ?= 注1
lookup-annotation: ## Lookup annotation (usage: make lookup-annotation REG_ID=angui ANNOTATION_ID="注1" PAGE_NUM=85)
	@if [ -n "$(PAGE_NUM)" ] && [ "$(PAGE_NUM)" != "7" ]; then \
		$(UV) run gridcode $(MCP_FLAGS) lookup-annotation --reg-id $(REG_ID) "$(ANNOTATION_ID)" --page $(PAGE_NUM); \
	else \
		$(UV) run gridcode $(MCP_FLAGS) lookup-annotation --reg-id $(REG_ID) "$(ANNOTATION_ID)"; \
	fi

TABLE_QUERY ?= 灵宝直流安控系统
TABLE_SEARCH_MODE ?= hybrid
search-tables: ## Search tables (usage: make search-tables REG_ID=angui TABLE_QUERY="母线失压" TABLE_SEARCH_MODE=hybrid)
	$(UV) run gridcode $(MCP_FLAGS) search-tables "$(TABLE_QUERY)" --reg-id $(REG_ID) --mode $(TABLE_SEARCH_MODE)

REFERENCE ?= 见第六章
resolve-reference: ## Resolve cross-reference (usage: make resolve-reference REG_ID=angui REFERENCE="见第六章")
	$(UV) run gridcode $(MCP_FLAGS) resolve-reference "$(REFERENCE)" --reg-id $(REG_ID)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 2: 上下文工具)
#----------------------------------------------------------------------

PATTERN ?=
ANNOTATION_TYPE ?=
search-annotations: ## Search all annotations (usage: make search-annotations REG_ID=angui PATTERN="电压" ANNOTATION_TYPE=note)
	@if [ -n "$(PATTERN)" ] && [ -n "$(ANNOTATION_TYPE)" ]; then \
		$(UV) run gridcode $(MCP_FLAGS) search-annotations $(REG_ID) --pattern "$(PATTERN)" --type $(ANNOTATION_TYPE); \
	elif [ -n "$(PATTERN)" ]; then \
		$(UV) run gridcode $(MCP_FLAGS) search-annotations $(REG_ID) --pattern "$(PATTERN)"; \
	elif [ -n "$(ANNOTATION_TYPE)" ]; then \
		$(UV) run gridcode $(MCP_FLAGS) search-annotations $(REG_ID) --type $(ANNOTATION_TYPE); \
	else \
		$(UV) run gridcode $(MCP_FLAGS) search-annotations $(REG_ID); \
	fi

TABLE_ID ?=
get-table: ## Get full table by ID (usage: make get-table REG_ID=angui TABLE_ID="table_xxx")
	@if [ -z "$(TABLE_ID)" ]; then \
		echo "$(YELLOW)Error: TABLE_ID is required.$(NC)"; \
		echo "Usage: make get-table REG_ID=angui TABLE_ID=\"table_xxx\""; \
		exit 1; \
	fi
	$(UV) run gridcode $(MCP_FLAGS) get-table "$(TABLE_ID)" --reg-id $(REG_ID)

#----------------------------------------------------------------------
# 表格注册表工具
#----------------------------------------------------------------------

build-table-registry: ## Build table registry for a regulation (usage: make build-table-registry REG_ID=angui_2024)
	@echo "$(BLUE)Building table registry for $(REG_ID)...$(NC)"
	@$(UV) run $(PYTHON) -c "from grid_code.storage import PageStore; from grid_code.parser import TableRegistryBuilder; ps = PageStore(); info = ps.load_info('$(REG_ID)'); pages = [ps.load_page('$(REG_ID)', i) for i in range(1, info.total_pages + 1)]; builder = TableRegistryBuilder('$(REG_ID)'); registry = builder.build(pages); ps.save_table_registry(registry); print(f'Done: {registry.total_tables} tables, {registry.cross_page_tables} cross-page')"

REBUILD_INDEX ?= false
build-table-index: ## Build table search index (FTS5 + vector) (usage: make build-table-index REG_ID=angui_2024 REBUILD_INDEX=true)
	@if [ "$(REBUILD_INDEX)" = "true" ]; then \
		$(UV) run gridcode build-table-index $(REG_ID) --rebuild; \
	else \
		$(UV) run gridcode build-table-index $(REG_ID); \
	fi

table-registry-stats: ## Show table registry statistics (usage: make table-registry-stats REG_ID=angui_2024)
	@$(UV) run $(PYTHON) -c "from grid_code.storage import PageStore; ps = PageStore(); reg = ps.load_table_registry('$(REG_ID)'); print(f'Total tables: {reg.total_tables}') if reg else print('No table registry found'); print(f'Cross-page tables: {reg.cross_page_tables}') if reg else None; print(f'Segment mappings: {len(reg.segment_to_table)}') if reg else None"

list-cross-page-tables: ## List all cross-page tables (usage: make list-cross-page-tables REG_ID=angui_2024)
	@$(UV) run $(PYTHON) -c "from grid_code.storage import PageStore; ps = PageStore(); reg = ps.load_table_registry('$(REG_ID)'); [print(f\"{tid}: P{e.page_start}-{e.page_end} ({len(e.segments)} segs)\") for tid, e in reg.tables.items() if e.is_cross_page] if reg else print('No table registry found')"

BLOCK_ID ?=
CONTEXT ?= 2
get-block-context: ## Get block with context (usage: make get-block-context REG_ID=angui BLOCK_ID="block_xxx" CONTEXT=2)
	@if [ -z "$(BLOCK_ID)" ]; then \
		echo "$(YELLOW)Error: BLOCK_ID is required.$(NC)"; \
		echo "Usage: make get-block-context REG_ID=angui BLOCK_ID=\"block_xxx\""; \
		exit 1; \
	fi
	$(UV) run gridcode $(MCP_FLAGS) get-block-context "$(BLOCK_ID)" --reg-id $(REG_ID) --context $(CONTEXT)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 3: 发现工具)
#----------------------------------------------------------------------

SIMILAR_QUERY ?= 三峡安控系统
LIMIT ?= 5
find-similar: ## Find similar content (usage: make find-similar REG_ID=angui SIMILAR_QUERY="母线失压处理")
	$(UV) run gridcode $(MCP_FLAGS) find-similar --reg-id $(REG_ID) --query "$(SIMILAR_QUERY)" --limit $(LIMIT)

SECTION_A ?=
SECTION_B ?=
compare-sections: ## Compare two sections (usage: make compare-sections REG_ID=angui SECTION_A="2.1.4" SECTION_B="2.1.5")
	@if [ -z "$(SECTION_A)" ] || [ -z "$(SECTION_B)" ]; then \
		echo "$(YELLOW)Error: SECTION_A and SECTION_B are required.$(NC)"; \
		echo "Usage: make compare-sections REG_ID=angui SECTION_A=\"2.1.4\" SECTION_B=\"2.1.5\""; \
		exit 1; \
	fi
	$(UV) run gridcode $(MCP_FLAGS) compare-sections "$(SECTION_A)" "$(SECTION_B)" --reg-id $(REG_ID)

BACKUP ?= true
reindex: ## Reindex document with new parser (usage: make reindex FILE=/path/to/doc.pdf REG_ID=angui BACKUP=true)
	@if [ -z "$(FILE)" ]; then \
		echo "$(YELLOW)Error: FILE is required.$(NC)"; \
		echo "Usage: make reindex FILE=/path/to/doc.pdf REG_ID=angui"; \
		exit 1; \
	fi
	@if [ "$(BACKUP)" = "true" ]; then \
		$(UV) run $(PYTHON) scripts/reindex_document.py $(FILE) --reg-id $(REG_ID) --backup; \
	else \
		$(UV) run $(PYTHON) scripts/reindex_document.py $(FILE) --reg-id $(REG_ID) --no-backup; \
	fi

verify-chapters: ## Verify chapter path extraction (usage: make verify-chapters REG_ID=angui PAGE_NUM=13)
	@echo "$(BLUE)Verifying chapter paths for $(REG_ID) page $(PAGE_NUM)...$(NC)"
	@$(UV) run $(PYTHON) scripts/verify_chapters.py $(REG_ID) $(PAGE_NUM)

stats-headings: ## Show heading detection statistics (usage: make stats-headings REG_ID=angui)
	@echo "$(BLUE)Analyzing heading detection for $(REG_ID)...$(NC)"
	@$(UV) run $(PYTHON) scripts/stats_headings.py $(REG_ID)

#----------------------------------------------------------------------
# Build & Distribution
#----------------------------------------------------------------------

build: ## Build package
	$(UV) build

build-wheel: ## Build wheel only
	$(UV) build --wheel

#----------------------------------------------------------------------
# Cleanup
#----------------------------------------------------------------------

clean: ## Clean build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

clean-data: ## Clean data directory (WARNING: removes all ingested documents)
	@echo "$(YELLOW)WARNING: This will remove all ingested documents!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && rm -rf data/storage || echo "Cancelled"

clean-backups: ## Clean backup data directory
	@if [ -d "data/backups" ]; then \
		echo "$(YELLOW)Removing backup data...$(NC)"; \
		rm -rf data/backups/; \
		echo "$(GREEN)Backups cleaned$(NC)"; \
	else \
		echo "$(YELLOW)No backups found$(NC)"; \
	fi

clean-all: clean clean-data ## Clean everything including data

#----------------------------------------------------------------------
# Development Helpers
#----------------------------------------------------------------------

dev: install-dev ## Setup development environment
	@echo "$(GREEN)Development environment ready!$(NC)"
	@echo "Run 'make help' to see available commands"

run: ## Run any gridcode command (usage: make run CMD="list")
	$(UV) run gridcode $(CMD)

#----------------------------------------------------------------------
# MCP Mode Convenience Targets
#----------------------------------------------------------------------

# Shortcut targets for MCP stdio mode
list-mcp: ## List regulations via MCP stdio
	$(MAKE) list MODE=mcp-stdio

search-mcp: ## Search via MCP stdio (usage: make search-mcp QUERY="母线失压")
	$(MAKE) search MODE=mcp-stdio QUERY="$(QUERY)" REG_ID="$(REG_ID)"

toc-mcp: ## Get TOC via MCP stdio
	$(MAKE) toc MODE=mcp-stdio REG_ID="$(REG_ID)"

read-pages-mcp: ## Read pages via MCP stdio
	$(MAKE) read-pages MODE=mcp-stdio REG_ID="$(REG_ID)" START_PAGE="$(START_PAGE)" END_PAGE="$(END_PAGE)"

# Shortcut targets for MCP SSE mode (requires 'make serve' running)
list-mcp-sse: ## List regulations via MCP SSE
	$(MAKE) list MODE=mcp-sse

search-mcp-sse: ## Search via MCP SSE (usage: make search-mcp-sse QUERY="母线失压")
	$(MAKE) search MODE=mcp-sse QUERY="$(QUERY)" REG_ID="$(REG_ID)"

toc-mcp-sse: ## Get TOC via MCP SSE
	$(MAKE) toc MODE=mcp-sse REG_ID="$(REG_ID)"

read-pages-mcp-sse: ## Read pages via MCP SSE
	$(MAKE) read-pages MODE=mcp-sse REG_ID="$(REG_ID)" START_PAGE="$(START_PAGE)" END_PAGE="$(END_PAGE)"

# Shortcut targets for chat with MCP SSE mode (requires 'make serve' running)
chat-mcp-sse: ## Chat via MCP SSE (usage: make chat-mcp-sse AGENT=claude)
	$(MAKE) chat MODE=mcp-sse AGENT="$(AGENT)" REG_ID="$(REG_ID)"

chat-claude-sse: ## Chat with Claude Agent via MCP SSE
	$(MAKE) chat-claude MODE=mcp-sse REG_ID="$(REG_ID)"

chat-pydantic-sse: ## Chat with Pydantic AI Agent via MCP SSE
	$(MAKE) chat-pydantic MODE=mcp-sse REG_ID="$(REG_ID)"

chat-langgraph-sse: ## Chat with LangGraph Agent via MCP SSE
	$(MAKE) chat-langgraph MODE=mcp-sse REG_ID="$(REG_ID)"

#----------------------------------------------------------------------
# MCP Service Verification
#----------------------------------------------------------------------

mcp-tools: ## List MCP tools (static metadata)
	$(UV) run gridcode mcp-tools

mcp-tools-v: ## List MCP tools with detailed info
	$(UV) run gridcode mcp-tools -v

mcp-tools-live: ## List MCP tools from live server (stdio)
	$(UV) run gridcode mcp-tools --live

mcp-verify: ## Verify MCP service completeness (stdio mode)
	$(UV) run gridcode mcp-tools --live --verify

mcp-verify-v: ## Verify MCP service with detailed output
	$(UV) run gridcode mcp-tools --live --verify -v

SSE_URL ?= http://localhost:8080/sse
mcp-verify-sse: ## Verify MCP service via SSE (requires 'make serve' running)
	$(UV) run gridcode mcp-tools --live --sse $(SSE_URL) --verify -v
