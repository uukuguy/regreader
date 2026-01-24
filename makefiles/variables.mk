# ============================================================
# RegReader Makefile 变量定义
# ============================================================

# 导入统一包管理器模板（自动检测 uv/conda）
include makefiles/pkgmgr.mk

# 工具链
PYTHON := python
PYTEST := pytest
RUFF := ruff
REGREADER := regreader

# 命令前缀（使用统一的 RUN_PREFIX，自动适配 uv/conda）
REGREADER_CMD := $(RUN_PREFIX) $(REGREADER)
PY_CMD := $(RUN_PREFIX) $(PYTHON)

# Agent 配置
AGENT ?= claude
AGENTS := claude pydantic langgraph
AGENT_FLAGS ?=  # 额外的 agent 参数，如 -v (verbose), -q (quiet)
DISPLAY ?= simple  # 显示模式: simple (默认), clean (简洁), enhanced (增强)

# AgentEx 配置（新的 agents_v2 实现）
# 设置 USE_AGENTEX=true 使用基于 agentex 的新实现
USE_AGENTEX ?= false
ifeq ($(USE_AGENTEX),true)
    AGENTEX_ENV := REGREADER_USE_AGENTEX=true
else
    AGENTEX_ENV :=
endif

# 默认值集中管理
REG_ID ?=  # 空值表示自动识别规程（推荐），也可显式指定如 REG_ID=wengui_2024
FILE ?= ./data/raw/wengui_2024.pdf
ASK_QUERY ?= 长南Ⅰ线停运会影响哪些断面的限额？
QUERY_FILE ?=  # 查询文件路径（用于 ask-file 命令）

# 条件性地设置 REG_ID_FLAG（只在 REG_ID 非空时添加 --reg-id 参数）
ifneq ($(REG_ID),)
    REG_ID_FLAG := --reg-id $(REG_ID)
else
    REG_ID_FLAG :=
endif

MAX_LEVEL ?= 3
START_PAGE ?= 4
END_PAGE ?= 6
PAGE_NUM ?= 7
LIMIT ?= 5
CONTEXT ?= 2
PORT ?= 8080

# MCP 模式配置
MODE ?= local
MCP_URL ?= http://127.0.0.1:8080/sse

ifeq ($(MODE),mcp-stdio)
    MCP_FLAGS := --mcp
else ifeq ($(MODE),mcp-sse)
    MCP_FLAGS := --mcp --mcp-transport sse --mcp-url $(MCP_URL)
else
    MCP_FLAGS :=
endif

# 颜色输出
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m

# Conda 依赖包列表（已弃用，保留用于向后兼容）
# 注意：现在使用 Makefile.pkgmgr 的统一接口，这些变量仅用于 conda.mk 的向后兼容
CONDA_BASE_DEPS := pydantic pydantic-settings lancedb mcp typer rich loguru \
                   anthropic claude-agent-sdk "pydantic-ai>=1.0.0" \
                   langgraph langchain-anthropic langchain-openai sentence-transformers

CONDA_DEV_DEPS := $(CONDA_BASE_DEPS) pytest pytest-asyncio ruff

CONDA_ALL_DEPS := $(CONDA_DEV_DEPS) tantivy whoosh jieba qdrant-client

CONDA_OCR_DEPS := docling $(CONDA_BASE_DEPS) rapidocr-onnxruntime

CONDA_FULL_DEPS := docling $(CONDA_BASE_DEPS)

CONDA_INSTALL_FLAGS := -c constraints-conda.txt --upgrade-strategy only-if-needed
