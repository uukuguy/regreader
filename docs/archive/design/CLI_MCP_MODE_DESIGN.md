# RegReader CLI MCP 模式实现设计文档

## 概述

为 RegReader CLI 添加 MCP 访问模式，让所有业务命令都能通过 MCP Server 访问数据，以便全面验证 MCP 功能可用性，支撑后续智能体调用。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI Commands                           │
│                  (typer + asyncio.run for async)                │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    create_tools() 工厂函数                       │
│          (use_mcp, transport, url) → RegReaderToolsProtocol       │
└────────────────────┬───────────────────────┬────────────────────┘
                     │                       │
         use_mcp=False                use_mcp=True
                     │                       │
                     ▼                       ▼
┌────────────────────────────┐   ┌────────────────────────────────┐
│    RegReaderTools           │   │   RegReaderMCPToolsAdapter      │
│    (本地直接访问)           │   │   (MCP 远程调用封装)            │
└────────────────────────────┘   └────────────────────────────────┘
```

## 配置优先级

```
命令行参数 --mcp > 环境变量 REGREADER_USE_MCP > 配置文件 use_mcp_mode > 默认值(False)
```

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/regreader/config.py` | 修改 | 添加 MCP 模式配置项 |
| `src/regreader/mcp/protocol.py` | 新增 | 工具协议接口定义 |
| `src/regreader/mcp/adapter.py` | 新增 | MCP 工具适配器 |
| `src/regreader/mcp/factory.py` | 新增 | 工具工厂函数 |
| `src/regreader/mcp/client.py` | 修改 | 添加 SSE 传输支持 |
| `src/regreader/mcp/__init__.py` | 修改 | 导出新增模块 |
| `src/regreader/cli.py` | 修改 | 添加全局 MCP 选项 |

## 实现步骤

### 阶段 1：基础架构

**1.1 修改 `config.py`** - 添加配置项
```python
use_mcp_mode: bool = Field(default=False, description="默认是否使用 MCP 模式")
mcp_transport: str = Field(default="stdio", description="MCP 传输方式: stdio, sse")
mcp_server_url: str | None = Field(default=None, description="MCP SSE 服务器 URL")
```

**1.2 新增 `mcp/protocol.py`** - 定义协议接口
- 定义 `RegReaderToolsProtocol` Protocol 类
- 包含所有 15 个工具方法签名

**1.3 新增 `mcp/factory.py`** - 工厂函数
- `create_tools(use_mcp, transport, server_url)` → 返回工具实例
- 处理配置优先级逻辑

### 阶段 2：MCP 适配器

**2.1 修改 `mcp/client.py`** - 扩展传输支持
- 添加 SSE 传输方式
- 支持 `transport` 参数选择传输方式

**2.2 新增 `mcp/adapter.py`** - MCP 工具适配器
- 将异步 MCP Client 调用包装为同步接口
- 实现所有 15 个工具方法的 MCP 调用封装

**2.3 更新 `mcp/__init__.py`** - 导出新模块

### 阶段 3：CLI 集成

**3.1 修改 `cli.py`** - 添加全局状态和选项

需要修改的命令（15个）：
- `list` → `tools.list_regulations()`
- `search` → `tools.smart_search()`
- `read-pages` → `tools.read_page_range()`
- `toc` → `tools.get_toc()`
- `read-chapter` → `tools.read_chapter_content()`
- `page-info` → `tools.get_page_chapter_info()`
- `chapter-structure` → `tools.get_chapter_structure()`
- `lookup-annotation` → `tools.lookup_annotation()`
- `search-tables` → `tools.search_tables()`
- `resolve-reference` → `tools.resolve_reference()`
- `search-annotations` → `tools.search_annotations()`
- `get-table` → `tools.get_table_by_id()`
- `get-block-context` → `tools.get_block_with_context()`
- `find-similar` → `tools.find_similar_content()`
- `compare-sections` → `tools.compare_sections()`

不需要修改的命令（管理类）：
- `ingest` - 入库命令，必须本地执行
- `serve` - 启动 MCP Server
- `delete` - 删除规程
- `inspect` - 调试命令
- `chat` - 已通过 MCP 访问
- `build-table-index` - 索引构建

## 使用示例

```bash
# 1. 默认模式（本地直接访问）
regreader search "母线失压" -r angui_2024
regreader toc -r angui_2024

# 2. MCP stdio 模式（自动启动子进程）
regreader --mcp search "母线失压" -r angui_2024
regreader --mcp read-pages -r angui_2024 -s 1 -e 5

# 3. MCP SSE 模式（连接外部服务）
# 终端1: 启动服务
regreader serve --transport sse --port 8080

# 终端2: 使用服务
regreader --mcp --mcp-transport sse --mcp-url http://localhost:8080/sse search "母线失压"

# 4. 环境变量方式
export REGREADER_USE_MCP=1
export REGREADER_MCP_TRANSPORT=stdio
regreader search "母线失压" -r angui_2024
```

## 注意事项

1. **异步/同步兼容**：CLI 是同步的，MCP Client 是异步的，使用 `asyncio.run()` 包装
2. **向后兼容**：默认 `use_mcp=False`，保持原有行为
3. **错误处理**：MCP 调用返回 `{"error": "..."}` 需要转换为合适的错误提示
4. **性能**：stdio 模式每次调用启动子进程有开销，SSE 模式更适合批量操作
