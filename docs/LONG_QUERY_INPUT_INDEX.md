# RegReader 文档索引

## 长文本查询输入功能

本功能支持多种方式输入长文本查询，特别适合处理复杂的多行查询和包含特殊字符的内容。

### 📚 文档列表

1. **[长文本查询输入指南](LONG_QUERY_INPUT_GUIDE.md)**
   - 快速开始
   - 三种输入方式详解
   - 特殊字符处理
   - 最佳实践
   - 示例集合

2. **[Makefile API 参考](MAKEFILE_API_REFERENCE.md)**
   - 命令完整参数说明
   - 使用示例
   - 变量参考
   - 组合使用

3. **[故障排除指南](TROUBLESHOOTING.md)**
   - 常见问题解决
   - 调试技巧
   - 获取帮助

### 🚀 快速链接

**基本用法**：
```bash
# 从文件读取
make ask-file QUERY_FILE=queries/my_query.txt AGENT=claude

# 从 stdin 读取
cat queries/my_query.txt | make ask-stdin AGENT=pydantic

# 查看示例
make ask-examples
```

**示例文件**：
- [queries/README.md](../queries/README.md) - 查询文件使用说明
- [queries/example_simple.txt](../queries/example_simple.txt) - 简单示例
- [queries/example_complex.txt](../queries/example_complex.txt) - 复杂示例

### 📖 相关文档

- [项目主文档](../CLAUDE.md)
- [Bash+FS 架构文档](bash-fs-paradiam/)
- [Subagents 架构文档](subagents/)

### 🔧 最近更新

**2024-01-14**：
- ✅ 修复 YAML frontmatter 处理问题
- ✅ 添加 `ask-file` 命令
- ✅ 添加 `ask-stdin` 命令
- ✅ 添加 `ask-examples` 命令
- ✅ 创建完整文档

### 💡 提示

- 使用 `make ask-examples` 查看所有输入方式
- 文件输入方式最适合长查询
- 支持 YAML frontmatter 和特殊字符
- 可以组合使用多个参数
