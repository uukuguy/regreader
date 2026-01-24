# ============================================================
# Makefile.pkgmgr - 统一包管理器模板
# ============================================================
# 自动检测 uv/conda 并提供统一的命令接口
# 版本: 1.0.0
# 许可: MIT
# 用法: 在项目 Makefile 中 include Makefile.pkgmgr
# ============================================================

#----------------------------------------------------------------------
# 后端自动检测
#----------------------------------------------------------------------
# 检测优先级:
# 1. 环境变量 PKGMGR_BACKEND (uv/conda)
# 2. 如果在 conda 环境中 (CONDA_PREFIX 非空) -> conda
# 3. 如果 uv 可用且不在 conda 环境 -> uv
# 4. 如果 conda 可用 -> conda
# 5. 报错并提示安装

# 允许通过环境变量强制指定后端
ifdef PKGMGR_BACKEND
    BACKEND := $(PKGMGR_BACKEND)
else
    # 检测是否在 conda 环境中
    ifdef CONDA_PREFIX
        BACKEND := conda
    else
        # 检测 uv 是否可用
        UV_AVAILABLE := $(shell command -v uv 2>/dev/null)
        ifneq ($(UV_AVAILABLE),)
            BACKEND := uv
        else
            # 检测 conda 是否可用
            CONDA_AVAILABLE := $(shell command -v conda 2>/dev/null)
            ifneq ($(CONDA_AVAILABLE),)
                BACKEND := conda
            else
                BACKEND := none
            endif
        endif
    endif
endif

# 后端验证
ifeq ($(BACKEND),none)
    $(error No package manager found. Please install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh)
endif

#----------------------------------------------------------------------
# 颜色输出
#----------------------------------------------------------------------

BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

#----------------------------------------------------------------------
# 后端特定配置
#----------------------------------------------------------------------

# uv 配置
ifeq ($(BACKEND),uv)
    RUN_PREFIX := uv run
    INSTALL_BASE := uv sync
    INSTALL_DEV := uv sync --extra dev
    INSTALL_ALL := uv sync --all-extras
    ADD_PKG := uv add
    REMOVE_PKG := uv remove
    LOCK_CMD := uv lock
    BACKEND_NAME := uv
endif

# conda 配置
ifeq ($(BACKEND),conda)
    RUN_PREFIX :=
    # 从项目根目录读取约束文件（如果存在）
    CONSTRAINTS_FILE := constraints-conda.txt
    ifneq ($(wildcard $(CONSTRAINTS_FILE)),)
        CONDA_CONSTRAINTS := -c $(CONSTRAINTS_FILE)
    else
        CONDA_CONSTRAINTS :=
    endif
    INSTALL_FLAGS := $(CONDA_CONSTRAINTS) --upgrade-strategy only-if-needed
    INSTALL_BASE := pip install $(INSTALL_FLAGS) -e .
    INSTALL_DEV := pip install $(INSTALL_FLAGS) -e ".[dev]"
    INSTALL_ALL := pip install $(INSTALL_FLAGS) -e ".[dev,tantivy,whoosh,qdrant,flag,otel,otel-otlp]"
    ADD_PKG := pip install $(INSTALL_FLAGS)
    REMOVE_PKG := pip uninstall -y
    LOCK_CMD := pip freeze > requirements-conda.txt
    BACKEND_NAME := conda (pip)
endif

#----------------------------------------------------------------------
# 统一命令接口
#----------------------------------------------------------------------

.PHONY: pkgmgr-info pkgmgr-install pkgmgr-install-dev pkgmgr-install-all \
        pkgmgr-add pkgmgr-remove pkgmgr-lock pkgmgr-help

pkgmgr-info: ## Show detected package manager backend
	@echo "$(GREEN)Package Manager Backend: $(BACKEND_NAME)$(NC)"
	@echo "$(BLUE)Run Prefix: $(RUN_PREFIX)$(NC)"
	@echo "$(BLUE)Install Command: $(INSTALL_BASE)$(NC)"

pkgmgr-install: ## Install base dependencies
	@echo "$(BLUE)Installing base dependencies with $(BACKEND_NAME)...$(NC)"
	$(INSTALL_BASE)
	@echo "$(GREEN)Installation complete!$(NC)"

pkgmgr-install-dev: ## Install with dev dependencies
	@echo "$(BLUE)Installing dev dependencies with $(BACKEND_NAME)...$(NC)"
	$(INSTALL_DEV)
	@echo "$(GREEN)Installation complete!$(NC)"

pkgmgr-install-all: ## Install with all optional dependencies
	@echo "$(BLUE)Installing all dependencies with $(BACKEND_NAME)...$(NC)"
	$(INSTALL_ALL)
	@echo "$(GREEN)Installation complete!$(NC)"

pkgmgr-add: ## Add a package (usage: make pkgmgr-add PKG=package-name)
	@if [ -z "$(PKG)" ]; then \
		echo "$(RED)Error: PKG is required$(NC)"; \
		echo "Usage: make pkgmgr-add PKG=package-name"; \
		exit 1; \
	fi
	@echo "$(BLUE)Adding package: $(PKG) with $(BACKEND_NAME)...$(NC)"
	$(ADD_PKG) $(PKG)

pkgmgr-remove: ## Remove a package (usage: make pkgmgr-remove PKG=package-name)
	@if [ -z "$(PKG)" ]; then \
		echo "$(RED)Error: PKG is required$(NC)"; \
		echo "Usage: make pkgmgr-remove PKG=package-name"; \
		exit 1; \
	fi
	@echo "$(BLUE)Removing package: $(PKG) with $(BACKEND_NAME)...$(NC)"
	$(REMOVE_PKG) $(PKG)

pkgmgr-lock: ## Lock dependencies
	@echo "$(BLUE)Locking dependencies with $(BACKEND_NAME)...$(NC)"
	$(LOCK_CMD)
	@echo "$(GREEN)Dependencies locked!$(NC)"

pkgmgr-help: ## Show package manager help
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)Package Manager Unified Interface$(NC)"
	@echo "$(GREEN)========================================$(NC)"
	@echo ""
	@echo "$(BLUE)Detected Backend: $(BACKEND_NAME)$(NC)"
	@echo ""
	@echo "$(YELLOW)Available Commands:$(NC)"
	@echo "  make pkgmgr-info          Show backend information"
	@echo "  make pkgmgr-install       Install base dependencies"
	@echo "  make pkgmgr-install-dev   Install with dev dependencies"
	@echo "  make pkgmgr-install-all   Install with all optional dependencies"
	@echo "  make pkgmgr-add PKG=...   Add a package"
	@echo "  make pkgmgr-remove PKG=...Remove a package"
	@echo "  make pkgmgr-lock          Lock dependencies"
	@echo ""
	@echo "$(YELLOW)Force Backend Selection:$(NC)"
	@echo "  PKGMGR_BACKEND=uv make pkgmgr-install"
	@echo "  PKGMGR_BACKEND=conda make pkgmgr-install"
	@echo ""
	@echo "$(YELLOW)Run Commands (use RUN_PREFIX):$(NC)"
	@echo "  \$$(RUN_PREFIX) python script.py"
	@echo "  \$$(RUN_PREFIX) pytest tests/"
	@echo "  \$$(RUN_PREFIX) regreader serve"
