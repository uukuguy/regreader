# Makefile 重构文档

## 概述

本次重构将原 696 行的单体 Makefile 拆分为模块化结构，提高了可维护性、可读性和可扩展性。

**重构目标:**
- 提高可维护性 - 代码模块化，职责清晰
- 改善可读性 - 消除重复，简化命令
- 增强可扩展性 - 易于添加新功能

**核心策略:**
- 混合方案：渐进式重构 + 模块化拆分
- 向后兼容：所有现有命令保持不变
- 功能隔离：Conda、Agent、MCP 工具分离

## 文件结构

```
regreader/
├── Makefile                    # 主入口 (247 行)
├── makefiles/                  # Makefile 模块目录
│   ├── variables.mk            # 统一变量定义 (65 行)
│   ├── conda.mk                # Conda 环境专用 (106 行)
│   ├── agents.mk               # Agent 命令接口 (87 行)
│   └── mcp-tools.mk            # MCP 工具 CLI (176 行)
└── scripts/makefile/           # Python 辅助脚本
    ├── table_registry_build.py
    ├── table_registry_stats.py
    └── list_cross_page_tables.py
```

## 模块说明

### 1. variables.mk - 变量定义模块

**职责:** 集中管理所有变量、默认值和配置

**核心变量:**

```makefile
# 工具链
PYTHON := python
UV := uv
GRIDCODE := regreader

# 命令前缀（消除 70+ 处重复）
UV_RUN := $(UV) run
REGREADER_CMD := $(UV_RUN) $(GRIDCODE)
PY_CMD := $(UV_RUN) $(PYTHON)

# Agent 配置
AGENT ?= claude
AGENTS := claude pydantic langgraph

# 默认值
REG_ID ?= wengui_2024
FILE ?= ./data/raw/wengui_2024.pdf
MAX_LEVEL ?= 3
START_PAGE ?= 4
END_PAGE ?= 6

# MCP 模式配置
MODE ?= local  # local, mcp-stdio, mcp-sse
MCP_FLAGS := [根据 MODE 自动设置]

# Conda 依赖包列表（消除 5 处重复）
CONDA_BASE_DEPS := pydantic pydantic-settings lancedb mcp ...
CONDA_DEV_DEPS := $(CONDA_BASE_DEPS) pytest pytest-asyncio ruff
CONDA_ALL_DEPS := $(CONDA_DEV_DEPS) tantivy whoosh jieba qdrant-client
```

**使用方式:**
- 在其他模块中通过 `include makefiles/variables.mk` 引入
- 使用 `$(REGREADER_CMD)` 代替 `$(UV) run regreader`
- 使用 `$(CONDA_BASE_DEPS)` 代替长字符串依赖列表

### 2. conda.mk - Conda 环境模块

**职责:** 隔离所有 Conda 相关功能（仅 Linux 服务器使用）

**主要功能:**

#### 安装命令
```bash
make install-conda           # 基础安装（不含 docling）
make install-conda-dev       # 开发依赖
make install-conda-all       # 所有可选后端
make install-conda-ocr       # OCR 支持（含 docling）
make install-conda-full      # 完整文档处理
```

#### MCP 服务
```bash
make serve-conda             # SSE 模式，端口 8080
make serve-conda-stdio       # stdio 模式
make serve-conda-port PORT=9000  # 自定义端口
```

#### CLI 命令
```bash
make chat-conda AGENT=claude REG_ID=angui_2024
make ask-conda ASK_QUERY="母线失压如何处理?"
make list-conda
make search-conda QUERY="故障处理"
```

#### Agent 快捷方式
```bash
make chat-conda-claude       # Claude Agent
make chat-conda-pydantic     # Pydantic AI Agent
make chat-conda-langgraph    # LangGraph Agent
make ask-conda-claude ASK_QUERY="..."
```

**技术实现:**
- 使用 `pip install $(CONDA_INSTALL_FLAGS) $(CONDA_BASE_DEPS)` 简化命令
- 不使用 UV 包管理器，直接调用 `regreader` 命令
- 使用 Make 变量覆盖实现快捷方式: `AGENT=claude`

### 3. agents.mk - Agent 命令模块

**职责:** 简化 Agent 三角形模式，提供统一接口

**设计思路:**
- 原有 21 个目标 (chat/ask × claude/pydantic/langgraph × uv/conda/orch/sse)
- 重构为 4 个通用命令 + 别名系统

#### 通用命令
```bash
# 基础命令（通过 AGENT 参数指定）
make chat AGENT=claude REG_ID=angui MODE=local
make ask ASK_QUERY="查询内容" AGENT=pydantic
make ask-json ASK_QUERY="..." AGENT=langgraph

# Orchestrator 模式（Subagent 架构）
make chat-orch AGENT=claude REG_ID=angui
make ask-orch ASK_QUERY="..." AGENT=pydantic
```

#### Agent 快捷别名（向后兼容）
```bash
# Chat 快捷方式
make chat-claude             # 等价于 chat AGENT=claude
make chat-pydantic           # 等价于 chat AGENT=pydantic
make chat-langgraph          # 等价于 chat AGENT=langgraph

# Ask 快捷方式
make ask-claude ASK_QUERY="..."
make ask-pydantic ASK_QUERY="..."
make ask-langgraph ASK_QUERY="..."

# Orchestrator 快捷方式
make chat-orch-claude
make ask-orch-pydantic ASK_QUERY="..."
```

#### SSE 模式快捷方式
```bash
# 需要先运行 make serve
make chat-claude-sse REG_ID=angui
make chat-pydantic-sse
make chat-langgraph-sse
```

**技术实现:**
- 通用命令使用 `$(AGENT)` 变量动态指定 Agent
- 快捷方式使用 Make 目标依赖和变量覆盖
- SSE 模式通过 `$(MAKE)` 递归调用并覆盖 `MODE=mcp-sse`

**优势:**
- 减少目标数量：21 → 6 个通用命令 + 别名
- 新增 Agent 只需在 `variables.mk` 中添加到 `AGENTS` 列表
- 保持向后兼容性

### 4. mcp-tools.mk - MCP 工具模块

**职责:** 整合所有 MCP 工具 CLI 命令

**工具分类:**

#### 基础工具
```bash
make toc REG_ID=angui MAX_LEVEL=3
make read-pages REG_ID=angui START_PAGE=85 END_PAGE=87
make read-chapter REG_ID=angui SECTION="2.1.4.1.6"
make chapter-structure REG_ID=angui
make page-info REG_ID=angui PAGE_NUM=85
```

#### Phase 1: 核心多跳工具
```bash
make lookup-annotation REG_ID=angui ANNOTATION_ID="注1" PAGE_NUM=85
make search-tables REG_ID=angui TABLE_QUERY="母线失压" TABLE_SEARCH_MODE=hybrid
make resolve-reference REG_ID=angui REFERENCE="见第六章"
```

#### Phase 2: 上下文工具
```bash
make search-annotations REG_ID=angui PATTERN="电压" ANNOTATION_TYPE=note
make get-table REG_ID=angui TABLE_ID="table_001"
make get-block-context REG_ID=angui BLOCK_ID="block_xxx" CONTEXT=2
```

#### Phase 3: 发现工具
```bash
make find-similar REG_ID=angui SIMILAR_QUERY="母线失压处理" LIMIT=5
make compare-sections REG_ID=angui SECTION_A="2.1.4" SECTION_B="2.1.5"
```

#### 表格注册表工具
```bash
make build-table-registry REG_ID=angui_2024
make build-table-index REG_ID=angui_2024 REBUILD_INDEX=true
make table-registry-stats REG_ID=angui_2024
make list-cross-page-tables REG_ID=angui_2024
```

#### MCP 模式快捷方式
```bash
# stdio 模式
make list-mcp
make search-mcp QUERY="母线失压"
make toc-mcp REG_ID=angui
make read-pages-mcp START_PAGE=85 END_PAGE=87

# SSE 模式（需要先运行 make serve）
make list-mcp-sse
make search-mcp-sse QUERY="母线失压"
make toc-mcp-sse REG_ID=angui
make read-pages-mcp-sse START_PAGE=85 END_PAGE=87
```

#### MCP 服务验证
```bash
make mcp-tools              # 列出工具元数据（静态）
make mcp-tools-v            # 详细信息
make mcp-tools-live         # 从运行中的服务器获取（stdio）
make mcp-verify             # 完整性验证（stdio）
make mcp-verify-v           # 详细验证输出
make mcp-verify-sse         # SSE 模式验证（需要 make serve）
```

**技术实现:**
- 使用 `$(REGREADER_CMD) $(MCP_FLAGS)` 统一命令前缀
- 使用 shell 条件判断处理可选参数
- 使用 `$(MAKE)` 递归调用实现 MCP 模式切换

## Python 辅助脚本

**背景:** 原 Makefile 包含 3 处超长 Python 一行代码（200+ 字符），违反代码规范

**解决方案:** 提取为独立 Python 脚本

### 1. table_registry_build.py

**功能:** 构建表格注册表

```python
def build_table_registry(reg_id: str) -> None:
    """构建表格注册表

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()
    info = ps.load_info(reg_id)
    pages = [ps.load_page(reg_id, i) for i in range(1, info.total_pages + 1)]
    builder = TableRegistryBuilder(reg_id)
    registry = builder.build(pages)
    ps.save_table_registry(registry)
    print(f"Done: {registry.total_tables} tables, {registry.cross_page_tables} cross-page")
```

**使用:**
```bash
make build-table-registry REG_ID=angui_2024
# 等价于: python scripts/makefile/table_registry_build.py angui_2024
```

### 2. table_registry_stats.py

**功能:** 显示表格注册表统计信息

```python
def show_stats(reg_id: str) -> None:
    """显示表格注册表统计信息

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()
    reg = ps.load_table_registry(reg_id)
    if reg:
        print(f"Total tables: {reg.total_tables}")
        print(f"Cross-page tables: {reg.cross_page_tables}")
        print(f"Segment mappings: {len(reg.segment_to_table)}")
```

**使用:**
```bash
make table-registry-stats REG_ID=angui_2024
```

### 3. list_cross_page_tables.py

**功能:** 列出所有跨页表格

```python
def list_cross_page_tables(reg_id: str) -> None:
    """列出所有跨页表格

    Args:
        reg_id: 规程标识符（如 angui_2024）
    """
    ps = PageStore()
    reg = ps.load_table_registry(reg_id)
    if reg:
        for tid, e in reg.tables.items():
            if e.is_cross_page:
                print(f"{tid}: P{e.page_start}-{e.page_end} ({len(e.segments)} segs)")
```

**使用:**
```bash
make list-cross-page-tables REG_ID=angui_2024
```

**优势:**
- ✅ 符合 Black 代码规范（100 字符限制）
- ✅ 可独立测试和维护
- ✅ 提供完整的错误处理和帮助信息
- ✅ 支持命令行参数验证

## 重构成果

### 数量统计

| 指标 | 重构前 | 重构后 | 改进 |
|------|--------|--------|------|
| 主 Makefile 行数 | 696 | 247 | -64.5% |
| 模块数量 | 1 | 5 | 模块化 |
| Python 一行代码 | 3 | 0 | 全部提取 |
| UV 前缀重复 | 70+ | 0 | 使用变量 |
| Conda 依赖重复 | 5 × 200+ 字符 | 1 个变量 | -80% |
| Agent 目标数 | 21 | 6 + 别名 | -71% |
| 超过 100 字符的行 | 多处 | 显著减少 | 改善 |

### 代码质量改进

**可维护性:**
- ✅ 模块职责清晰，易于定位和修改
- ✅ 变量集中管理，修改一处即可
- ✅ Python 脚本独立维护和测试

**可读性:**
- ✅ 消除大量重复代码
- ✅ 命令前缀统一，易于理解
- ✅ 模块化结构，层次分明

**可扩展性:**
- ✅ 新增 Agent 只需在变量中定义
- ✅ 新增 MCP 工具添加到对应模块
- ✅ 新增 Conda 命令添加到 conda.mk

**向后兼容性:**
- ✅ 所有现有命令保持不变
- ✅ 命令行参数语义不变
- ✅ 输出格式保持一致

## 使用指南

### 基本用法

```bash
# 安装
make install              # UV 模式（推荐）
make install-conda        # Conda 模式（Linux 服务器）

# MCP 服务
make serve                # 启动 SSE 服务（端口 8080）
make serve-stdio          # 启动 stdio 服务

# Agent 聊天
make chat AGENT=claude REG_ID=angui_2024
make chat-pydantic REG_ID=wengui_2024

# 单次查询
make ask ASK_QUERY="母线失压如何处理?" AGENT=claude
make ask-json ASK_QUERY="..." AGENT=pydantic

# MCP 工具
make toc REG_ID=angui_2024
make search-tables TABLE_QUERY="母线失压"
make lookup-annotation ANNOTATION_ID="注1" PAGE_NUM=85
```

### 高级用法

#### MCP 模式切换

```bash
# 本地模式（默认）
make chat AGENT=claude MODE=local

# stdio 模式
make chat AGENT=claude MODE=mcp-stdio

# SSE 模式（需要先运行 make serve）
make chat AGENT=claude MODE=mcp-sse
# 或使用快捷方式
make chat-claude-sse
```

#### Orchestrator 模式（Subagent 架构）

```bash
# 启动 Orchestrator 聊天
make chat-orch AGENT=claude REG_ID=angui_2024
make chat-orch-pydantic REG_ID=wengui_2024

# 单次查询
make ask-orch ASK_QUERY="表6-2注1的内容" AGENT=claude
make ask-orch-pydantic ASK_QUERY="三峡安控系统配置"
```

#### 自定义参数

```bash
# 自定义页面范围
make read-pages REG_ID=angui START_PAGE=10 END_PAGE=20

# 自定义搜索限制
make find-similar SIMILAR_QUERY="故障处理" LIMIT=10

# 自定义上下文大小
make get-block-context BLOCK_ID="block_xxx" CONTEXT=5
```

### Conda 环境使用

```bash
# 1. 安装（假设已有 conda 环境和 torch）
make install-conda

# 2. 启动服务
make serve-conda

# 3. 使用 CLI（在另一个终端）
make chat-conda-claude REG_ID=angui_2024
make ask-conda-pydantic ASK_QUERY="母线失压如何处理?"
make list-conda
```

## 扩展开发

### 添加新 Agent

1. 在 `makefiles/variables.mk` 中添加:
```makefile
AGENTS := claude pydantic langgraph new_agent
```

2. 自动获得所有命令:
```bash
make chat-new_agent
make ask-new_agent
make chat-orch-new_agent
```

### 添加新 MCP 工具

在 `makefiles/mcp-tools.mk` 中添加:
```makefile
new-tool: ## New tool description
	$(REGREADER_CMD) $(MCP_FLAGS) new-tool --arg1 $(ARG1) --arg2 $(ARG2)
```

### 添加新 Conda 命令

在 `makefiles/conda.mk` 中添加:
```makefile
new-conda-command: ## Description
	regreader new-command --options
```

## 最佳实践

### 1. 变量使用

**推荐:**
```makefile
$(REGREADER_CMD) chat --reg-id $(REG_ID)
```

**不推荐:**
```makefile
$(UV) run regreader chat --reg-id angui_2024
```

### 2. 可选参数处理

**推荐:**
```makefile
target:
	@if [ -z "$(REQUIRED_ARG)" ]; then \
		echo "Error: REQUIRED_ARG is required"; \
		exit 1; \
	fi
	@if [ -n "$(OPTIONAL_ARG)" ]; then \
		$(REGREADER_CMD) command --required $(REQUIRED_ARG) --optional $(OPTIONAL_ARG); \
	else \
		$(REGREADER_CMD) command --required $(REQUIRED_ARG); \
	fi
```

### 3. 快捷方式实现

**推荐:**
```makefile
chat-claude: ## Chat with Claude Agent
	$(REGREADER_CMD) $(MCP_FLAGS) chat --reg-id $(REG_ID) --agent claude
```

**或使用变量覆盖:**
```makefile
chat-claude: AGENT=claude
chat-claude: chat
```

### 4. 错误提示

**推荐:**
```makefile
target:
	@echo "$(YELLOW)Warning: This is a warning$(NC)"
	@echo "$(BLUE)Info: Processing...$(NC)"
	@echo "$(GREEN)Success: Done!$(NC)"
```

## 故障排除

### 问题 1: 找不到模块文件

**错误信息:**
```
make: *** No rule to make target `makefiles/variables.mk', needed by `Makefile'.  Stop.
```

**解决方案:**
- 确认 `makefiles/` 目录存在
- 确认所有 `.mk` 文件存在
- 检查 include 路径是否正确

### 问题 2: Conda 命令不工作

**症状:** `make chat-conda` 报错 "regreader: command not found"

**解决方案:**
```bash
# 1. 确认在 conda 环境中
conda activate your-env

# 2. 重新安装
make install-conda

# 3. 验证安装
which regreader
regreader --version
```

### 问题 3: MCP 模式不工作

**症状:** `make chat MODE=mcp-sse` 无法连接

**解决方案:**
```bash
# 1. 先启动服务
make serve

# 2. 在另一个终端使用
make chat MODE=mcp-sse AGENT=claude
# 或使用快捷方式
make chat-claude-sse
```

## 版本历史

### v2.0.0 (2025-01-11) - 模块化重构

**Phase 1: 变量提取和脚本化**
- ✅ 创建 `makefiles/variables.mk`
- ✅ 提取 3 个 Python 脚本
- ✅ 简化 Conda 依赖管理

**Phase 2: 模块化拆分**
- ✅ 创建 `makefiles/conda.mk`
- ✅ 创建 `makefiles/agents.mk`
- ✅ 创建 `makefiles/mcp-tools.mk`

**成果:**
- 主 Makefile: 696 → 247 行 (-64.5%)
- 模块化: 1 → 5 个文件
- 代码重复: 显著减少
- 可维护性: 大幅提升

## 参考资料

- [RegReader CLAUDE.md](../../CLAUDE.md) - 项目开发指南
- [Bash+FS 架构设计](./BASH_FS_ARCHITECTURE.md)
- [Makefile 最佳实践](https://makefiletutorial.com/)
- [GNU Make 文档](https://www.gnu.org/software/make/manual/)

## 贡献指南

如需修改 Makefile 结构：

1. **变量修改** → 编辑 `makefiles/variables.mk`
2. **Conda 命令** → 编辑 `makefiles/conda.mk`
3. **Agent 命令** → 编辑 `makefiles/agents.mk`
4. **MCP 工具** → 编辑 `makefiles/mcp-tools.mk`
5. **核心功能** → 编辑主 `Makefile`

**测试验证:**
```bash
# 语法检查
make -n target

# 功能测试
make target [ARGS]

# 完整验证
make help | grep target
```
