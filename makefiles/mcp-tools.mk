# ============================================================
# RegReader Makefile - MCP Tools 模块
# ============================================================
# MCP 工具 CLI 命令
# 依赖: mk/variables.mk
# ============================================================

include makefiles/variables.mk

#----------------------------------------------------------------------
# 文档读取命令
#----------------------------------------------------------------------

read-chapter: ## Read chapter content by section number (usage: make read-chapter REG_ID=angui SECTION="2.1.4.1.6")
	@if [ -z "$(SECTION)" ]; then \
		echo "$(YELLOW)Error: SECTION is required.$(NC)"; \
		echo "Usage: make read-chapter REG_ID=angui SECTION=\"2.1.4.1.6\""; \
		exit 1; \
	fi
	@if [ "$(NO_CHILDREN)" = "true" ]; then \
		$(REGREADER_CMD) $(MCP_FLAGS) read-chapter --reg-id $(REG_ID) --section "$(SECTION)" --no-children; \
	else \
		$(REGREADER_CMD) $(MCP_FLAGS) read-chapter --reg-id $(REG_ID) --section "$(SECTION)"; \
	fi

#----------------------------------------------------------------------
# MCP Tools CLI (基础工具)
#----------------------------------------------------------------------

toc: ## Get regulation TOC (usage: make toc REG_ID=angui)
	$(REGREADER_CMD) $(MCP_FLAGS) toc $(REG_ID) --level ${MAX_LEVEL}

read-pages: ## Read page range (usage: make read-pages REG_ID=angui START_PAGE=85 END_PAGE=87)
	$(REGREADER_CMD) $(MCP_FLAGS) read-pages --reg-id $(REG_ID) --start $(START_PAGE) --end $(END_PAGE)

chapter-structure: ## Get chapter structure (usage: make chapter-structure REG_ID=angui)
	$(REGREADER_CMD) $(MCP_FLAGS) chapter-structure $(REG_ID)

page-info: ## Get page chapter info (usage: make page-info REG_ID=angui PAGE_NUM=85)
	$(REGREADER_CMD) $(MCP_FLAGS) page-info --reg-id $(REG_ID) --page $(PAGE_NUM)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 1: 核心多跳工具)
#----------------------------------------------------------------------

lookup-annotation: ## Lookup annotation (usage: make lookup-annotation REG_ID=angui ANNOTATION_ID="注1" PAGE_NUM=85)
	@if [ -n "$(PAGE_NUM)" ] && [ "$(PAGE_NUM)" != "7" ]; then \
		$(REGREADER_CMD) $(MCP_FLAGS) lookup-annotation --reg-id $(REG_ID) "$(ANNOTATION_ID)" --page $(PAGE_NUM); \
	else \
		$(REGREADER_CMD) $(MCP_FLAGS) lookup-annotation --reg-id $(REG_ID) "$(ANNOTATION_ID)"; \
	fi

search-tables: ## Search tables (usage: make search-tables REG_ID=angui TABLE_QUERY="母线失压" TABLE_SEARCH_MODE=hybrid)
	$(REGREADER_CMD) $(MCP_FLAGS) search-tables "$(TABLE_QUERY)" --reg-id $(REG_ID) --mode $(TABLE_SEARCH_MODE)

resolve-reference: ## Resolve cross-reference (usage: make resolve-reference REG_ID=angui REFERENCE="见第六章")
	$(REGREADER_CMD) $(MCP_FLAGS) resolve-reference "$(REFERENCE)" --reg-id $(REG_ID)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 2: 上下文工具)
#----------------------------------------------------------------------

search-annotations: ## Search all annotations (usage: make search-annotations REG_ID=angui PATTERN="电压" ANNOTATION_TYPE=note)
	@if [ -n "$(PATTERN)" ] && [ -n "$(ANNOTATION_TYPE)" ]; then \
		$(REGREADER_CMD) $(MCP_FLAGS) search-annotations $(REG_ID) --pattern "$(PATTERN)" --type $(ANNOTATION_TYPE); \
	elif [ -n "$(PATTERN)" ]; then \
		$(REGREADER_CMD) $(MCP_FLAGS) search-annotations $(REG_ID) --pattern "$(PATTERN)"; \
	elif [ -n "$(ANNOTATION_TYPE)" ]; then \
		$(REGREADER_CMD) $(MCP_FLAGS) search-annotations $(REG_ID) --type $(ANNOTATION_TYPE); \
	else \
		$(REGREADER_CMD) $(MCP_FLAGS) search-annotations $(REG_ID); \
	fi

get-table: ## Get full table by ID (usage: make get-table REG_ID=angui TABLE_ID="table_xxx")
	@if [ -z "$(TABLE_ID)" ]; then \
		echo "$(YELLOW)Error: TABLE_ID is required.$(NC)"; \
		echo "Usage: make get-table REG_ID=angui TABLE_ID=\"table_xxx\""; \
		exit 1; \
	fi
	$(REGREADER_CMD) $(MCP_FLAGS) get-table "$(TABLE_ID)" --reg-id $(REG_ID)

get-block-context: ## Get block with context (usage: make get-block-context REG_ID=angui BLOCK_ID="block_xxx" CONTEXT=2)
	@if [ -z "$(BLOCK_ID)" ]; then \
		echo "$(YELLOW)Error: BLOCK_ID is required.$(NC)"; \
		echo "Usage: make get-block-context REG_ID=angui BLOCK_ID=\"block_xxx\""; \
		exit 1; \
	fi
	$(REGREADER_CMD) $(MCP_FLAGS) get-block-context "$(BLOCK_ID)" --reg-id $(REG_ID) --context $(CONTEXT)

#----------------------------------------------------------------------
# MCP Tools CLI (Phase 3: 发现工具)
#----------------------------------------------------------------------

find-similar: ## Find similar content (usage: make find-similar REG_ID=angui SIMILAR_QUERY="母线失压处理")
	$(REGREADER_CMD) $(MCP_FLAGS) find-similar --reg-id $(REG_ID) --query "$(SIMILAR_QUERY)" --limit $(LIMIT)

compare-sections: ## Compare two sections (usage: make compare-sections REG_ID=angui SECTION_A="2.1.4" SECTION_B="2.1.5")
	@if [ -z "$(SECTION_A)" ] || [ -z "$(SECTION_B)" ]; then \
		echo "$(YELLOW)Error: SECTION_A and SECTION_B are required.$(NC)"; \
		echo "Usage: make compare-sections REG_ID=angui SECTION_A=\"2.1.4\" SECTION_B=\"2.1.5\""; \
		exit 1; \
	fi
	$(REGREADER_CMD) $(MCP_FLAGS) compare-sections "$(SECTION_A)" "$(SECTION_B)" --reg-id $(REG_ID)

#----------------------------------------------------------------------
# 表格注册表工具
#----------------------------------------------------------------------

build-table-registry: ## Build table registry for a regulation (usage: make build-table-registry REG_ID=angui_2024)
	@echo "$(BLUE)Building table registry for $(REG_ID)...$(NC)"
	@$(PY_CMD) scripts/makefile/table_registry_build.py $(REG_ID)

build-table-index: ## Build table search index (FTS5 + vector) (usage: make build-table-index REG_ID=angui_2024 REBUILD_INDEX=true)
	@if [ "$(REBUILD_INDEX)" = "true" ]; then \
		$(REGREADER_CMD) build-table-index $(REG_ID) --rebuild; \
	else \
		$(REGREADER_CMD) build-table-index $(REG_ID); \
	fi

table-registry-stats: ## Show table registry statistics (usage: make table-registry-stats REG_ID=angui_2024)
	@$(PY_CMD) scripts/makefile/table_registry_stats.py $(REG_ID)

list-cross-page-tables: ## List all cross-page tables (usage: make list-cross-page-tables REG_ID=angui_2024)
	@$(PY_CMD) scripts/makefile/list_cross_page_tables.py $(REG_ID)

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

#----------------------------------------------------------------------
# MCP Service Verification
#----------------------------------------------------------------------

mcp-tools: ## List MCP tools (static metadata)
	$(REGREADER_CMD) mcp-tools

mcp-tools-v: ## List MCP tools with detailed info
	$(REGREADER_CMD) mcp-tools -v

mcp-tools-live: ## List MCP tools from live server (stdio)
	$(REGREADER_CMD) mcp-tools --live

mcp-verify: ## Verify MCP service completeness (stdio mode)
	$(REGREADER_CMD) mcp-tools --live --verify

mcp-verify-v: ## Verify MCP service with detailed output
	$(REGREADER_CMD) mcp-tools --live --verify -v

mcp-verify-sse: ## Verify MCP service via SSE (requires 'make serve' running)
	$(REGREADER_CMD) mcp-tools --live --sse $(SSE_URL) --verify -v
