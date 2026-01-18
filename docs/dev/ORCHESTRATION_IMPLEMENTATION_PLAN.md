# 编排模式实施计划

## 文档信息

- **创建日期**: 2026-01-18
- **版本**: v1.0
- **预计工期**: 5-7 个工作日

## 实施阶段概览

```
Phase 1: 基础设施完善 (1天)
    ├── Task 1.1: 修复 SSE 异步问题
    ├── Task 1.2: 完善 SubagentConfig
    └── Task 1.3: 实现工具白名单机制

Phase 2: OrchestratorAgent LLM 推理 (2天)
    ├── Task 2.1: 实现 _plan_subtasks_with_llm
    ├── Task 2.2: 实现 _aggregate_results_with_llm
    └── Task 2.3: 三个框架的适配

Phase 3: L1 子智能体实现 (2-3天)
    ├── Task 3.1: LocateChaptersSubagent
    ├── Task 3.2: FetchContentSubagent
    ├── Task 3.3: FindTablesSubagent
    ├── Task 3.4: ResolveReferencesSubagent
    └── Task 3.5: SemanticSearchSubagent

Phase 4: 集成与测试 (1-2天)
    ├── Task 4.1: 端到端集成测试
    ├── Task 4.2: 错误处理和恢复
    └── Task 4.3: 性能优化

Phase 5: 文档与交付 (0.5天)
    ├── Task 5.1: 更新用户文档
    ├── Task 5.2: 更新 WORK_LOG
    └── Task 5.3: 创建示例和教程
```

---

## Phase 1: 基础设施完善

### Task 1.1: 修复 SSE 异步问题

**优先级**: 🔴 高

**问题描述**:
```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

**实施步骤**:
1. 分析 `mcp/client/sse.py` 中的异步上下文管理
2. 确保 TaskGroup 在同一个 task 中进入和退出
3. 修改 `MCPConnectionManager.close()` 方法
4. 测试 SSE 模式的连接和断开

**验证标准**:
- ✅ SSE 模式可以正常连接和断开
- ✅ 不再出现 TaskGroup 错误
- ✅ 多次连接/断开不会泄漏资源

**预计时间**: 2-3 小时

---

### Task 1.2: 完善 SubagentConfig

**优先级**: 🔴 高

**实施步骤**:
1. 创建 5 个 L1 子智能体的配置对象
2. 定义每个子智能体的工具白名单
3. 添加配置到 `SUBAGENT_CONFIGS` 字典
4. 更新 `get_config()` 函数

**配置示例**:
```python
LOCATE_CHAPTERS_CONFIG = SubagentConfig(
    name="locate_chapters",
    description="从规程目录中定位相关章节",
    subagent_type=SubagentType.LOCATE_CHAPTERS,
    available_tools=["get_toc", "get_chapter_structure"],
    system_prompt="你是一个章节定位专家...",
)
```

**验证标准**:
- ✅ 所有 5 个配置对象已创建
- ✅ `get_config()` 可以正确返回配置
- ✅ 不再出现 "config not found" 警告

**预计时间**: 1-2 小时

---

### Task 1.3: 实现工具白名单机制

**优先级**: 🟡 中

**实施步骤**:
1. 在 `MCPConnectionManager` 中实现工具过滤
2. 在创建子智能体时传递工具白名单
3. 在 MCP 客户端中验证工具访问权限
4. 添加工具访问日志

**实现位置**:
- `src/regreader/agents/shared/mcp_connection.py`
- `src/regreader/mcp/client.py`

**验证标准**:
- ✅ 子智能体只能访问白名单中的工具
- ✅ 访问非白名单工具时抛出异常
- ✅ 工具访问被正确记录

**预计时间**: 2-3 小时


---

## Phase 2: OrchestratorAgent LLM 推理

### Task 2.1: 实现 _plan_subtasks_with_llm

**优先级**: 🔴 高

**实施步骤**:
1. 设计规划 prompt 模板
2. 实现 LLM 调用逻辑
3. 解析 LLM 返回的 JSON 结果
4. 添加错误处理和重试机制

**实现位置**:
- `src/regreader/agents/orchestrator_agent.py`

**Prompt 模板**:
```python
PLANNING_PROMPT = """
你是一个任务规划专家。用户提出了关于电力系统安全规程的查询。

可用的子任务类型：
{available_subagents}

用户查询：{query}
规程ID：{reg_id}

请分析查询，确定需要执行哪些子任务。
返回 JSON 格式：[{{"type": "...", "params": {{...}}, "reason": "..."}}]
"""
```

**验证标准**:
- ✅ LLM 可以正确分析查询
- ✅ 返回的子任务列表合理
- ✅ JSON 解析成功率 > 95%

**预计时间**: 4-5 小时

---

### Task 2.2: 实现 _aggregate_results_with_llm

**优先级**: 🔴 高

**实施步骤**:
1. 设计聚合 prompt 模板
2. 实现结果格式化逻辑
3. 实现 LLM 调用和响应处理
4. 添加引用来源的格式化

**实现位置**:
- `src/regreader/agents/orchestrator_agent.py`

**Prompt 模板**:
```python
AGGREGATION_PROMPT = """
你是一个信息聚合专家。多个子任务已完成，请综合结果回答用户问题。

用户查询：{query}

子任务结果：
{subtask_results}

要求：
1. 直接回答用户问题
2. 引用具体章节和页码
3. 保持专业性和准确性
"""
```

**验证标准**:
- ✅ 聚合结果完整准确
- ✅ 包含正确的引用来源
- ✅ 回答格式清晰易读

**预计时间**: 3-4 小时

---

### Task 2.3: 三个框架的适配

**优先级**: 🟡 中

**实施步骤**:
1. 实现 Claude SDK 版本的 LLM 调用
2. 实现 Pydantic AI 版本的 LLM 调用
3. 实现 LangGraph 版本的 LLM 调用
4. 统一接口和错误处理

**实现位置**:
- `src/regreader/agents/orchestrated/claude.py`
- `src/regreader/agents/orchestrated/pydantic.py`
- `src/regreader/agents/orchestrated/langgraph.py`

**验证标准**:
- ✅ 三个框架都能正确调用 LLM
- ✅ 接口统一，行为一致
- ✅ 错误处理完善

**预计时间**: 4-6 小时


---

## Phase 3: L1 子智能体实现

### Task 3.1: LocateChaptersSubagent

**优先级**: 🔴 高

**实施步骤**:
1. 创建 `src/regreader/agents/subagents/locate_chapters.py`
2. 实现 `BaseL1Subagent` 接口
3. 实现章节定位逻辑
4. 添加单元测试

**核心逻辑**:
```python
class LocateChaptersSubagent(BaseL1Subagent):
    async def execute(self, context: SubagentContext) -> SubagentResult:
        # 1. 调用 get_toc 获取目录
        toc = await self.call_tool("get_toc", reg_id=context.reg_id)
        
        # 2. 使用 LLM 分析目录，匹配相关章节
        chapters = await self._analyze_toc_with_llm(toc, context.query)
        
        # 3. 返回结果
        return SubagentResult(
            content=f"找到相关章节：{chapters}",
            sources=[f"{context.reg_id}:toc"],
            tool_calls=self.tool_calls,
            metadata={"chapters": chapters}
        )
```

**验证标准**:
- ✅ 可以正确调用 get_toc 工具
- ✅ LLM 分析准确率 > 90%
- ✅ 单元测试通过

**预计时间**: 3-4 小时

---

### Task 3.2: FetchContentSubagent

**优先级**: 🔴 高

**实施步骤**:
1. 创建 `src/regreader/agents/subagents/fetch_content.py`
2. 实现内容获取逻辑
3. 处理跨页内容
4. 添加单元测试

**核心逻辑**:
```python
class FetchContentSubagent(BaseL1Subagent):
    async def execute(self, context: SubagentContext) -> SubagentResult:
        chapters = context.hints.get("chapters", [])
        contents = []
        
        for chapter in chapters:
            content = await self.call_tool(
                "read_chapter_content",
                reg_id=context.reg_id,
                section_number=chapter
            )
            contents.append(content)
        
        return SubagentResult(
            content="\n\n".join(contents),
            sources=self._extract_sources(contents),
            tool_calls=self.tool_calls,
            metadata={"chapters": chapters}
        )
```

**验证标准**:
- ✅ 可以获取完整章节内容
- ✅ 正确处理跨页内容
- ✅ 单元测试通过

**预计时间**: 3-4 小时


---

### Task 3.3: FindTablesSubagent

**优先级**: 🟡 中

**实施步骤**:
1. 创建 `src/regreader/agents/subagents/find_tables.py`
2. 实现表格搜索逻辑
3. 实现表格内容提取
4. 添加单元测试

**预计时间**: 3-4 小时

---

### Task 3.4: ResolveReferencesSubagent

**优先级**: 🟡 中

**实施步骤**:
1. 创建 `src/regreader/agents/subagents/resolve_references.py`
2. 实现引用类型识别
3. 实现引用解析逻辑
4. 添加单元测试

**预计时间**: 3-4 小时

---

### Task 3.5: SemanticSearchSubagent

**优先级**: 🟡 中

**实施步骤**:
1. 创建 `src/regreader/agents/subagents/semantic_search.py`
2. 实现语义搜索逻辑
3. 实现结果排序和过滤
4. 添加单元测试

**预计时间**: 2-3 小时


---

## Phase 4: 集成与测试

### Task 4.1: 端到端集成测试

**优先级**: 🔴 高

**实施步骤**:
1. 创建集成测试用例
2. 测试完整的查询流程
3. 验证结果准确性
4. 性能基准测试

**测试用例**:
```python
# 测试用例 1: 简单查询
query = "母线失压如何处理？"
expected_chapters = ["6", "6.1"]

# 测试用例 2: 复杂查询（需要多个子任务）
query = "锦苏直流系统发生闭锁故障时，安控装置的动作逻辑是什么？"
expected_subtasks = ["locate_chapters", "fetch_content", "find_tables"]

# 测试用例 3: 引用解析
query = "注1的内容是什么？"
expected_subtasks = ["resolve_references"]
```

**验证标准**:
- ✅ 所有测试用例通过
- ✅ 结果准确率 > 90%
- ✅ 平均响应时间 < 30秒

**预计时间**: 4-6 小时

---

### Task 4.2: 错误处理和恢复

**优先级**: 🟡 中

**实施步骤**:
1. 添加子任务失败处理
2. 实现重试机制
3. 添加降级策略
4. 完善错误日志

**错误场景**:
- MCP 工具调用失败
- LLM 返回格式错误
- 子智能体超时
- 网络连接中断

**验证标准**:
- ✅ 错误被正确捕获和记录
- ✅ 重试机制有效
- ✅ 降级策略合理

**预计时间**: 3-4 小时

---

### Task 4.3: 性能优化

**优先级**: 🟢 低

**实施步骤**:
1. 分析性能瓶颈
2. 优化 LLM 调用次数
3. 实现并行执行
4. 添加缓存机制

**优化目标**:
- 减少 LLM 调用次数 30%
- 支持子任务并行执行
- 添加结果缓存

**预计时间**: 4-6 小时


---

## Phase 5: 文档与交付

### Task 5.1: 更新用户文档

**优先级**: 🟡 中

**实施步骤**:
1. 更新 `CLAUDE.md` 中的编排模式说明
2. 更新 CLI 使用文档
3. 添加编排模式示例
4. 更新 API 文档

**文档内容**:
- 编排模式的工作原理
- 使用方法和参数说明
- 常见问题和解决方案
- 性能对比和最佳实践

**预计时间**: 2-3 小时

---

### Task 5.2: 更新 WORK_LOG

**优先级**: 🟡 中

**实施步骤**:
1. 记录所有实现的功能
2. 记录遇到的问题和解决方案
3. 记录性能数据
4. 记录后续优化建议

**预计时间**: 1 小时

---

### Task 5.3: 创建示例和教程

**优先级**: 🟢 低

**实施步骤**:
1. 创建基础使用示例
2. 创建高级使用示例
3. 创建故障排查指南
4. 创建性能调优指南

**预计时间**: 2-3 小时


---

## 实施优先级排序

### 关键路径（必须完成）

1. **Task 1.2**: 完善 SubagentConfig（前置依赖）
2. **Task 2.1**: 实现 _plan_subtasks_with_llm（核心功能）
3. **Task 2.2**: 实现 _aggregate_results_with_llm（核心功能）
4. **Task 3.1**: LocateChaptersSubagent（最常用）
5. **Task 3.2**: FetchContentSubagent（最常用）
6. **Task 4.1**: 端到端集成测试（验证）

### 次要任务（可延后）

- Task 1.1: 修复 SSE 异步问题（可先用 stdio 模式）
- Task 1.3: 工具白名单机制（可先不限制）
- Task 3.3-3.5: 其他 L1 子智能体（按需实现）
- Task 4.2-4.3: 错误处理和性能优化（后期优化）

### 可选任务（时间允许）

- Task 2.3: 三个框架的适配（可先只实现 Claude SDK）
- Task 5.1-5.3: 文档和示例（可后补）


---

## 任务清单（Checklist）

### Phase 1: 基础设施完善

- [ ] Task 1.1: 修复 SSE 异步问题
  - [ ] 分析 TaskGroup 错误原因
  - [ ] 修改异步上下文管理
  - [ ] 测试 SSE 连接/断开
  - [ ] 验证无资源泄漏

- [ ] Task 1.2: 完善 SubagentConfig
  - [ ] 创建 LOCATE_CHAPTERS_CONFIG
  - [ ] 创建 FETCH_CONTENT_CONFIG
  - [ ] 创建 FIND_TABLES_CONFIG
  - [ ] 创建 RESOLVE_REFERENCES_CONFIG
  - [ ] 创建 SEMANTIC_SEARCH_CONFIG
  - [ ] 更新 SUBAGENT_CONFIGS 字典
  - [ ] 测试 get_config() 函数

- [ ] Task 1.3: 实现工具白名单机制
  - [ ] 在 MCPConnectionManager 中实现过滤
  - [ ] 在子智能体创建时传递白名单
  - [ ] 在 MCP 客户端中验证权限
  - [ ] 添加工具访问日志
  - [ ] 测试白名单限制

### Phase 2: OrchestratorAgent LLM 推理

- [ ] Task 2.1: 实现 _plan_subtasks_with_llm
  - [ ] 设计规划 prompt 模板
  - [ ] 实现 LLM 调用逻辑
  - [ ] 实现 JSON 解析
  - [ ] 添加错误处理和重试
  - [ ] 测试规划准确性

- [ ] Task 2.2: 实现 _aggregate_results_with_llm
  - [ ] 设计聚合 prompt 模板
  - [ ] 实现结果格式化
  - [ ] 实现 LLM 调用
  - [ ] 添加引用来源格式化
  - [ ] 测试聚合质量

- [ ] Task 2.3: 三个框架的适配
  - [ ] 实现 Claude SDK 版本
  - [ ] 实现 Pydantic AI 版本
  - [ ] 实现 LangGraph 版本
  - [ ] 统一接口和错误处理
  - [ ] 测试三个框架


### Phase 3: L1 子智能体实现

- [ ] Task 3.1: LocateChaptersSubagent
  - [ ] 创建文件和基础结构
  - [ ] 实现 execute() 方法
  - [ ] 实现 LLM 目录分析
  - [ ] 添加单元测试
  - [ ] 集成测试

- [ ] Task 3.2: FetchContentSubagent
  - [ ] 创建文件和基础结构
  - [ ] 实现内容获取逻辑
  - [ ] 处理跨页内容
  - [ ] 添加单元测试
  - [ ] 集成测试

- [ ] Task 3.3: FindTablesSubagent
  - [ ] 创建文件和基础结构
  - [ ] 实现表格搜索
  - [ ] 实现表格提取
  - [ ] 添加单元测试
  - [ ] 集成测试

- [ ] Task 3.4: ResolveReferencesSubagent
  - [ ] 创建文件和基础结构
  - [ ] 实现引用识别
  - [ ] 实现引用解析
  - [ ] 添加单元测试
  - [ ] 集成测试

- [ ] Task 3.5: SemanticSearchSubagent
  - [ ] 创建文件和基础结构
  - [ ] 实现语义搜索
  - [ ] 实现结果排序
  - [ ] 添加单元测试
  - [ ] 集成测试


### Phase 4: 集成与测试

- [ ] Task 4.1: 端到端集成测试
  - [ ] 创建测试用例
  - [ ] 测试简单查询
  - [ ] 测试复杂查询
  - [ ] 测试引用解析
  - [ ] 性能基准测试
  - [ ] 验证结果准确性

- [ ] Task 4.2: 错误处理和恢复
  - [ ] 添加子任务失败处理
  - [ ] 实现重试机制
  - [ ] 添加降级策略
  - [ ] 完善错误日志
  - [ ] 测试错误场景

- [ ] Task 4.3: 性能优化
  - [ ] 分析性能瓶颈
  - [ ] 优化 LLM 调用
  - [ ] 实现并行执行
  - [ ] 添加缓存机制
  - [ ] 性能对比测试

### Phase 5: 文档与交付

- [ ] Task 5.1: 更新用户文档
  - [ ] 更新 CLAUDE.md
  - [ ] 更新 CLI 文档
  - [ ] 添加使用示例
  - [ ] 更新 API 文档

- [ ] Task 5.2: 更新 WORK_LOG
  - [ ] 记录实现功能
  - [ ] 记录问题和解决方案
  - [ ] 记录性能数据
  - [ ] 记录优化建议

- [ ] Task 5.3: 创建示例和教程
  - [ ] 基础使用示例
  - [ ] 高级使用示例
  - [ ] 故障排查指南
  - [ ] 性能调优指南

---

## 风险和依赖

### 技术风险

1. **LLM 推理准确性**: LLM 可能无法准确规划子任务
   - **缓解措施**: 设计清晰的 prompt，添加示例，实现重试机制

2. **异步上下文管理**: SSE 客户端的 TaskGroup 错误
   - **缓解措施**: 先使用 stdio 模式，后续修复 SSE

3. **工具调用失败**: MCP 工具可能失败或超时
   - **缓解措施**: 添加重试机制，实现降级策略

### 依赖关系

- Task 2.1 依赖 Task 1.2（需要 SubagentConfig）
- Task 3.x 依赖 Task 1.2（需要配置）
- Task 4.1 依赖 Task 2.x 和 Task 3.x（需要完整功能）

---

## 成功标准

### 功能完整性

- ✅ OrchestratorAgent 可以正确规划子任务
- ✅ 至少实现 2 个 L1 子智能体（LocateChapters + FetchContent）
- ✅ 可以完成端到端查询流程
- ✅ 结果准确率 > 85%

### 性能指标

- ✅ 平均响应时间 < 30秒
- ✅ LLM 调用次数 < 5次/查询
- ✅ 工具调用成功率 > 95%

### 代码质量

- ✅ 单元测试覆盖率 > 80%
- ✅ 集成测试通过率 100%
- ✅ 代码符合项目规范
- ✅ 文档完整清晰

