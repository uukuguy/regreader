# RegReader 开发者指南

本指南面向 RegReader 的开发者和贡献者，介绍如何参与项目开发、扩展功能和贡献代码。

## 目录

- [开发环境设置](#开发环境设置)
- [架构概览](#架构概览)
- [扩展指南](#扩展指南)
- [测试指南](#测试指南)
- [代码规范](#代码规范)
- [贡献流程](#贡献流程)

---

## 开发环境设置

### 克隆仓库

```bash
git clone https://github.com/your-org/regreader.git
cd regreader
```

### 创建虚拟环境

推荐使用 Conda：

```bash
# 创建环境
conda create -n regreader python=3.12
conda activate regreader

# 或使用 venv
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
```

### 安装开发依赖

```bash
# 安装所有依赖（包括可选索引后端）
pip install -e ".[dev,all-indexes]"

# 或使用 Makefile
make install-dev
```

### 运行测试

```bash
# 运行所有测试
pytest -xvs

# 运行 Bash+FS 架构测试
make test-bash-fs

# 生成覆盖率报告
pytest --cov=src/regreader --cov-report=html
```

---

## 架构概览

RegReader 采用 **7层架构**，从下到上依次为：

```
┌─────────────────────────────────────────────────────────────────┐
│                     业务层 (CLI / API)                          │
├─────────────────────────────────────────────────────────────────┤
│                     Agent 框架层                                 │
│           Claude SDK  |  Pydantic AI  |  LangGraph               │
├─────────────────────────────────────────────────────────────────┤
│                     编排层 (Orchestrator)                        │
│   QueryAnalyzer → SubagentRouter → ResultAggregator             │
├─────────────────────────────────────────────────────────────────┤
│                     子代理层 (Domain Experts)                    │
│   RegSearch-Subagent (SEARCH/TABLE/REFERENCE/DISCOVERY)         │
├─────────────────────────────────────────────────────────────────┤
│                     基础设施层                                    │
│   FileContext | SkillLoader | EventBus | SecurityGuard          │
├─────────────────────────────────────────────────────────────────┤
│                     MCP 工具层                                    │
│   16+ tools organized by phase (BASE/MULTI_HOP/CONTEXT/...)     │
├─────────────────────────────────────────────────────────────────┤
│                     存储 & 索引层                                 │
│   PageStore | HybridSearch | FTS5/LanceDB | Embedding           │
└─────────────────────────────────────────────────────────────────┘
```

详细架构设计请参考：[Bash+FS 架构设计](bash-fs-paradiam/ARCHITECTURE_DESIGN.md)

---

## 扩展指南

完整的扩展指南请参考项目 CLAUDE.md 文件中的"架构扩展指南"部分。

主要扩展点：
- 添加新的索引后端
- 添加新的嵌入后端
- 添加新的子代理类型
- 添加新的 MCP 工具
- 添加新的技能

---

## 测试指南

### 运行测试

```bash
# 运行所有测试
pytest -xvs

# 运行特定模块
pytest tests/test_page_store.py -xvs

# 运行 Bash+FS 架构测试
make test-bash-fs

# 生成覆盖率报告
pytest --cov=src/regreader --cov-report=html
```

详细测试指南请参考 tests/ 目录中的测试示例。

---

## 代码规范

### Python 代码风格

遵循 **PEP 8** 和项目特定规范：

- 使用 Python 3.12+ 类型注解语法
- 使用 Google 风格的 docstring
- 通过 black 格式化代码
- 通过 isort 排序导入
- 通过 mypy 类型检查
- 通过 ruff 代码检查

### 代码审查检查清单

- [ ] 所有函数有类型注解
- [ ] 所有公共API有docstring
- [ ] 遵循命名规范
- [ ] 通过代码格式化和检查
- [ ] 有对应的单元测试
- [ ] 测试覆盖率 > 80%

---

## 贡献流程

### 1. Fork 仓库并创建分支

```bash
git checkout -b feature/my-new-feature
```

### 2. 开发和测试

```bash
# 开发功能
# ...

# 运行测试
pytest -xvs

# 格式化代码
make format

# 检查代码
make lint
make typecheck
```

### 3. 提交代码

```bash
git add .
git commit -m "feat: 添加新功能XXX"
```

### 4. 创建 Pull Request

在 GitHub 上创建 Pull Request，描述你的更改。

---

## 延伸阅读

- [API 参考](API_REFERENCE.md)
- [用户指南](USER_GUIDE.md)
- [Bash+FS 架构设计](bash-fs-paradiam/ARCHITECTURE_DESIGN.md)
- [子代理架构](subagents/SUBAGENTS_ARCHITECTURE.md)
- [MCP工具设计](dev/MCP_TOOLS_DESIGN.md)
