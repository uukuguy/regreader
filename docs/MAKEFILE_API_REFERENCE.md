# Makefile 命令 API 参考

## 概述

本文档提供 GridCode Makefile 命令的完整 API 参考，包括所有参数、选项和使用示例。

## 长文本查询命令

### ask-file

从文件读取查询内容并执行。

**语法**：
```bash
make ask-file QUERY_FILE=<path> [AGENT=<agent>] [REG_ID=<reg>] [AGENT_FLAGS=<flags>] [MODE=<mode>]
```

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `QUERY_FILE` | string | 是 | - | 查询文件路径（相对或绝对） |
| `AGENT` | enum | 否 | `claude` | Agent 类型：`claude`, `pydantic`, `langgraph` |
| `REG_ID` | string | 否 | - | 规程 ID（空值表示自动识别） |
| `AGENT_FLAGS` | string | 否 | - | 额外的 agent 参数（如 `-v`, `-o`, `-q`） |
| `MODE` | enum | 否 | `local` | 运行模式：`local`, `mcp-stdio`, `mcp-sse` |

**返回值**：
- 成功：显示 Agent 回答和来源
- 失败：显示错误信息并退出

**示例**：

```bash
# 基本用法
make ask-file QUERY_FILE=queries/my_query.txt

# 指定 Agent 和规程
make ask-file QUERY_FILE=queries/query.txt AGENT=pydantic REG_ID=angui_2024

# 详细模式
make ask-file QUERY_FILE=queries/query.txt AGENT_FLAGS="-v"

# Orchestrator 模式
make ask-file QUERY_FILE=queries/query.txt AGENT_FLAGS="-o"

# MCP SSE 模式
make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse
```

**错误处理**：

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| `错误: 必须指定 QUERY_FILE 参数` | 未提供 QUERY_FILE | 添加 `QUERY_FILE=path` 参数 |
| `错误: 文件不存在` | 文件路径错误 | 检查文件路径是否正确 |
| `No such option: ---` | 旧版本 Makefile | 更新到最新版本 |

**技术细节**：

命令内部使用 `--` 参数分隔符来处理特殊字符：
```bash
gridcode ask --agent claude -- "$(cat file.txt)"
```

这确保文件内容中的 `---`、`--` 等字符不会被误解析为命令选项。

---

### ask-stdin

从标准输入读取查询内容并执行。

**语法**：
```bash
<input> | make ask-stdin [AGENT=<agent>] [REG_ID=<reg>] [AGENT_FLAGS=<flags>]
make ask-stdin [AGENT=<agent>] [REG_ID=<reg>] < <file>
```

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `AGENT` | enum | 否 | `claude` | Agent 类型 |
| `REG_ID` | string | 否 | - | 规程 ID |
| `AGENT_FLAGS` | string | 否 | - | 额外的 agent 参数 |

**输入**：
- 通过管道：`cat file.txt | make ask-stdin`
- 通过重定向：`make ask-stdin < file.txt`
- 通过 echo：`echo "query" | make ask-stdin`

**返回值**：
- 成功：显示 Agent 回答
- 失败：显示错误信息

**示例**：

```bash
# 管道输入
cat queries/query.txt | make ask-stdin AGENT=claude

# 重定向输入
make ask-stdin AGENT=pydantic REG_ID=angui_2024 < queries/query.txt

# Echo 输入
echo "母线失压如何处理？" | make ask-stdin AGENT=claude

# 组合多个文件
cat part1.txt part2.txt | make ask-stdin AGENT=claude
```

**错误处理**：

| 错误 | 原因 | 解决方法 |
|------|------|----------|
| `错误: stdin 输入为空` | 没有输入内容 | 确认管道或重定向正确 |

---

### ask-examples

显示长文本查询输入方式的使用示例。

**语法**：
```bash
make ask-examples
```

**参数**：无

**返回值**：显示所有输入方式的详细示例

**示例**：

```bash
make ask-examples
```

**输出**：
- 方案 1：从文件读取
- 方案 2：从 stdin 读取
- 方案 3：Here-Document
- 方案 4：直接使用 gridcode CLI

---

## 标准查询命令

### ask

使用命令行参数执行单次查询。

**语法**：
```bash
make ask ASK_QUERY="<query>" [AGENT=<agent>] [REG_ID=<reg>] [AGENT_FLAGS=<flags>]
```

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `ASK_QUERY` | string | 是 | - | 查询内容 |
| `AGENT` | enum | 否 | `claude` | Agent 类型 |
| `REG_ID` | string | 否 | - | 规程 ID |
| `AGENT_FLAGS` | string | 否 | - | 额外参数 |

**示例**：

```bash
# 基本用法
make ask ASK_QUERY="母线失压如何处理？"

# 使用 Here-Document
make ask ASK_QUERY="$(cat <<'EOF'
多行查询内容...
EOF
)" AGENT=claude
```

---

### chat

启动交互式对话。

**语法**：
```bash
make chat [AGENT=<agent>] [REG_ID=<reg>] [AGENT_FLAGS=<flags>]
```

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `AGENT` | enum | 否 | `claude` | Agent 类型 |
| `REG_ID` | string | 否 | - | 规程 ID |
| `AGENT_FLAGS` | string | 否 | - | 额外参数 |

**示例**：

```bash
# 基本用法
make chat AGENT=claude REG_ID=angui_2024

# 详细模式
make chat AGENT=pydantic AGENT_FLAGS="-v"
```

---

## Agent 类型

### 支持的 Agent

| Agent | 说明 | 特点 |
|-------|------|------|
| `claude` | Claude SDK Agent | 使用 Anthropic 官方 SDK，支持 preset |
| `pydantic` | Pydantic AI Agent | 基于 Pydantic AI 框架 |
| `langgraph` | LangGraph Agent | 基于 LangGraph 框架 |

### Agent 标志

| 标志 | 说明 | 示例 |
|------|------|------|
| `-v`, `--verbose` | 详细模式 | `AGENT_FLAGS="-v"` |
| `-q`, `--quiet` | 静默模式 | `AGENT_FLAGS="-q"` |
| `-o`, `--orchestrator` | Orchestrator 模式 | `AGENT_FLAGS="-o"` |
| `-j`, `--json` | JSON 输出 | `AGENT_FLAGS="-j"` |

---

## 运行模式

### MODE 参数

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| `local` | 本地模式（默认） | 直接访问本地数据 |
| `mcp-stdio` | MCP stdio 模式 | 通过 stdio 协议访问 MCP Server |
| `mcp-sse` | MCP SSE 模式 | 通过 SSE 协议访问远程 MCP Server |

### MCP 配置

**环境变量**：
```bash
MCP_URL=http://127.0.0.1:8080/sse  # SSE 模式的 URL
```

**示例**：
```bash
# 使用 MCP SSE 模式
make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse

# 自定义 MCP URL
MCP_URL=http://remote-server:8080/sse make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse
```

---

## 变量参考

### 全局变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT` | `claude` | 默认 Agent 类型 |
| `REG_ID` | - | 默认规程 ID（空值表示自动识别） |
| `ASK_QUERY` | `长南Ⅰ线停运会影响哪些断面的限额？` | 默认查询内容 |
| `QUERY_FILE` | - | 查询文件路径 |
| `AGENT_FLAGS` | - | 额外的 agent 参数 |
| `MODE` | `local` | 运行模式 |
| `MCP_URL` | `http://127.0.0.1:8080/sse` | MCP SSE URL |

### 覆盖变量

可以通过命令行覆盖默认值：

```bash
# 覆盖默认 Agent
make ask AGENT=pydantic ASK_QUERY="查询内容"

# 覆盖默认规程
make chat REG_ID=wengui_2024

# 覆盖 MCP URL
MCP_URL=http://custom-server:8080/sse make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse
```

---

## 组合使用

### 示例 1：详细模式 + Orchestrator

```bash
make ask-file QUERY_FILE=queries/complex_query.txt AGENT=claude AGENT_FLAGS="-v -o"
```

### 示例 2：MCP SSE + JSON 输出

```bash
make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse AGENT_FLAGS="-j"
```

### 示例 3：批量查询

```bash
for file in queries/*.txt; do
  make ask-file QUERY_FILE="$file" AGENT=claude REG_ID=angui_2024
done
```

---

## 调试

### 查看实际执行的命令

使用 `make -n` (dry-run) 查看命令：

```bash
make -n ask-file QUERY_FILE=queries/query.txt
```

### 启用详细模式

```bash
make ask-file QUERY_FILE=queries/query.txt AGENT_FLAGS="-v"
```

### 检查变量值

```bash
make -p | grep "^AGENT"
make -p | grep "^REG_ID"
```
