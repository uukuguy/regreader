# ============================================================
# RegReader Makefile - Agents 模块
# ============================================================
# Agent 命令统一接口
# 依赖: mk/variables.mk
# ============================================================

include makefiles/variables.mk

#----------------------------------------------------------------------
# 通用 Agent 命令
#----------------------------------------------------------------------

chat: ## Start interactive chat (usage: make chat REG_ID=angui AGENT=claude MODE=mcp-sse)
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

ask: ## Single query to Agent (usage: make ask ASK_QUERY="母线失压如何处理?" AGENT=claude)
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

ask-json: ## Single query with JSON output
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS) --json

ask-file: ## Query from file (usage: make ask-file QUERY_FILE=queries/query.txt AGENT=claude)
	@if [ -z "$(QUERY_FILE)" ]; then \
		echo "$(YELLOW)错误: 必须指定 QUERY_FILE 参数$(NC)"; \
		echo "用法: make ask-file QUERY_FILE=queries/query.txt AGENT=claude REG_ID=angui_2024"; \
		echo "示例文件内容:"; \
		echo "  请详细说明母线失压的处理流程，包括："; \
		echo "  1. 故障判断标准"; \
		echo "  2. 应急处理步骤"; \
		exit 1; \
	fi
	@if [ ! -f "$(QUERY_FILE)" ]; then \
		echo "$(YELLOW)错误: 文件不存在: $(QUERY_FILE)$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)从文件读取查询: $(QUERY_FILE)$(NC)"
	$(REGREADER_CMD) $(MCP_FLAGS) ask $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS) -- "$$(cat $(QUERY_FILE))"

ask-stdin: ## Query from stdin (usage: cat query.txt | make ask-stdin AGENT=claude)
	@echo "$(BLUE)从 stdin 读取查询...$(NC)"
	@read -r -d '' QUERY || true; \
	if [ -z "$$QUERY" ]; then \
		echo "$(YELLOW)错误: stdin 输入为空$(NC)"; \
		echo "用法: cat query.txt | make ask-stdin AGENT=claude REG_ID=angui_2024"; \
		echo "或者: echo '查询内容' | make ask-stdin AGENT=claude"; \
		exit 1; \
	fi; \
	$(REGREADER_CMD) $(MCP_FLAGS) ask $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS) -- "$$QUERY"

chat-orch: ## Start chat with Orchestrator (usage: make chat-orch REG_ID=angui AGENT=claude)
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent $(AGENT) --orchestrator $(AGENT_FLAGS)

ask-orch: ## Single query with Orchestrator (usage: make ask-orch ASK_QUERY="表6-2注1的内容")
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) --orchestrator $(AGENT_FLAGS)

#----------------------------------------------------------------------
# Agent 快捷别名（向后兼容）
#----------------------------------------------------------------------

# Chat aliases
chat-claude: ## Start chat with Claude Agent SDK
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent claude $(AGENT_FLAGS)

chat-pydantic: ## Start chat with Pydantic AI Agent
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent pydantic $(AGENT_FLAGS)

chat-langgraph: ## Start chat with LangGraph Agent
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent langgraph $(AGENT_FLAGS)

# Ask aliases
ask-claude: ## Single query with Claude Agent
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent claude $(AGENT_FLAGS)

ask-pydantic: ## Single query with Pydantic AI Agent
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent pydantic $(AGENT_FLAGS)

ask-langgraph: ## Single query with LangGraph Agent
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent langgraph $(AGENT_FLAGS)

# Orchestrator chat aliases
chat-orch-claude: ## Start chat with Claude Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent claude --orchestrator $(AGENT_FLAGS)

chat-orch-pydantic: ## Start chat with Pydantic Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent pydantic --orchestrator $(AGENT_FLAGS)

chat-orch-langgraph: ## Start chat with LangGraph Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent langgraph --orchestrator $(AGENT_FLAGS)

# Orchestrator ask aliases
ask-orch-claude: ## Single query with Claude Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent claude --orchestrator $(AGENT_FLAGS)

ask-orch-pydantic: ## Single query with Pydantic Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent pydantic --orchestrator $(AGENT_FLAGS)

ask-orch-langgraph: ## Single query with LangGraph Orchestrator
	$(REGREADER_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent langgraph --orchestrator $(AGENT_FLAGS)

#----------------------------------------------------------------------
# SSE Mode 快捷方式（需要先运行 'make serve'）
#----------------------------------------------------------------------

chat-mcp-sse: ## Chat via MCP SSE (usage: make chat-mcp-sse AGENT=claude)
	$(MAKE) chat MODE=mcp-sse AGENT="$(AGENT)" REG_ID="$(REG_ID)"

chat-claude-sse: ## Chat with Claude Agent via MCP SSE
	$(MAKE) chat-claude MODE=mcp-sse REG_ID="$(REG_ID)"

chat-pydantic-sse: ## Chat with Pydantic AI Agent via MCP SSE
	$(MAKE) chat-pydantic MODE=mcp-sse REG_ID="$(REG_ID)"

chat-langgraph-sse: ## Chat with LangGraph Agent via MCP SSE
	$(MAKE) chat-langgraph MODE=mcp-sse REG_ID="$(REG_ID)"

#----------------------------------------------------------------------
# 长文本查询输入方式示例
#----------------------------------------------------------------------

.PHONY: ask-examples
ask-examples: ## Show examples for long query input methods
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)长文本查询输入方式示例$(NC)"
	@echo "$(GREEN)========================================$(NC)"
	@echo ""
	@echo "$(BLUE)方案 1: 从文件读取（推荐）$(NC)"
	@echo "  1. 创建查询文件:"
	@echo "     cat > queries/my_query.txt <<'EOF'"
	@echo "     请详细说明母线失压的处理流程，包括："
	@echo "     1. 故障判断标准"
	@echo "     2. 应急处理步骤"
	@echo "     3. 恢复操作流程"
	@echo "     EOF"
	@echo ""
	@echo "  2. 使用文件查询:"
	@echo "     make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude REG_ID=angui_2024"
	@echo ""
	@echo "$(BLUE)方案 2: 从 stdin 读取$(NC)"
	@echo "  1. 管道输入:"
	@echo "     cat queries/my_query.txt | make ask-stdin AGENT=pydantic REG_ID=angui_2024"
	@echo ""
	@echo "  2. 重定向输入:"
	@echo "     make ask-stdin AGENT=claude REG_ID=angui_2024 < queries/my_query.txt"
	@echo ""
	@echo "  3. Echo 输入:"
	@echo "     echo '母线失压如何处理？' | make ask-stdin AGENT=claude"
	@echo ""
	@echo "$(BLUE)方案 3: Here-Document（Bash 原生，无需修改代码）$(NC)"
	@echo "  make ask ASK_QUERY=\"\$$(cat <<'EOF'"
	@echo "  请详细说明母线失压的处理流程，包括："
	@echo "  1. 故障判断标准"
	@echo "  2. 应急处理步骤"
	@echo "  3. 恢复操作流程"
	@echo "  EOF"
	@echo "  )\" AGENT=claude REG_ID=angui_2024"
	@echo ""
	@echo "$(BLUE)方案 4: 直接使用 regreader CLI$(NC)"
	@echo "  regreader ask \"\$$(cat queries/my_query.txt)\" -r angui_2024 --agent claude"
	@echo ""
	@echo "$(GREEN)========================================$(NC)"
