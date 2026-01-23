# 编排架构重设计进度报告

## 项目概述

基于 infiAgent 多级智能体编排实现，重新设计 RegReader 的 "-m" 模式运行机制。

## 已完成阶段

### Phase 1: 核心基础设施 ✅

**Phase 1.1: HierarchyManager 实现**
- 文件: `src/regreader/orchestration/hierarchy_manager.py`
- 功能: Agent 调用栈管理、共享上下文、状态持久化
- 状态文件: `coordinator/session_{timestamp}/call_stack.json`, `shared_context.json`

**Phase 1.2: SubagentConfig 更新**
- 文件: `src/regreader/subagents/config.py`
- 添加 5 个 L1 原子化子任务类型:
  - `LOCATE_CHAPTERS` - 定位章节
  - `FETCH_CONTENT` - 获取内容
  - `FIND_TABLES` - 查找表格
  - `RESOLVE_REFERENCES` - 解析引用
  - `SEMANTIC_SEARCH` - 语义搜索
- 更新 `SUBAGENT_CONFIGS` 注册表

### Phase 2: OrchestratorAgent 和框架实现 ✅

**Phase 2.1: OrchestratorAgent 基础实现**
- 文件: `src/regreader/agents/orchestrator_agent.py`
- 核心功能:
  - 继承 `BaseOrchestrator`
  - 集成 `HierarchyManager` 进行 agent 调度
  - 实现 `_ensure_initialized()` - 初始化和注册
  - 实现 `_execute_orchestration()` - 核心编排逻辑
  - 实现 `_plan_subtasks()` - 任务规划（占位符）
  - 实现 `_execute_subtask()` - 子任务执行（占位符）
  - 实现 `_aggregate_results()` - 结果聚合（占位符）

**Phase 2.2.1: Claude SDK Orchestrator**
- 文件: `src/regreader/agents/orchestrated/claude.py`
- 备份: `claude.py.backup`
- 特性:
  - 继承 `OrchestratorAgent`
  - 使用 Claude SDK 作为 LLM 后端
  - 支持 `preset: "claude_code"`
  - 集成 MCP 工具访问

**Phase 2.2.2: Pydantic AI Orchestrator**
- 文件: `src/regreader/agents/orchestrated/pydantic.py`
- 备份: `pydantic.py.backup`
- 特性:
  - 继承 `OrchestratorAgent`
  - 使用 Pydantic AI 作为 LLM 后端
  - 集成 MCP 工具访问

**Phase 2.2.3: LangGraph Orchestrator**
- 文件: `src/regreader/agents/orchestrated/langgraph.py`
- 备份: `langgraph.py.backup`
- 特性:
  - 继承 `OrchestratorAgent`
  - 使用 LangGraph 作为 LLM 后端
  - 集成 MCP 工具访问

### Phase 3: 工具子集模式和父子追踪 ✅

**Phase 3.1: MCPConnectionManager 工具白名单支持**
- 文件: `src/regreader/agents/shared/mcp_connection.py`
- 更新内容:
  - `MCPConnectionConfig` 添加 `allowed_tools` 字段
  - `MCPConnectionManager.get_client()` 传递工具白名单到客户端
  - 添加 `is_tool_allowed()` 方法检查工具权限
  - 添加 `get_allowed_tools()` 方法获取白名单

**Phase 3.2: BaseSubagent 父子追踪支持**
- 文件: `src/regreader/subagents/base.py`
- 更新内容:
  - `__init__` 添加 `hierarchy_manager` 和 `parent_id` 参数
  - 添加 `agent_id` 自动生成（格式: `{type}_{uuid}`）
  - 添加 `register_to_hierarchy()` 方法注册到 HierarchyManager
  - 添加 `unregister_from_hierarchy()` 方法注销
  - 添加 `update_status()` 方法更新状态

**Phase 3.3: RegReaderMCPClient 工具访问控制**
- 文件: `src/regreader/mcp/client.py`
- 更新内容:
  - `__init__` 添加 `allowed_tools` 参数
  - `connect()` 方法应用工具白名单过滤
  - `call_tool()` 方法添加权限检查，抛出 `PermissionError`
  - 添加 `is_tool_allowed()` 方法检查工具权限

### Phase 4: CLI 接口更新 ✅

**Phase 4.1: 移除 --main-agent 标志**
- 文件: `src/regreader/cli.py`
- 更新内容:
  - 从 `ask` 命令移除 `--main-agent` / `-m` 标志
  - 从 `chat` 命令移除 `--main-agent` / `-m` 标志
  - 移除相关的 MainAgent 实例化逻辑

**Phase 4.2: 添加 --mode 选项**
- 文件: `src/regreader/cli.py`
- 更新内容:
  - 添加 `AgentMode` 枚举（standard/orchestrated）
  - 在 `ask` 和 `chat` 命令添加 `--mode` 选项
  - 保留 `--orchestrator` / `-o` 标志用于向后兼容
  - `-o` 标志映射到 `--mode orchestrated`

**Phase 4.3: 废弃 MainAgent 实现**
- 文件: `src/regreader/agents/main/agent.py`
- 更新内容:
  - 添加模块级废弃警告到 docstring
  - 添加类级废弃警告到 MainAgent docstring
  - 在 `__init__()` 添加运行时警告（warnings.warn + logger.warning）
  - 提供迁移指南（旧命令 → 新命令）

### Phase 5: 测试 ✅

**Phase 5.1: HierarchyManager 单元测试**
- 文件: `tests/test_hierarchy_manager.py`
- 测试覆盖:
  - 基础功能: 初始化、会话目录创建
  - Agent 栈管理: push_agent (root/child)、pop_agent
  - 状态更新: update_agent_status（完整/部分更新）
  - 上下文获取: get_agent_context
  - 状态持久化: save_state、load_state
  - 复杂场景: 嵌套层级、顺序执行、跨会话恢复

**Phase 5.2: OrchestratorAgent 单元测试**
- 文件: `tests/test_orchestrator_agent.py`
- 测试覆盖:
  - 初始化: 基础初始化、无 HierarchyManager、agent_id 生成
  - Agent 注册: _ensure_initialized、幂等性
  - 任务规划: 搜索查询、表格查询、引用查询、复杂查询
  - 子任务执行: 返回结果、不同任务类型
  - 结果聚合: 单个结果、多个结果、空结果

## 待完成阶段

### Phase 5.3-5.5: 文档更新 (可选)

**目标**:
1. 更新架构文档（可选，当前进度文档已足够）
2. 创建迁移指南（可选，MainAgent 已包含迁移说明）

**关键文件**:
- `docs/dev/ORCHESTRATION_REDESIGN.md` (可选)
- `docs/dev/MIGRATION_GUIDE.md` (可选)

## 关键设计决策

### 1. 正确理解 L1 子智能体
- **L1 ≠ SEARCH/TABLE/REFERENCE/DISCOVERY 分类**
- **L1 = 原子化子任务功能**（由 Agent Skills 明确描述）
- L1 子智能体接收明确的子任务目标，内部进行规划推理，直接操作 L0 MCP 工具

### 2. 3-Level 架构层级
- **L2**: OrchestratorAgent - 理解用户主任务，组合 L1 原子化功能
- **L1**: 原子化子任务 - 定位章节、获取内容、查找表格、解析引用、语义搜索
- **L0**: MCP 工具 - 16+ 底层数据访问工具

### 3. 向后兼容策略
- **保留**: `-o` / `--orchestrator` 标志（映射到 `--mode orchestrated`）
- **移除**: `-m` / `--main-agent` 标志（已损坏的实现）
- **新增**: `--mode` 选项作为主要接口

### 4. 状态持久化
- 所有 agent 调用都保存到 `coordinator/session_{timestamp}/` 目录
- 支持调试和故障恢复
- JSON 格式的调用栈和共享上下文

## 当前限制和 TODO

### 占位符实现
以下方法当前使用简单规则匹配，需要后续实现 LLM 规划推理：

1. **`OrchestratorAgent._plan_subtasks()`**
   - 当前: 简单关键词匹配
   - TODO: 使用 LLM 进行规划推理

2. **`OrchestratorAgent._execute_subtask()`**
   - 当前: 返回占位符结果
   - TODO: 实际调用 L1 子智能体

3. **`OrchestratorAgent._aggregate_results()`**
   - 当前: 简单字符串拼接
   - TODO: 使用 LLM 进行智能聚合

### 框架特定实现
三个框架的 orchestrator 当前都继承 OrchestratorAgent 的占位符实现，需要后续添加框架特定的 LLM 调用逻辑。

## 验证计划

### 单元测试
```bash
pytest tests/test_hierarchy_manager.py -xvs
pytest tests/test_orchestrator_agent.py -xvs
```

### 集成测试
```bash
# Claude SDK
regreader chat -r angui_2024 --mode orchestrated --agent claude

# Pydantic AI
regreader chat -r angui_2024 --mode orchestrated --agent pydantic

# LangGraph
regreader chat -r angui_2024 --mode orchestrated --agent langgraph
```

### 端到端验证
测试查询: "母线失压如何处理？需要查看相关表格和注释"

预期行为:
1. OrchestratorAgent 分析查询
2. 分解为子任务（搜索内容、查找表格、解析注释）
3. HierarchyManager 追踪 agent 栈
4. 聚合结果并返回

## 时间线

- **2026-01-18 上午**: Phase 1 和 Phase 2 完成
- **2026-01-18 下午**: Phase 3 完成
- **2026-01-18 晚上**: Phase 4 和 Phase 5 完成

## 项目完成总结

### 已完成的核心功能

**1. 基础设施层 (Phase 1)**
- ✅ HierarchyManager: Agent 调用栈管理、共享上下文、状态持久化
- ✅ SubagentConfig: 5 个 L1 原子化子任务类型定义和配置

**2. 编排层 (Phase 2)**
- ✅ OrchestratorAgent: 基础编排智能体实现
- ✅ Claude SDK Orchestrator: 继承 OrchestratorAgent
- ✅ Pydantic AI Orchestrator: 继承 OrchestratorAgent
- ✅ LangGraph Orchestrator: 继承 OrchestratorAgent

**3. 工具访问控制 (Phase 3)**
- ✅ MCPConnectionManager: 工具白名单支持
- ✅ BaseSubagent: 父子追踪和 HierarchyManager 集成
- ✅ RegReaderMCPClient: 工具权限检查和访问控制

**4. CLI 接口 (Phase 4)**
- ✅ 移除损坏的 `--main-agent` / `-m` 标志
- ✅ 添加 `--mode` 选项 (standard/orchestrated)
- ✅ 保留 `-o` 标志用于向后兼容
- ✅ MainAgent 废弃警告和迁移指南

**5. 测试覆盖 (Phase 5)**
- ✅ HierarchyManager 单元测试: 8 个测试类，20+ 测试用例
- ✅ OrchestratorAgent 单元测试: 5 个测试类，15+ 测试用例

### 架构优势

1. **正确的 3-Level 层级**
   - L2 编排智能体: 理解用户主任务，组合 L1 原子化功能
   - L1 原子化子任务: 定位章节、获取内容、查找表格、解析引用、语义搜索
   - L0 MCP 工具: 16+ 底层数据访问工具

2. **强制工具访问控制**
   - 配置层: MCPConnectionConfig.allowed_tools
   - 管理层: MCPConnectionManager 过滤
   - 客户端层: RegReaderMCPClient 权限检查

3. **完整的父子追踪**
   - 自动生成唯一 agent_id
   - HierarchyManager 追踪调用栈
   - JSON 格式状态持久化

4. **向后兼容的 CLI**
   - `-o` 标志继续工作
   - 新的 `--mode` 选项更清晰
   - 废弃的 `-m` 标志有明确迁移路径

## 参考文档

- 完整计划: `/Users/sujiangwen/.claude/plans/sequential-gathering-hejlsberg.md`
- 架构设计: `docs/subagents/SUBAGENTS_ARCHITECTURE.md`
- Bash+FS 架构: `docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md`
