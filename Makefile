# GridCode Makefile
# Power Grid Regulations Intelligent Retrieval Agent

.PHONY: help install install-dev install-all test lint format check serve serve-stdio chat build clean

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python
UV := uv
PYTEST := pytest
RUFF := ruff

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
	@awk 'BEGIN {FS = ":.*##"; printf ""} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Examples:$(NC)"
	@echo "  make install-dev          # Install with dev dependencies"
	@echo "  make test                 # Run all tests"
	@echo "  make serve                # Start MCP server (SSE mode)"
	@echo "  make chat REG_ID=angui    # Start chat with specific regulation"

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

chat: ## Start interactive chat (usage: make chat REG_ID=angui AGENT=claude)
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent $(AGENT)

chat-claude: ## Start chat with Claude Agent SDK
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent claude

chat-pydantic: ## Start chat with Pydantic AI Agent
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent pydantic

chat-langgraph: ## Start chat with LangGraph Agent
	$(UV) run gridcode chat --reg-id $(REG_ID) --agent langgraph

list: ## List all ingested regulations
	$(UV) run gridcode list

QUERY ?= 母线失压
search: ## Search regulations (usage: make search QUERY="母线失压" REG_ID=angui)
	$(UV) run gridcode search "$(QUERY)" --reg-id $(REG_ID)

FILE ?=
ingest: ## Ingest a document (usage: make ingest FILE=/path/to/doc.docx REG_ID=angui)
	@if [ -z "$(FILE)" ]; then \
		echo "Error: FILE is required. Usage: make ingest FILE=/path/to/doc.docx REG_ID=angui"; \
		exit 1; \
	fi
	$(UV) run gridcode ingest --file $(FILE) --reg-id $(REG_ID)

version: ## Show GridCode version
	$(UV) run gridcode version

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
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] && rm -rf data/ || echo "Cancelled"

clean-all: clean clean-data ## Clean everything including data

#----------------------------------------------------------------------
# Development Helpers
#----------------------------------------------------------------------

dev: install-dev ## Setup development environment
	@echo "$(GREEN)Development environment ready!$(NC)"
	@echo "Run 'make help' to see available commands"

run: ## Run any gridcode command (usage: make run CMD="list")
	$(UV) run gridcode $(CMD)
