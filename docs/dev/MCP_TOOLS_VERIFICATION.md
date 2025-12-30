# MCP 服务验证功能文档

## 功能概述

`mcp-tools` 命令增强版，支持实时连接 MCP Server 获取工具列表并验证服务完整性。

## 命令用法

### 静态模式（原有功能）

```bash
# 列出所有工具（静态元数据）
gridcode mcp-tools

# 按分类过滤
gridcode mcp-tools -c base

# 显示详细信息
gridcode mcp-tools -v

# 仅列出分类
gridcode mcp-tools --list-categories
```

### 实时模式（新增功能）

```bash
# 连接 stdio 模式 MCP Server（自动启动子进程）
gridcode mcp-tools --live

# 连接外部 SSE 服务
gridcode mcp-tools --live --sse http://localhost:8080/sse

# 验证服务完整性（名称 + 参数签名）
gridcode mcp-tools --live --verify

# 详细验证（显示所有工具状态）
gridcode mcp-tools --live --verify -v
```

## 参数说明

| 参数 | 简写 | 说明 |
|------|------|------|
| `--category` | `-c` | 按分类过滤: base, multi-hop, context, discovery, navigation |
| `--verbose` | `-v` | 显示详细信息（含工具链） |
| `--list-categories` | - | 仅列出分类 |
| `--live` | `-l` | 实时连接 MCP Server 获取工具列表 |
| `--sse` | - | SSE 服务器 URL（默认使用 stdio 模式） |
| `--verify` | - | 验证服务完整性（对比静态元数据） |

## 验证内容

验证模式会检查以下内容：

1. **服务连接** - MCP Server 是否可以正常连接
2. **工具数量** - 实际工具数量与预期是否一致
3. **工具名称** - 所有预期工具是否都存在
4. **参数签名** - 每个工具的参数列表是否匹配

## 输出示例

### 验证通过

```
正在连接 MCP Server (stdio)...
连接成功！

MCP 服务验证报告
========================================

✓ 服务连接: 成功
✓ 工具数量: 16/16 (100%)
✓ 参数签名: 全部匹配

验证结果: ✓ 通过
```

### 验证失败（工具缺失）

```
MCP 服务验证报告
========================================

✓ 服务连接: 成功
✗ 工具数量: 14/16 (87.5%)
✓ 参数签名: 全部匹配

工具验证详情:
  ✓ get_toc                   - 存在，参数匹配 (1/1)
  ✗ smart_search              - 缺失
  ✓ read_page_range           - 存在，参数匹配 (3/3)
  ...

验证结果: ✗ 失败 (缺失工具: smart_search, compare_sections)
```

### 验证失败（参数不匹配）

```
MCP 服务验证报告
========================================

✓ 服务连接: 成功
✓ 工具数量: 16/16 (100%)
✗ 参数签名: 2 个工具参数不匹配

工具验证详情:
  ✓ get_toc                   - 存在，参数匹配 (1/1)
  ✗ smart_search              - 参数不匹配
      缺少: section_number
      多余: scope
  ...

验证结果: ✗ 失败 (参数不匹配: smart_search)
```

## 元数据定义

工具参数定义位于 `src/grid_code/mcp/tool_metadata.py` 的 `expected_params` 字段：

```python
TOOL_METADATA = {
    "get_toc": ToolMetadata(
        name="get_toc",
        brief="获取规程目录树",
        category=ToolCategory.BASE,
        ...,
        expected_params={"reg_id": "string"},
    ),
    "smart_search": ToolMetadata(
        name="smart_search",
        brief="混合检索",
        category=ToolCategory.BASE,
        ...,
        expected_params={
            "query": "string",
            "reg_id": "string",
            "chapter_scope": "string|null",
            "limit": "integer",
            "block_types": "array|null",
            "section_number": "string|null",
        },
    ),
    ...
}
```

## 适用场景

1. **开发调试** - 验证 MCP Server 工具注册是否正确
2. **CI/CD 集成** - 在部署前自动验证服务完整性
3. **问题排查** - 快速定位工具缺失或参数变更问题
4. **版本升级** - 验证升级后工具兼容性

## 依赖说明

- stdio 模式会自动启动 `gridcode serve --transport stdio` 子进程
- SSE 模式需要先手动启动 `gridcode serve --transport sse`

## 故障排除

### SSE 连接返回 502 Bad Gateway

**症状**：使用 `--sse` 参数连接时返回 502 错误，但服务器已正常启动。

**原因**：系统代理（如 ClashX、V2Ray 等）拦截了 HTTP 请求。httpx 默认读取系统代理设置，导致请求被转发到代理服务器而非本地 MCP 服务。

**解决方案**：
1. MCP 客户端已内置修复，使用自定义 httpx 客户端禁用代理
2. 如仍有问题，可临时关闭系统代理
3. 或在代理规则中添加 `localhost` 直连规则

**技术细节**：
- `src/grid_code/mcp/client.py` 中的 `_connect_sse()` 方法使用 `httpx.AsyncClient(proxy=None, trust_env=False)` 绑定连接
- 这确保 SSE 连接不会被系统代理干扰

## Makefile 命令

```makefile
# 验证 MCP 服务（stdio 模式）
make mcp-verify

# 验证 MCP 服务（SSE 模式，需先启动服务）
make mcp-verify-sse
```
