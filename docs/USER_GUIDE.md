# RegReader 用户指南

本指南面向 RegReader 的最终用户，详细介绍如何使用 RegReader 进行电力安规检索。

## 目录

- [快速开始](#快速开始)
- [安装](#安装)
- [基础使用](#基础使用)
- [高级功能](#高级功能)
- [常见问题](#常见问题)

---

## 快速开始

### 安装 RegReader

```bash
# 基础安装
pip install regreader

# 安装可选索引后端
pip install regreader[tantivy]   # 高性能关键词检索
pip install regreader[whoosh]    # 中文分词支持
pip install regreader[qdrant]    # 生产级向量数据库

# 安装所有可选依赖
pip install regreader[all-indexes]
```

### 配置环境

创建 `.env` 文件配置API密钥：

```bash
# Claude API (推荐)
export REGREADER_ANTHROPIC_API_KEY="your-api-key"

# 或使用 OpenAI API
export REGREADER_OPENAI_API_KEY="your-api-key"

# 或使用本地 Ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0
```

### 导入规程文档

```bash
# 导入单个PDF文档
regreader ingest --file angui_2024.pdf --reg-id angui_2024

# 批量导入目录下的文档
regreader ingest --dir regulations/ --format pdf

# 生成元数据（使用LLM增强）
regreader enrich-metadata angui_2024
```

### 开始检索

```bash
# 方式1：直接查询
regreader ask "母线失压如何处理？" --reg-id angui_2024

# 方式2：交互式对话
regreader chat --reg-id angui_2024 --agent pydantic
```

---

## 安装

### 系统要求

- **Python**: 3.12 或更高版本
- **操作系统**: macOS, Linux, Windows
- **内存**: 至少 4GB RAM（推荐 8GB）
- **存储**: 根据规程文档大小而定（建议至少 10GB 可用空间）

### 安装步骤

#### 1. 基础安装

```bash
pip install regreader
```

这将安装默认配置：
- 关键词索引：SQLite FTS5
- 向量索引：LanceDB
- 嵌入模型：sentence-transformers（BGE-small-zh-v1.5）

#### 2. 可选组件

根据需求安装可选索引后端：

```bash
# Tantivy - 高性能全文检索（推荐生产环境）
pip install regreader[tantivy]

# Whoosh - 纯Python实现，中文分词友好
pip install regreader[whoosh]

# Qdrant - 生产级向量数据库（支持分布式）
pip install regreader[qdrant]

# FlagEmbedding - 更高质量的中文嵌入模型
pip install regreader[flag]
```

#### 3. 开发环境安装

如需参与开发或运行测试：

```bash
git clone https://github.com/your-org/regreader.git
cd regreader
pip install -e ".[dev]"
```

---

## 基础使用

### 文档导入

#### 导入单个PDF

```bash
regreader ingest \
    --file regulations/angui_2024.pdf \
    --reg-id angui_2024
```

**参数说明**:
- `--file`: PDF文档路径
- `--reg-id`: 规程唯一标识（建议格式：`规程名_年份`）

#### 批量导入

```bash
regreader ingest \
    --dir regulations/ \
    --format pdf
```

RegReader 会自动：
1. 解析PDF结构（使用Docling）
2. 提取页面、表格、注释
3. 构建目录树
4. 创建关键词和向量索引

#### 查看导入的规程

```bash
# 列出所有规程
regreader list

# 输出示例：
# ┌─────────────┬───────┬──────────────┐
# │ 规程标识    │ 页数  │ 导入时间     │
# ├─────────────┼───────┼──────────────┤
# │ angui_2024  │ 450   │ 2024-01-15   │
# │ jigui_2023  │ 380   │ 2024-01-14   │
# └─────────────┴───────┴──────────────┘
```

### 检索功能

#### 1. 快速查询

最简单的使用方式：

```bash
regreader ask "母线失压如何处理？" --reg-id angui_2024
```

**输出示例**:
```
母线失压处理方法：

1. 判断故障范围
   - 检查母线电压表指示
   - 确认失压母线编号

2. 应急处理步骤
   - 立即切除失压母线上的负荷
   - 投入备用母线
   - 恢复重要负荷供电

[来源: 安规2024 P85 表6-2]
[来源: 安规2024 P86-87]
```

#### 2. 交互式对话

进入对话模式，支持多轮查询：

```bash
regreader chat --reg-id angui_2024 --agent pydantic
```

**对话示例**:
```
> 母线失压如何处理？
[Agent回答...]

> 需要多长时间恢复？
[Agent回答，带上下文...]

> 有哪些注意事项？
[Agent回答...]

> exit
再见！
```

#### 3. 指定章节范围

缩小检索范围，提高准确性：

```bash
regreader search "母线失压" \
    --reg-id angui_2024 \
    --chapter "第六章" \
    --limit 10
```

#### 4. 指定内容类型

只检索特定类型的内容：

```bash
# 只检索表格
regreader search "故障代码" \
    --reg-id angui_2024 \
    --types table

# 检索文本和表格
regreader search "处理流程" \
    --reg-id angui_2024 \
    --types text,table
```

### 浏览目录

#### 查看规程目录结构

```bash
# 查看3级目录
regreader toc angui_2024 --level 3

# 展开特定章节
regreader toc angui_2024 --level 3 --expand "2.1.4"
```

**输出示例**:
```
安全规程 2024版
├── 第一章 总则 (P1-10)
├── 第二章 电气设备 (P11-50)
│   ├── 2.1 高压设备 (P11-30)
│   │   ├── 2.1.1 断路器 (P11-15)
│   │   ├── 2.1.2 隔离开关 (P16-20)
│   │   └── ...
│   └── 2.2 低压设备 (P31-50)
└── ...
```

### 读取页面内容

```bash
# 读取单页
regreader read-pages --reg-id angui_2024 --start 85 --end 85

# 读取页面范围（自动拼接跨页表格）
regreader read-pages --reg-id angui_2024 --start 85 --end 87
```

---

## 高级功能

### Agent 框架选择

RegReader 提供三种 Agent 实现，各有特点：

#### 1. Claude Agent SDK（推荐用于Claude模型）

**优势**:
- 原生MCP支持，性能最优
- 默认使用 `preset: "claude_code"` 最佳实践
- 上下文管理高效

**使用**:
```bash
# 标准模式
regreader chat-claude --reg-id angui_2024

# 编排器模式（上下文隔离，~800 tokens）
regreader chat-claude-orch --reg-id angui_2024
```

#### 2. Pydantic AI Agent（推荐用于多模型）

**优势**:
- 类型安全
- 支持多种LLM后端（OpenAI, Anthropic, Ollama等）
- 生产就绪

**使用**:
```bash
# 标准模式
regreader chat-pydantic --reg-id angui_2024

# 编排器模式
regreader chat-pydantic-orch --reg-id angui_2024
```

#### 3. LangGraph Agent（推荐用于复杂工作流）

**优势**:
- 复杂工作流编排
- 状态管理
- 可视化调试

**使用**:
```bash
# 标准模式
regreader chat-langgraph --reg-id angui_2024

# 编排器模式
regreader chat-langgraph-orch --reg-id angui_2024
```

### 标准模式 vs 编排器模式

#### 标准模式
- **上下文**: ~4000 tokens（包含所有工具描述）
- **适用**: 简单、单跳查询
- **示例**: "母线失压如何处理？"

```bash
regreader chat --agent pydantic --reg-id angui_2024
```

#### 编排器模式
- **上下文**: ~800 tokens per orchestrator（专用子代理）
- **适用**: 复杂、多跳查询，需要多种工具类型
- **优势**:
  - 上下文隔离，减少token消耗
  - 更好的专注度
  - 支持并行执行

```bash
regreader chat --agent pydantic --reg-id angui_2024 --orchestrator
# 或简写
regreader chat --agent pydantic --reg-id angui_2024 -o
```

**编排器示例查询**:
```
> 对比第2.1.4章节和第2.1.5章节的处理流程差异，并总结关键点

[Orchestrator分析意图]
→ 需要 SearchAgent（章节定位）
→ 需要 ReferenceAgent（交叉对比）

[并行执行]
SearchAgent: 定位2.1.4和2.1.5章节
ReferenceAgent: 提取关键流程步骤

[聚合结果]
提供详细对比...
```

### 长查询输入

对于复杂的多行查询，RegReader 提供多种输入方式：

#### 方式1：从文件读取（推荐）

```bash
# 1. 创建查询文件
cat > queries/complex_query.txt <<'EOF'
请详细说明母线失压的处理流程，包括：
1. 故障判断标准和判断依据
2. 应急处理的详细步骤
3. 恢复操作流程和注意事项
4. 相关表格和参考章节
EOF

# 2. 执行查询
regreader ask "$(cat queries/complex_query.txt)" --reg-id angui_2024

# 或使用 Makefile
make ask-file QUERY_FILE=queries/complex_query.txt AGENT=claude REG=angui_2024
```

#### 方式2：Here-Document（Bash原生）

```bash
regreader ask "$(cat <<'EOF'
请详细说明母线失压的处理流程，包括：
1. 故障判断标准和判断依据
2. 应急处理的详细步骤
3. 恢复操作流程和注意事项
4. 相关表格和参考章节
EOF
)" --reg-id angui_2024
```

#### 方式3：交互式编辑器

```bash
# 打开编辑器输入查询
EDITOR=vim regreader ask-interactive --reg-id angui_2024
```

详细说明请参考：[长查询输入指南](LONG_QUERY_INPUT_GUIDE.md)

### 表格检索

专门针对表格内容的检索：

```bash
# 混合检索（关键词+语义）
regreader search-tables "故障代码对照" \
    --reg-id angui_2024 \
    --mode hybrid \
    --limit 10

# 仅关键词检索
regreader search-tables "110kV" \
    --reg-id angui_2024 \
    --mode keyword

# 仅语义检索
regreader search-tables "电压等级" \
    --reg-id angui_2024 \
    --mode vector
```

### 注释查找

查找文档中的注释内容：

```bash
# 查找指定注释
regreader lookup-annotation \
    --reg-id angui_2024 \
    --annotation "注1" \
    --page 85

# 搜索所有相关注释
regreader search-annotations \
    --reg-id angui_2024 \
    --query "电压等级"
```

### 交叉引用解析

解析"见第X章"类型的引用：

```bash
regreader resolve-reference \
    --reg-id angui_2024 \
    --reference "见第六章"
```

### 多规程检索

跨多个规程进行检索：

```bash
# 检索所有规程
regreader search "母线失压" --all

# 输出示例：
# 找到 3 个规程中的相关内容：
#
# [安规2024] P85-87
# 母线失压处理方法...
#
# [继电保护规程2023] P102
# 母线失压保护动作...
#
# [电网调度规程2024] P45
# 母线失压调度处理...
```

### 本地LLM（Ollama）

使用本地部署的 Ollama 模型：

```bash
# 1. 启动 Ollama 服务
ollama serve

# 2. 下载模型
ollama pull Qwen3-4B-Instruct-2507:Q8_0

# 3. 配置环境变量
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# 4. 使用 RegReader
regreader chat --agent pydantic --reg-id angui_2024
```

**自动检测**: RegReader 会自动检测 Ollama 后端（当 base_url 包含 `:11434` 或 `ollama` 关键词）

### MCP 服务器模式

启动 MCP 服务器供外部客户端使用：

```bash
# stdio 模式（推荐用于 Claude Desktop）
regreader serve --transport stdio

# SSE 模式（用于网页客户端）
regreader serve --transport sse --port 8080
```

### 导出JSON格式结果

```bash
# 导出为JSON
regreader ask "母线失压如何处理？" \
    --reg-id angui_2024 \
    --json > result.json

# JSON 结构
{
  "query": "母线失压如何处理？",
  "content": "...",
  "sources": ["安规2024 P85 表6-2", "安规2024 P86-87"],
  "tool_calls": [...],
  "metadata": {...}
}
```

---

## 常见问题

### Q1: 导入文档时出现解析错误

**A**: Docling 需要较新版本的依赖，请确保：
```bash
pip install --upgrade docling
pip install --upgrade pdf2image
```

如果是OCR问题，请安装 Tesseract：
```bash
# macOS
brew install tesseract tesseract-lang

# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim
```

### Q2: 检索结果不准确

**A**: 尝试以下优化方法：

1. **调整检索权重**:
```bash
export REGREADER_FTS_WEIGHT=0.6
export REGREADER_VECTOR_WEIGHT=0.4
```

2. **指定章节范围**:
```bash
regreader search "查询内容" --reg-id angui_2024 --chapter "第六章"
```

3. **使用编排器模式**（更好的上下文理解）:
```bash
regreader chat --agent pydantic --reg-id angui_2024 --orchestrator
```

### Q3: Agent 响应太慢

**A**:
1. **使用本地 Ollama 模型**（更快，无需网络）
2. **减少 `--limit` 参数**（减少检索结果数量）
3. **切换到 Haiku 模型**（更快但可能牺牲质量）:
```bash
export REGREADER_LLM_MODEL_NAME=claude-haiku-4-20250514
```

### Q4: 内存占用过高

**A**:
1. **切换到更轻量的索引后端**:
```bash
export REGREADER_KEYWORD_INDEX_BACKEND=fts5
export REGREADER_VECTOR_INDEX_BACKEND=lancedb
```

2. **减少嵌入模型维度**:
```bash
export REGREADER_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5  # 512维
```

3. **清理临时文件**:
```bash
rm -rf coordinator/scratch/*
rm -rf subagents/*/scratch/*
```

### Q5: 如何删除已导入的规程

```bash
# 删除单个规程
regreader delete angui_2024

# 清空所有数据
rm -rf data/storage/
```

### Q6: 跨页表格识别不准确

**A**: 这通常是 Docling 解析问题。可以尝试：

1. **检查原始PDF质量**（扫描件需要OCR）
2. **手动标注跨页表格**（高级功能，参见开发者指南）
3. **提交issue**，附上PDF样本供改进

### Q7: 如何更新规程文档

```bash
# 1. 删除旧版本
regreader delete angui_2024

# 2. 重新导入新版本
regreader ingest --file angui_2024_v2.pdf --reg-id angui_2024

# 3. 重新生成元数据
regreader enrich-metadata angui_2024
```

### Q8: 命令行太长，有简化方式吗？

**A**: 使用 Makefile 简化命令：

```bash
# 对话
make chat AGENT=pydantic REG=angui_2024

# 查询
make ask QUERY="母线失压" AGENT=pydantic REG=angui_2024

# 长查询
make ask-file QUERY_FILE=queries/query.txt AGENT=claude REG=angui_2024

# 查看所有命令
make help
```

详见：[Makefile API参考](MAKEFILE_API_REFERENCE.md)

---

## 性能优化建议

### 检索性能

1. **使用 Tantivy 替代 FTS5**（生产环境推荐）:
```bash
pip install regreader[tantivy]
export REGREADER_KEYWORD_INDEX_BACKEND=tantivy
```

2. **启用编排器模式**（减少上下文，提升响应速度）:
```bash
regreader chat --agent pydantic --reg-id angui_2024 -o
```

3. **合理设置检索数量**:
```bash
# 默认 top_k=10，可根据需求调整
export REGREADER_SEARCH_TOP_K=5  # 减少检索结果，提升速度
```

### 存储优化

1. **使用 SSD 存储**（提升 I/O 性能）
2. **定期清理日志文件**:
```bash
find coordinator/logs -mtime +30 -delete
find subagents/*/logs -mtime +30 -delete
```

### Agent 性能

1. **选择合适的 Agent 框架**:
   - 简单查询：Claude SDK（最快）
   - 复杂查询：Pydantic AI + Orchestrator（最优）
   - 工作流：LangGraph（最灵活）

2. **合理使用缓存**:
```bash
export REGREADER_ENABLE_CACHE=true
```

---

## 下一步

- **API 参考**: 参见 [API_REFERENCE.md](API_REFERENCE.md)
- **开发者指南**: 参见 [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- **架构设计**: 参见 [docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md](bash-fs-paradiam/ARCHITECTURE_DESIGN.md)
- **故障排查**: 参见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## 获取帮助

- **GitHub Issues**: https://github.com/your-org/regreader/issues
- **文档**: https://regreader.readthedocs.io
- **社区**: https://discord.gg/regreader
