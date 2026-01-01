# GridCode 开发工作日志 (dev 分支)

## 2026-01-02 代码分析与文档更新

### 会话概述

对当前代码实现进行全面分析，更新 CLAUDE.md 项目指南，并生成最新的系统设计与实现文档。

### 完成的工作

#### 1. 全面代码分析

对项目各模块进行了深入分析：

**Parser 层**
- `docling_parser.py` - 文档解析器，支持 OCR 和表格结构提取
- `page_extractor.py` - 页面内容提取器
- `table_registry_builder.py` - 跨页表格处理

**Storage 层**
- `models.py` - 核心数据模型 (PageDocument, ContentBlock, DocumentStructure, TableRegistry 等)
- `page_store.py` - 页面持久化存储管理

**Index 层**
- `base.py` - 抽象基类定义
- `hybrid_search.py` - RRF 混合检索器
- `table_search.py` - 表格混合检索
- `keyword/` - FTS5/Tantivy/Whoosh 关键词索引实现
- `vector/` - LanceDB/Qdrant 向量索引实现

**Embedding 层**
- `base.py` - 嵌入抽象接口
- `sentence_transformer.py` - SentenceTransformer 后端
- `flag.py` - FlagEmbedding 后端

**MCP 层**
- `tools.py` - 工具实现（4 阶段分类：基础/多跳/上下文/发现）
- `server.py` - FastMCP Server 创建
- `tool_metadata.py` - 工具元数据
- `client.py` - MCP 客户端

**Agent 层**
- `base.py` - Agent 抽象基类
- `claude_agent.py` - Claude Agent SDK 实现
- `pydantic_agent.py` - Pydantic AI 实现
- `langgraph_agent.py` - LangGraph 实现
- `memory.py` - 对话历史管理
- `display.py` - 状态显示回调
- `mcp_connection.py` - MCP 连接配置

#### 2. CLAUDE.md 更新

更新了项目开发指南，包括：

- **项目结构**: 更新为完整的目录树，包含所有子模块和文件
- **技术栈**: 添加 Embedding 层（SentenceTransformer/FlagEmbedding）
- **数据模型**: 扩展为三个分类（页面级/结构/检索）
- **MCP 工具接口**: 按 Phase 0-3 分类展示全部工具
- **开发约束**: 添加 Embedding 层扩展指南
- **CLI 命令**: 完整列出所有命令及示例
- **配置系统**: 添加完整环境变量参考
- **异常体系**: 列出完整异常类层次结构
- **文档路径**: 更新为 dev 分支路径

#### 3. 设计实施文档

创建 `docs/dev/DESIGN_DOCUMENT.md`，包含：

- **项目概述**: 定位、设计理念、技术栈架构图
- **数据模型设计**: 核心模型层级、章节结构模型、检索模型
- **存储层实现**: PageStore、TableRegistry 详细设计
- **索引层实现**: 抽象接口、关键词/向量索引实现、混合检索
- **Embedding 层实现**: 抽象接口和具体实现
- **MCP 工具层实现**: 工具分类体系、核心工具实现、Server 实现
- **Agent 层实现**: 抽象基类、三种框架实现、对话历史管理
- **CLI 实现**: 命令结构和完整命令列表
- **配置系统**: GridCodeSettings 详细配置
- **异常体系**: 完整异常类定义
- **实现状态汇总**: 已完成模块和可选模块状态
- **技术亮点**: 架构设计、数据处理、检索优化、工具设计
- **附录**: 依赖清单、环境变量参考

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `CLAUDE.md` | 全面更新项目开发指南 |
| `docs/dev/DESIGN_DOCUMENT.md` | 新建 - 系统设计与实现文档 |
| `docs/dev/WORK_LOG.md` | 更新工作日志 |

### 技术亮点总结

1. **Page-Based 架构**: 保留文档原始结构，支持跨页内容处理
2. **可插拔索引**: 支持多种关键词和向量索引后端
3. **MCP 协议标准化**: 工具接口统一，多 Agent 框架复用
4. **三框架并行**: 同时支持 Claude SDK、Pydantic AI、LangGraph
5. **分阶段工具体系**: 基础 → 多跳 → 上下文 → 发现
6. **RRF 混合检索**: 结合关键词和语义检索优势

### 后续建议

1. 补充单元测试覆盖率
2. 添加集成测试用例
3. 完善 README.md 用户文档
4. 考虑添加性能基准测试

---

## 2025-12-30 Agent MCP 架构重构

### 会话概述

重构了三个 Agent 框架的 MCP 连接管理，实现统一的 `MCPConnectionConfig` 和 `MCPConnectionManager` 机制，支持 stdio（子进程）和 SSE（共享服务）两种传输方式，解决了原有架构中各 Agent 独立创建 MCP 连接的资源浪费问题。

### 背景问题

用户提出三个架构问题：
1. 3个Agent和客户端是什么关系？
2. 为什么在CLI中调用agent循环，但各自还要创建MCP server？
3. Agent设计是否与grid-code的整体架构适配？

分析后发现原有设计的问题：
- 三个 Agent 各自独立创建 MCP 连接配置
- 无法在运行时切换传输模式
- CLI 全局 MCP 配置无法传递给 Agent

### 完成的工作

#### 1. 核心模块 (新建)

创建 `src/grid_code/agents/mcp_connection.py`：

**MCPConnectionConfig** - MCP 连接配置类
```python
@dataclass
class MCPConnectionConfig:
    transport: Literal["stdio", "sse"] = "stdio"
    server_url: str | None = None
    server_name: str = MCP_SERVER_NAME

    @classmethod
    def from_settings(cls) -> MCPConnectionConfig:
        """从全局配置创建"""

    @classmethod
    def stdio(cls) -> MCPConnectionConfig:
        """创建 stdio 模式配置"""

    @classmethod
    def sse(cls, server_url: str | None = None) -> MCPConnectionConfig:
        """创建 SSE 模式配置"""
```

**MCPConnectionManager** - MCP 连接管理器（单例模式）
```python
class MCPConnectionManager:
    def get_claude_sdk_config(self) -> dict[str, Any]:
        """获取 Claude Agent SDK 格式的 MCP 配置"""

    def get_pydantic_mcp_server(self):
        """获取 Pydantic AI 的 MCP Server 对象"""

    def get_langgraph_client(self) -> GridCodeMCPClient:
        """获取 LangGraph 使用的 MCP 客户端"""
```

**便捷函数**
```python
def get_mcp_manager(config: MCPConnectionConfig | None = None) -> MCPConnectionManager
def configure_mcp(transport: Literal["stdio", "sse"] = "stdio", server_url: str | None = None) -> None
```

#### 2. Agent 改造

为三个 Agent 添加 `mcp_config` 参数：

**ClaudeAgent** (`src/grid_code/agents/claude_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_claude_sdk_config()` 获取配置
- SSE 模式自动回退到 stdio（Claude SDK 限制）

**PydanticAIAgent** (`src/grid_code/agents/pydantic_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_pydantic_mcp_server()` 获取 MCP Server
- 支持 stdio 和 SSE 两种模式

**LangGraphAgent** (`src/grid_code/agents/langgraph_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_langgraph_client()` 获取 MCP Client
- 完整支持 stdio 和 SSE 两种模式

#### 3. CLI 集成

修改 `src/grid_code/cli.py` 的 `chat` 命令：
```python
# 构建 MCP 配置（从全局状态）
if state.mcp_transport == "sse" and state.mcp_url:
    mcp_config = MCPConnectionConfig.sse(state.mcp_url)
else:
    mcp_config = MCPConnectionConfig.stdio()

# 传递给 Agent
agent = ClaudeAgent(reg_id=reg_id, mcp_config=mcp_config)
```

#### 4. 模块导出

更新 `src/grid_code/agents/__init__.py`：
```python
from .mcp_connection import MCPConnectionConfig, MCPConnectionManager, configure_mcp, get_mcp_manager

__all__ = [
    # ... existing exports ...
    # MCP Connection
    "MCPConnectionConfig",
    "MCPConnectionManager",
    "configure_mcp",
    "get_mcp_manager",
]
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/agents/mcp_connection.py` | 新建 - MCPConnectionConfig + MCPConnectionManager |
| `src/grid_code/agents/claude_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/grid_code/agents/pydantic_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/grid_code/agents/langgraph_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/grid_code/agents/__init__.py` | 导出新的 MCP 连接管理类 |
| `src/grid_code/cli.py` | chat 命令传递 MCP 配置 |
| `tests/dev/test_mcp_connection.py` | 新建 - 13 个单元测试 |

### 测试结果

```
tests/dev/test_mcp_connection.py - 13 passed
```

测试覆盖：
- ✅ MCPConnectionConfig 默认配置
- ✅ stdio/sse 工厂方法
- ✅ 单例模式
- ✅ 配置覆盖
- ✅ Claude SDK 配置获取（含 SSE 回退）
- ✅ LangGraph 客户端获取
- ✅ configure_mcp 便捷函数

### 使用示例

```python
# 方式1: 使用默认配置（stdio）
agent = ClaudeAgent(reg_id="angui_2024")

# 方式2: 显式指定 stdio 配置
from grid_code.agents import MCPConnectionConfig
config = MCPConnectionConfig.stdio()
agent = ClaudeAgent(reg_id="angui_2024", mcp_config=config)

# 方式3: 使用 SSE 配置
config = MCPConnectionConfig.sse("http://localhost:8080/sse")
agent = LangGraphAgent(reg_id="angui_2024", mcp_config=config)

# 方式4: 全局配置
from grid_code.agents import configure_mcp
configure_mcp(transport="sse", server_url="http://localhost:8080/sse")
agent = PydanticAIAgent(reg_id="angui_2024")  # 自动使用 SSE
```

### 架构关系说明

```
CLI (gridcode chat)
    │
    ├─→ MCPConnectionConfig.sse() / .stdio()
    │
    └─→ Agent.__init__(mcp_config=...)
            │
            └─→ MCPConnectionManager (单例)
                    │
                    ├─→ get_claude_sdk_config()    → Claude SDK
                    ├─→ get_pydantic_mcp_server()  → Pydantic AI
                    └─→ get_langgraph_client()     → LangGraph
                            │
                            └─→ GridCodeMCPClient
                                    │
                                    └─→ MCP Server (stdio/sse)
                                            │
                                            └─→ PageStore
```

### 设计决策

1. **单例模式**：MCPConnectionManager 使用单例确保全局配置一致性
2. **框架适配**：每个框架使用独立的适配方法，保持原生特性
3. **SSE 回退**：Claude SDK 不支持 SSE 时自动回退到 stdio，并记录警告
4. **向后兼容**：不传 mcp_config 时使用默认 stdio 配置

### 后续建议

1. 考虑添加连接池复用机制（多 Agent 共享连接）
2. 监控 MCP 连接状态，实现自动重连
3. 添加 MCP 调用超时配置

---

## 2025-12-30 MCP 模式支持与 Makefile 更新

### 会话概述

实现了 CLI 的 MCP 模式支持，允许通过全局 `--mcp` 选项使用 MCP 协议调用工具。同时更新 Makefile 支持便捷切换 local/mcp-stdio/mcp-sse 模式，并修复了 SSE 连接的 502 Bad Gateway 问题。

### 完成的工作

#### 1. CLI MCP 模式支持

添加全局选项支持 MCP 远程调用：

```bash
# stdio 模式（自动启动子进程）
gridcode --mcp list

# SSE 模式（连接外部服务器）
gridcode --mcp --mcp-transport sse --mcp-url http://localhost:8080/sse list
```

新增文件：
- `src/grid_code/mcp/protocol.py` - MCP 模式配置 dataclass
- `src/grid_code/mcp/factory.py` - 工具工厂，根据模式创建本地或远程工具
- `src/grid_code/mcp/adapter.py` - MCP 工具适配器，封装异步 MCP 调用为同步接口

#### 2. Makefile 模式切换支持

新增 MODE 变量实现便捷模式切换：

```makefile
# 可选值: local (默认), mcp-stdio, mcp-sse
MODE ?= local
MCP_URL ?= http://127.0.0.1:8080/sse

ifeq ($(MODE),mcp-stdio)
    MCP_FLAGS := --mcp
else ifeq ($(MODE),mcp-sse)
    MCP_FLAGS := --mcp --mcp-transport sse --mcp-url $(MCP_URL)
else
    MCP_FLAGS :=
endif
```

使用示例：
```bash
make list                        # 本地模式
make list MODE=mcp-stdio         # MCP stdio 模式
make list MODE=mcp-sse           # MCP SSE 模式

# 便捷快捷方式
make list-mcp                    # 等价于 MODE=mcp-stdio
make list-mcp-sse                # 等价于 MODE=mcp-sse
```

更新了 15 个业务命令 target 添加 `$(MCP_FLAGS)` 支持。

#### 3. Server 端口配置修复

修复了 `make serve` 端口参数不生效的问题：

- 问题：FastMCP 需要在构造函数中设置 host/port，而非 run() 方法
- 解决：修改 `create_mcp_server()` 接受 host/port 参数，CLI 端动态创建服务器

修改文件：
- `src/grid_code/mcp/server.py` - create_mcp_server() 添加 host/port 参数
- `src/grid_code/cli.py` - serve 命令动态创建服务器

#### 4. SSE 502 Bad Gateway 修复

修复了 MCP SSE 模式返回 502 错误的问题：

- 根因：httpx 默认 `trust_env=True` 会读取 HTTP_PROXY 环境变量
- 表现：SSE 请求经过代理后返回 502，但 curl 直接请求正常
- 解决：在 `adapter.py` 中添加自定义 httpx 客户端工厂，设置 `trust_env=False`

```python
def _no_proxy_httpx_client_factory(**kwargs) -> httpx.AsyncClient:
    """创建不使用环境代理的 httpx AsyncClient"""
    return httpx.AsyncClient(trust_env=False, **kwargs)

# 使用自定义工厂
transport = await stack.enter_async_context(
    sse_client(self.server_url, httpx_client_factory=_no_proxy_httpx_client_factory)
)
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/mcp/protocol.py` | 新建 - MCP 模式配置 dataclass |
| `src/grid_code/mcp/factory.py` | 新建 - 工具工厂 |
| `src/grid_code/mcp/adapter.py` | 新建 - MCP 工具适配器 + trust_env 修复 |
| `src/grid_code/mcp/server.py` | create_mcp_server() 添加 host/port 参数 |
| `src/grid_code/cli.py` | 添加全局 --mcp 选项，修改 serve 命令 |
| `Makefile` | 添加 MODE/MCP_FLAGS 变量，更新业务命令 |

### 测试结果

- ✅ `make list MODE=mcp-sse` - SSE 模式列出规程正常
- ✅ `make toc MODE=mcp-sse REG_ID=angui_2024` - SSE 模式获取目录正常
- ✅ `make serve PORT=8080` - 服务器正确监听 8080 端口
- ✅ `make list-mcp` - stdio 快捷方式正常

---

## 2024-12-29 MCP工具集扩展与CLI命令实现

### 会话概述

完成了MCP工具集的扩展实现，包括8个新工具的开发、CLI命令接口创建和Makefile更新。

### 完成的工作

#### 1. MCP工具集实现 (8个新工具)

**Phase 1: 核心多跳工具 (P0)**
- `lookup_annotation` - 注释查找（支持"注1"、"方案A"等变体匹配）
- `search_tables` - 表格搜索（按标题或单元格内容搜索）
- `resolve_reference` - 交叉引用解析（解析"见第六章"、"参见表6-2"等）

**Phase 2: 上下文工具 (P1)**
- `search_annotations` - 注释搜索（搜索所有匹配的注释）
- `get_table_by_id` - 获取完整表格（含跨页合并）
- `get_block_with_context` - 获取块上下文

**Phase 3: 发现工具 (P2)**
- `find_similar_content` - 相似内容发现
- `compare_sections` - 章节比较

#### 2. CLI命令接口 (12个新命令)

为所有MCP工具创建了对应的CLI命令，便于直接测试：

| 命令 | 功能 |
|------|------|
| `toc` | 获取规程目录树（增强版，带树状显示） |
| `read-pages` | 读取页面范围 |
| `chapter-structure` | 获取章节结构 |
| `page-info` | 获取页面章节信息 |
| `lookup-annotation` | 注释查找 |
| `search-tables` | 表格搜索 |
| `resolve-reference` | 交叉引用解析 |
| `search-annotations` | 注释搜索 |
| `get-table` | 获取完整表格 |
| `get-block-context` | 获取块上下文 |
| `find-similar` | 相似内容发现 |
| `compare-sections` | 章节比较 |

#### 3. TOC命令显示增强

使用Rich库实现美观的树状显示：
- 层级图标: 📚 (根) → 📖 (章) → 📑 (节) → 📄 (条) → 📝 (款) → • (项)
- 层级颜色: bold cyan → bold green → yellow → white → dim
- 页码显示 (dim cyan)
- Panel边框带标题和副标题
- 选项: `--expand/-e` 展开所有层级, `--level/-l` 最大深度
- 折叠节点指示器 [+N]
- 底部图例说明

#### 4. Makefile更新

添加了所有新CLI命令对应的Make目标：
- 更新.PHONY声明
- 添加MCP Tools CLI节（基础工具、Phase 1-3）
- 更新help说明添加MCP Tools Testing示例

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/mcp/tools.py` | 新增8个工具方法 + ReferenceResolver类 |
| `src/grid_code/mcp/server.py` | 注册8个新MCP工具 |
| `src/grid_code/exceptions.py` | 新增3个异常类 |
| `src/grid_code/agents/prompts.py` | 更新系统提示词 |
| `src/grid_code/cli.py` | 新增12个CLI命令 + 增强toc命令 |
| `Makefile` | 添加新命令对应的Make目标 |

### 测试结果

- ✅ `uv run gridcode --help` - 显示所有新命令
- ✅ `make help` - 显示所有Make目标
- ✅ `uv run gridcode toc angui_2024` - 树状显示正常工作

### 设计文档

详细设计文档保存在: `docs/dev/MCP_TOOLS_DESIGN.md`

### 后续建议

1. 使用实际数据对所有CLI命令进行集成测试
2. 根据测试结果调整工具参数和返回格式
3. 考虑为其他命令（如chapter-structure）也添加美化显示
