# 故障排除指南

## 常见问题

### 1. 文件相关错误

#### 错误：文件不存在
```
错误: 文件不存在: queries/my_query.txt
```

**原因**：
- 文件路径错误
- 文件未创建
- 工作目录不正确

**解决方法**：
```bash
# 检查文件是否存在
ls -la queries/my_query.txt

# 使用绝对路径
make ask-file QUERY_FILE=/absolute/path/to/query.txt

# 检查当前目录
pwd
```

#### 错误：查询内容为空
```
错误: 查询内容为空
```

**原因**：
- 文件为空
- 文件编码问题
- 文件权限问题

**解决方法**：
```bash
# 检查文件内容
cat queries/my_query.txt

# 检查文件大小
ls -lh queries/my_query.txt

# 检查文件编码
file queries/my_query.txt
```

### 2. 特殊字符错误

#### 错误：No such option: ---
```
No such option: ---
name: wengui-dc-limit
```

**原因**：
- 使用旧版本 Makefile
- 文件包含 YAML frontmatter

**解决方法**：
```bash
# 更新 Makefile
git pull origin main

# 确认使用正确的命令
make ask-file QUERY_FILE=queries/query.txt  # 正确
# 不要手动构造命令
```

### 3. stdin 输入错误

#### 错误：stdin 输入为空
```
错误: stdin 输入为空
```

**原因**：
- 管道输入失败
- 重定向文件不存在
- 命令执行顺序错误

**解决方法**：
```bash
# 检查管道
cat queries/query.txt | make ask-stdin

# 检查重定向
make ask-stdin < queries/query.txt

# 验证文件内容
cat queries/query.txt
```

### 4. Agent 相关错误

#### 错误：Agent 类型无效
```
Invalid value for '--agent': 'invalid' is not one of 'claude', 'pydantic', 'langgraph'
```

**解决方法**：
```bash
# 使用正确的 Agent 类型
make ask-file QUERY_FILE=queries/query.txt AGENT=claude
make ask-file QUERY_FILE=queries/query.txt AGENT=pydantic
make ask-file QUERY_FILE=queries/query.txt AGENT=langgraph
```

### 5. MCP 相关错误

#### 错误：MCP Server 连接失败
```
Error: Failed to connect to MCP server
```

**原因**：
- MCP Server 未启动
- URL 配置错误
- 网络问题

**解决方法**：
```bash
# 启动 MCP Server
make serve

# 检查 MCP Server 状态
curl http://127.0.0.1:8080/sse

# 使用正确的 URL
MCP_URL=http://127.0.0.1:8080/sse make ask-file QUERY_FILE=queries/query.txt MODE=mcp-sse
```

## 调试技巧

### 1. 使用 dry-run 模式

```bash
# 查看实际执行的命令
make -n ask-file QUERY_FILE=queries/query.txt
```

### 2. 启用详细模式

```bash
# 查看详细输出
make ask-file QUERY_FILE=queries/query.txt AGENT_FLAGS="-v"
```

### 3. 检查变量值

```bash
# 查看 Makefile 变量
make -p | grep "^AGENT"
make -p | grep "^QUERY_FILE"
```

### 4. 测试文件读取

```bash
# 测试文件内容
cat queries/query.txt

# 测试命令替换
echo "$(cat queries/query.txt)"
```

## 获取帮助

### 查看命令帮助

```bash
# 查看所有可用命令
make help

# 查看示例
make ask-examples

# 查看 gridcode CLI 帮助
uv run gridcode ask --help
```

### 查看文档

- [长文本查询输入指南](LONG_QUERY_INPUT_GUIDE.md)
- [Makefile API 参考](MAKEFILE_API_REFERENCE.md)
- [项目文档](../CLAUDE.md)
