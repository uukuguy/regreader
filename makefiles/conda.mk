# ============================================================
# GridCode Makefile - Conda 模块
# ============================================================
# Conda 环境专用命令（仅 Linux 服务器使用）
# 依赖: mk/variables.mk
# ============================================================

include makefiles/variables.mk

#----------------------------------------------------------------------
# Conda 安装目标
#----------------------------------------------------------------------

install-conda: ## Install in conda environment (uses system torch)
	@echo "$(BLUE)Installing GridCode in conda environment...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Note: docling excluded (ingest on Mac, serve on Linux)$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_BASE_DEPS)
	@echo "$(YELLOW)Step 2: Installing grid-code in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-dev: ## Install with dev dependencies in conda environment
	@echo "$(BLUE)Installing GridCode with dev dependencies...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_DEV_DEPS)
	@echo "$(YELLOW)Step 2: Installing grid-code in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-all: ## Install with all optional backends in conda environment
	@echo "$(BLUE)Installing GridCode with all optional index backends...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_ALL_DEPS)
	@echo "$(YELLOW)Step 2: Installing grid-code in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-ocr: ## Install with OCR support in conda environment (requires docling)
	@echo "$(BLUE)Installing GridCode with OCR support...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies (including docling for OCR)...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_OCR_DEPS)
	@echo "$(YELLOW)Step 2: Installing grid-code in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-full: ## Install with docling for ingest support in conda environment
	@echo "$(BLUE)Installing GridCode with full ingest support...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_FULL_DEPS)
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

#----------------------------------------------------------------------
# Conda MCP 服务
#----------------------------------------------------------------------

serve-conda: ## Start MCP server in conda environment (SSE mode)
	$(GRIDCODE) serve --transport sse --port 8080

serve-conda-stdio: ## Start MCP server in conda environment (stdio mode)
	$(GRIDCODE) serve --transport stdio

serve-conda-port: ## Start MCP server on custom port in conda (usage: make serve-conda-port PORT=9000)
	$(GRIDCODE) serve --transport sse --port $(PORT)

#----------------------------------------------------------------------
# Conda CLI 命令
#----------------------------------------------------------------------

chat-conda: ## Start chat in conda environment (usage: make chat-conda AGENT=claude)
	$(GRIDCODE) chat --reg-id $(REG_ID) --agent $(AGENT)

ask-conda: ## Single query in conda environment (usage: make ask-conda ASK_QUERY="...")
	$(GRIDCODE) $(MCP_FLAGS) ask "$(ASK_QUERY)" --reg-id $(REG_ID) --agent $(AGENT)

list-conda: ## List regulations in conda environment
	$(GRIDCODE) list

search-conda: ## Search in conda environment (usage: make search-conda QUERY="...")
	$(GRIDCODE) search "$(QUERY)" --reg-id $(REG_ID)

#----------------------------------------------------------------------
# Conda Agent 快捷方式（向后兼容）
#----------------------------------------------------------------------

chat-conda-claude: AGENT=claude
chat-conda-claude: chat-conda  ## Chat with Claude Agent in conda environment

chat-conda-pydantic: AGENT=pydantic
chat-conda-pydantic: chat-conda  ## Chat with Pydantic AI Agent in conda environment

chat-conda-langgraph: AGENT=langgraph
chat-conda-langgraph: chat-conda  ## Chat with LangGraph Agent in conda environment

ask-conda-claude: AGENT=claude
ask-conda-claude: ask-conda  ## Single query with Claude Agent in conda environment

ask-conda-pydantic: AGENT=pydantic
ask-conda-pydantic: ask-conda  ## Single query with Pydantic AI Agent in conda environment

ask-conda-langgraph: AGENT=langgraph
ask-conda-langgraph: ask-conda  ## Single query with LangGraph Agent in conda environment
