# RegReader Makefile
# Power Grid Regulations Intelligent Retrieval Agent

# 导入变量定义
include makefiles/variables.mk
include makefiles/conda.mk
include makefiles/agents.mk
include makefiles/mcp-tools.mk

.PHONY: help install install-dev install-all test test-mcp test-heading lint format check serve serve-stdio chat build clean reindex read-chapter \
	ask ask-json ask-claude ask-pydantic ask-langgraph \
	chat-orch chat-orch-claude chat-orch-pydantic chat-orch-langgraph \
	ask-orch ask-orch-claude ask-orch-pydantic ask-orch-langgraph \
	toc read-pages chapter-structure page-info lookup-annotation search-tables resolve-reference \
	search-annotations get-table get-block-context find-similar compare-sections \
	build-table-registry table-registry-stats list-cross-page-tables build-table-index \
	list-mcp search-mcp toc-mcp read-pages-mcp list-mcp-sse search-mcp-sse toc-mcp-sse read-pages-mcp-sse \
	chat-mcp-sse chat-claude-sse chat-pydantic-sse chat-langgraph-sse \
	mcp-tools mcp-tools-v mcp-tools-live mcp-verify mcp-verify-v mcp-verify-sse \
	enrich-metadata enrich-metadata-all search-all search-multi search-smart \
	test-bash-fs verify-bash-fs test-infrastructure test-regsearch

# Default target
.DEFAULT_GOAL := help

#----------------------------------------------------------------------
# Help
#----------------------------------------------------------------------

help: ## Show this help message
	@echo "$(BLUE)RegReader - Power Grid Regulations Intelligent Retrieval Agent$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make install-dev              # Install with dev dependencies (uv)"
	@echo "  make test                     # Run all tests"
	@echo "  make serve                    # Start MCP server (SSE mode)"
	@echo "  make chat                     # Start interactive chat (auto-detect regulation)"
	@echo "  make chat REG_ID=angui_2024   # Chat with specific regulation"
	@echo "  make ask ASK_QUERY=\"母线失压如何处理?\"  # Single query (auto-detect)"
	@echo "  make ask ASK_QUERY=\"...\" REG_ID=angui_2024  # Query in specific regulation"
	@echo ""
	@echo "$(GREEN)Agent Flags:$(NC)"
	@echo "  AGENT_FLAGS=\"-v\"              # Verbose mode: show DEBUG logs"
	@echo "  AGENT_FLAGS=\"-q\"              # Quiet mode: only show final result"
	@echo "  make ask-pydantic AGENT_FLAGS=\"-v\" ASK_QUERY=\"...\""
	@echo ""
	@echo "$(GREEN)Regulation ID (Optional):$(NC)"
	@echo "  REG_ID=                       # Auto-detect regulation (default, recommended)"
	@echo "  REG_ID=angui_2024             # Query in specific regulation"
	@echo "  REG_ID=wengui_2024            # Query in specific regulation"
	@echo ""
	@echo "$(GREEN)Orchestrator Mode (Subagent Architecture):$(NC)"
	@echo "  make chat-orch REG_ID=angui_2024                # Chat with Orchestrator"
	@echo "  make chat-orch-claude REG_ID=angui_2024         # Claude Orchestrator"
	@echo "  make chat-orch-pydantic REG_ID=angui_2024       # Pydantic Orchestrator"
	@echo "  make chat-orch-langgraph REG_ID=angui_2024      # LangGraph Orchestrator"
	@echo "  make ask-orch ASK_QUERY=\"表6-2注1的内容\" REG_ID=angui_2024  # Single query"
	@echo ""
	@echo "$(GREEN)Multi-Regulation Search:$(NC)"
	@echo "  make search-smart QUERY=\"母线失压\"              # Smart selection (auto-detect regulation)"
	@echo "  make search QUERY=\"母线失压\" REG_ID=angui_2024  # Single regulation"
	@echo "  make search-multi QUERY=\"稳定控制\" REG_IDS=\"angui_2024,wengui_2024\"  # Multiple"
	@echo "  make search-all QUERY=\"故障处理\"               # Search all regulations"
	@echo "  make enrich-metadata REG_ID=angui_2024         # Generate metadata for one"
	@echo "  make enrich-metadata-all                       # Generate metadata for all"
	@echo ""
	@echo "$(GREEN)Conda Environment (for Linux with existing torch):$(NC)"
	@echo "  make install-conda            # Install in active conda environment"
	@echo "  make serve-conda              # Start MCP server (no uv)"
	@echo "  make chat-conda-claude        # Chat with Claude Agent"
	@echo "  make ask-conda-pydantic       # Single query with Pydantic AI"
	@echo "  make list-conda               # List regulations"
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
	@echo ""
	@echo "$(GREEN)Bash+FS Subagents Architecture:$(NC)"
	@echo "  make test-bash-fs             # Run Bash+FS unit tests"
	@echo "  make test-infrastructure      # Test infrastructure layer (FileContext, EventBus, etc.)"
	@echo "  make test-regsearch           # Test RegSearchSubagent"
	@echo "  make verify-bash-fs           # Run architecture verification (no pytest needed)"

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
	$(UV_RUN) $(RUFF) check src/regreader tests

lint-fix: ## Run ruff linter with auto-fix
	$(UV_RUN) $(RUFF) check --fix src/regreader tests

format: ## Format code with ruff
	$(UV_RUN) $(RUFF) format src/regreader tests

format-check: ## Check code formatting without changes
	$(UV_RUN) $(RUFF) format --check src/regreader tests

check: lint format-check ## Run all code quality checks

#----------------------------------------------------------------------
# Testing
#----------------------------------------------------------------------

test: ## Run all tests
	$(UV_RUN) $(PYTEST) tests/ -v

test-cov: ## Run tests with coverage report
	$(UV_RUN) $(PYTEST) tests/ -v --cov=src/regreader --cov-report=term-missing

test-fast: ## Run tests without slow markers
	$(UV_RUN) $(PYTEST) tests/ -v -m "not slow"

test-mcp: ## Run MCP connection tests
	$(UV_RUN) $(PYTEST) tests/dev/test_mcp_connection.py -xvs

test-heading: ## Run heading detection tests
	$(PY_CMD) tests/test_heading_detection.py

#----------------------------------------------------------------------
# Bash+FS Subagents Architecture Testing
#----------------------------------------------------------------------

test-bash-fs: ## Run Bash+FS architecture unit tests
	$(UV_RUN) $(PYTEST) tests/bash-fs-paradiam/ -xvs

test-infrastructure: ## Run infrastructure layer tests (FileContext, EventBus, etc.)
	$(UV_RUN) $(PYTEST) tests/bash-fs-paradiam/test_file_context.py tests/bash-fs-paradiam/test_event_bus.py tests/bash-fs-paradiam/test_security_guard.py tests/bash-fs-paradiam/test_skill_loader.py -xvs

test-regsearch: ## Run RegSearchSubagent tests
	$(UV_RUN) $(PYTEST) tests/bash-fs-paradiam/test_regsearch_subagent.py -xvs

verify-bash-fs: ## Run complete Bash+FS architecture verification (no pytest required)
	@echo "$(BLUE)Verifying Bash+FS Subagents Architecture...$(NC)"
	@$(PY_CMD) scripts/verify_bash_fs.py

#----------------------------------------------------------------------
# MCP Server
#----------------------------------------------------------------------

serve: ## Start MCP server (SSE mode, port 8080)
	$(REGREADER_CMD) serve --transport sse --port 8080

serve-stdio: ## Start MCP server (stdio mode, for Claude Desktop)
	$(REGREADER_CMD) serve --transport stdio

PORT ?= 8080
serve-port: ## Start MCP server on custom port (usage: make serve-port PORT=9000)
	$(REGREADER_CMD) serve --transport sse --port $(PORT)

list: ## List all ingested regulations
	$(REGREADER_CMD) $(MCP_FLAGS) list

QUERY ?= 母线失压
search: ## Search regulations (usage: make search QUERY="母线失压" REG_ID=angui)
	$(REGREADER_CMD) $(MCP_FLAGS) search "$(QUERY)" $(REG_ID_FLAG)

#----------------------------------------------------------------------
# Multi-Regulation Search
#----------------------------------------------------------------------

search-smart: ## Smart search - auto-detect regulation (usage: make search-smart QUERY="母线失压")
	$(REGREADER_CMD) $(MCP_FLAGS) search "$(QUERY)"

REG_IDS ?= angui_2024,wengui_2024
search-multi: ## Search multiple regulations (usage: make search-multi QUERY="稳定控制" REG_IDS="angui_2024,wengui_2024")
	@IFS=',' read -ra REGS <<< "$(REG_IDS)"; \
	REG_ARGS=""; \
	for reg in "$${REGS[@]}"; do \
		REG_ARGS="$$REG_ARGS -r $$reg"; \
	done; \
	$(REGREADER_CMD) $(MCP_FLAGS) search "$(QUERY)" $$REG_ARGS

search-all: ## Search all regulations (usage: make search-all QUERY="故障处理")
	$(REGREADER_CMD) $(MCP_FLAGS) search "$(QUERY)" --all

#----------------------------------------------------------------------
# Metadata Enrichment
#----------------------------------------------------------------------

enrich-metadata: ## Generate metadata for a regulation (usage: make enrich-metadata REG_ID=angui_2024)
	$(REGREADER_CMD) enrich-metadata $(REG_ID)

enrich-metadata-all: ## Generate metadata for all regulations
	$(REGREADER_CMD) enrich-metadata --all

# REG_ID ?= angui_2024
# FILE ?= ./data/raw/angui_2024.pdf
REG_ID ?= wengui_2024
FILE ?= ./data/raw/wengui_2024.pdf
ingest: ## Ingest a document (usage: make ingest FILE=/path/to/doc.docx REG_ID=angui)
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE is required. Usage: make ingest FILE=/path/to/doc.docx REG_ID=angui"; \
		exit 1; \
	fi
	$(REGREADER_CMD) ingest --file $(FILE) --reg-id $(REG_ID)

version: ## Show RegReader version
	$(REGREADER_CMD) version

PAGE_NUM ?= 7
OUTPUT ?=
inspect: ## Inspect page data across indexes (usage: make inspect REG_ID=angui PAGE_NUM=25)
	@if [ -z "$(OUTPUT)" ]; then \
		$(REGREADER_CMD) inspect $(REG_ID) $(PAGE_NUM); \
	else \
		$(REGREADER_CMD) inspect $(REG_ID) $(PAGE_NUM) --output $(OUTPUT); \
	fi

inspect-vectors: ## Inspect page data with vector display
	$(REGREADER_CMD) inspect $(REG_ID) $(PAGE_NUM) --show-vectors


# Litellm Proxy
start-litellm-proxy:
	bash litellm/start-litellm-proxy.sh
