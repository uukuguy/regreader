# ============================================================
# RegReader Makefile - Conda 模块
# ============================================================
# ⚠️  DEPRECATED: 此文件已弃用，将在未来版本中移除
# ============================================================
#
# 弃用原因：
#   所有功能已被 makefiles/pkgmgr.mk 统一接口替代
#   pkgmgr.mk 自动检测 uv/conda，无需手动指定
#
# 迁移指南：
#   make install-conda      → make install
#   make install-conda-dev  → make install-dev
#   make install-conda-all  → make install-all
#   make chat-conda         → make chat
#   make ask-conda          → make ask
#
# 强制使用 conda 后端（如需要）：
#   PKGMGR_BACKEND=conda make install-dev
#   PKGMGR_BACKEND=conda make chat
#
# 移除计划：
#   - v1.1.0: 添加弃用警告（当前版本）
#   - v1.2.0: 默认不加载（需手动 include）
#   - v1.3.0: 完全移除此文件
# ============================================================

$(warning ⚠️  makefiles/conda.mk is DEPRECATED and will be removed in v1.3.0)
$(warning ⚠️  Use unified commands: make install, make chat, etc.)
$(warning ⚠️  See makefiles/pkgmgr.mk for the new interface)

# 注意：不再包含 variables.mk，因为主 Makefile 已经包含了

#----------------------------------------------------------------------
# Conda 安装目标
#----------------------------------------------------------------------

install-conda: ## Install in conda environment (uses system torch)
	@echo "$(BLUE)Installing RegReader in conda environment...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Note: docling excluded (ingest on Mac, serve on Linux)$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_BASE_DEPS)
	@echo "$(YELLOW)Step 2: Installing regreader in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-dev: ## Install with dev dependencies in conda environment
	@echo "$(BLUE)Installing RegReader with dev dependencies...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_DEV_DEPS)
	@echo "$(YELLOW)Step 2: Installing regreader in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-all: ## Install with all optional backends in conda environment
	@echo "$(BLUE)Installing RegReader with all optional index backends...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_ALL_DEPS)
	@echo "$(YELLOW)Step 2: Installing regreader in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-ocr: ## Install with OCR support in conda environment (requires docling)
	@echo "$(BLUE)Installing RegReader with OCR support...$(NC)"
	@echo "$(YELLOW)Prerequisite: conda environment with torch, tiktoken already installed$(NC)"
	@echo "$(YELLOW)Step 1: Installing dependencies (including docling for OCR)...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_OCR_DEPS)
	@echo "$(YELLOW)Step 2: Installing regreader in editable mode...$(NC)"
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

install-conda-full: ## Install with docling for ingest support in conda environment
	@echo "$(BLUE)Installing RegReader with full ingest support...$(NC)"
	pip install $(CONDA_INSTALL_FLAGS) $(CONDA_FULL_DEPS)
	pip install -e . --no-deps
	@echo "$(GREEN)Installation complete!$(NC)"

#----------------------------------------------------------------------
# Conda MCP 服务
#----------------------------------------------------------------------

serve-conda: ## Start MCP server in conda environment (SSE mode)
	$(REGREADER) serve --transport sse --port 8080

serve-conda-stdio: ## Start MCP server in conda environment (stdio mode)
	$(REGREADER) serve --transport stdio

serve-conda-port: ## Start MCP server on custom port in conda (usage: make serve-conda-port PORT=9000)
	$(REGREADER) serve --transport sse --port $(PORT)

#----------------------------------------------------------------------
# Conda CLI 命令
#----------------------------------------------------------------------

chat-conda: ## Start chat in conda environment (usage: make chat-conda AGENT=claude)
	$(REGREADER) chat $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

ask-conda: ## Single query in conda environment (usage: make ask-conda ASK_QUERY="...")
	$(REGREADER) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

list-conda: ## List regulations in conda environment
	$(REGREADER) list

search-conda: ## Search in conda environment (usage: make search-conda QUERY="...")
	$(REGREADER) search "$(QUERY)" --reg-id $(REG_ID)

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
