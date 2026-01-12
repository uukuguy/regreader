# ============================================================
# GridCode Makefile - Agents 模块
# ============================================================
# Agent 命令统一接口
# 依赖: mk/variables.mk
# ============================================================

include makefiles/variables.mk

#----------------------------------------------------------------------
# 通用 Agent 命令
#----------------------------------------------------------------------

chat: ## Start interactive chat (usage: make chat REG_ID=angui AGENT=claude MODE=mcp-sse)
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

ask: ## Single query to Agent (usage: make ask ASK_QUERY="母线失压如何处理?" AGENT=claude)
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS)

ask-json: ## Single query with JSON output
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) $(AGENT_FLAGS) --json

chat-orch: ## Start chat with Orchestrator (usage: make chat-orch REG_ID=angui AGENT=claude)
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent $(AGENT) --orchestrator $(AGENT_FLAGS)

ask-orch: ## Single query with Orchestrator (usage: make ask-orch ASK_QUERY="表6-2注1的内容")
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent $(AGENT) --orchestrator $(AGENT_FLAGS)

#----------------------------------------------------------------------
# Agent 快捷别名（向后兼容）
#----------------------------------------------------------------------

# Chat aliases
chat-claude: ## Start chat with Claude Agent SDK
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent claude $(AGENT_FLAGS)

chat-pydantic: ## Start chat with Pydantic AI Agent
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent pydantic $(AGENT_FLAGS)

chat-langgraph: ## Start chat with LangGraph Agent
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent langgraph $(AGENT_FLAGS)

# Ask aliases
ask-claude: ## Single query with Claude Agent
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent claude $(AGENT_FLAGS)

ask-pydantic: ## Single query with Pydantic AI Agent
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent pydantic $(AGENT_FLAGS)

ask-langgraph: ## Single query with LangGraph Agent
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent langgraph $(AGENT_FLAGS)

# Orchestrator chat aliases
chat-orch-claude: ## Start chat with Claude Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent claude --orchestrator $(AGENT_FLAGS)

chat-orch-pydantic: ## Start chat with Pydantic Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent pydantic --orchestrator $(AGENT_FLAGS)

chat-orch-langgraph: ## Start chat with LangGraph Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) chat $(REG_ID_FLAG) --agent langgraph --orchestrator $(AGENT_FLAGS)

# Orchestrator ask aliases
ask-orch-claude: ## Single query with Claude Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent claude --orchestrator $(AGENT_FLAGS)

ask-orch-pydantic: ## Single query with Pydantic Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent pydantic --orchestrator $(AGENT_FLAGS)

ask-orch-langgraph: ## Single query with LangGraph Orchestrator
	$(GRIDCODE_CMD) $(MCP_FLAGS) ask "$(ASK_QUERY)" $(REG_ID_FLAG) --agent langgraph --orchestrator $(AGENT_FLAGS)

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
