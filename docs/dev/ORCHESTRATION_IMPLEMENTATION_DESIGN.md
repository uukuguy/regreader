# 编排模式完整实现设计文档

## 文档信息

- **创建日期**: 2026-01-18
- **版本**: v1.0
- **状态**: 设计阶段

## 1. 概述

### 1.1 目标

完整实现 RegReader 的编排模式（Orchestration Mode），基于 infiAgent 的多智能体编排架构，实现三层智能体架构：

- **L2 编排智能体（OrchestratorAgent）**: 理解用户主任务，规划并组合 L1 原子化功能
- **L1 原子化子智能体**: 执行具体的原子化子任务（定位章节、获取内容、查找表格等）
- **L0 MCP 工具**: 底层数据访问工具（16+ 工具）

### 1.2 当前状态

**已完成**:
- ✅ 架构设计和框架代码（Phase 1-5）
- ✅ HierarchyManager（agent 调用栈管理）
- ✅ OrchestratorAgent 基类（占位符实现）
- ✅ SubagentConfig 系统
- ✅ 三个框架的编排器骨架（Claude/Pydantic/LangGraph）
- ✅ Bug 修复（6个关键错误）

**未完成**:
- ❌ OrchestratorAgent 的 LLM 规划推理
- ❌ L1 原子化子智能体实现（5个）
- ❌ 子智能体与 MCP 工具的集成
- ❌ SSE 客户端异步问题修复
- ❌ 端到端集成测试

### 1.3 设计原则

1. **渐进式实现**: 先实现核心功能，再优化性能
2. **框架无关**: 支持三个框架（Claude SDK/Pydantic AI/LangGraph）
3. **工具白名单**: L1 子智能体只能访问指定的 MCP 工具
4. **状态持久化**: 所有 agent 状态保存到文件系统
5. **错误恢复**: 支持从失败状态恢复

## 2. 架构设计

### 2.1 三层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   L2 编排智能体层                                │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  OrchestratorAgent                                       │   │
│  │  - 理解用户主任务                                         │   │
│  │  - LLM 规划推理（_plan_subtasks）                        │   │
│  │  - 调度 L1 子智能体（_execute_subtask）                  │   │
│  │  - 智能聚合结果（_aggregate_results）                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   L1 原子化子智能体层                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  LocateChaptersSubagent (定位章节)                       │   │
│  │  - 工具白名单: get_toc, get_chapter_structure            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FetchContentSubagent (获取内容)                         │   │
│  │  - 工具白名单: read_chapter_content, read_page_range     │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FindTablesSubagent (查找表格)                           │   │
│  │  - 工具白名单: search_tables, get_table_by_id            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ResolveReferencesSubagent (解析引用)                    │   │
│  │  - 工具白名单: resolve_reference, lookup_annotation      │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SemanticSearchSubagent (语义搜索)                       │   │
│  │  - 工具白名单: smart_search, find_similar_content        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   L0 MCP 工具层                                  │
│  16+ 底层工具: get_toc, smart_search, read_page_range,          │
│  search_tables, lookup_annotation, resolve_reference, etc.      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 OrchestratorAgent（L2）

**职责**:
- 理解用户主任务的意图
- 使用 LLM 进行规划推理，确定需要哪些 L1 子任务
- 调度 L1 子智能体执行子任务
- 使用 LLM 聚合子任务结果，生成最终回答

**关键方法**:
```python
async def _execute_orchestration(query: str, context_info: str) -> str:
    """执行编排逻辑"""
    # 1. LLM 规划推理
    subtasks = await self._plan_subtasks_with_llm(query, context_info)

    # 2. 调度 L1 子智能体
    subtask_results = []
    for subtask in subtasks:
        result = await self._execute_subtask(subtask)
        subtask_results.append(result)

    # 3. LLM 智能聚合
    final_answer = await self._aggregate_results_with_llm(subtask_results, query)

    return final_answer
```

#### 2.2.2 L1 原子化子智能体

每个 L1 子智能体都是一个独立的智能体，具有：
- **明确的功能定义**: 由 SubagentConfig 描述
- **工具白名单**: 只能访问指定的 MCP 工具
- **内部规划推理**: 决定如何使用工具完成子任务
- **结构化输出**: 返回 SubagentResult

**通用接口**:
```python
class BaseL1Subagent:
    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行子任务"""
        pass
```


## 3. L1 原子化子智能体详细设计

### 3.1 LocateChaptersSubagent（定位章节）

**功能**: 从规程目录中定位与用户任务相关的章节

**输入**:
- `query`: 用户查询关键词
- `reg_id`: 规程ID

**工具白名单**:
- `get_toc`: 获取目录树
- `get_chapter_structure`: 获取章节结构

**输出**:
```python
SubagentResult(
    content="找到相关章节：第六章 母线失压处理",
    sources=["angui_2024:toc"],
    tool_calls=[{"tool": "get_toc", "args": {...}}],
    metadata={"chapters": ["6", "6.1", "6.2"]}
)
```

**实现策略**:
1. 调用 `get_toc` 获取完整目录
2. 使用 LLM 分析目录，匹配相关章节
3. 返回章节编号列表

---

### 3.2 FetchContentSubagent（获取内容）

**功能**: 获取指定章节的完整内容

**输入**:
- `chapter_numbers`: 章节编号列表（如 ["6", "6.1"]）
- `reg_id`: 规程ID

**工具白名单**:
- `read_chapter_content`: 读取章节内容
- `read_page_range`: 读取页面范围
- `get_block_with_context`: 获取带上下文的内容块

**输出**:
```python
SubagentResult(
    content="第六章内容：...",
    sources=["angui_2024:page_45", "angui_2024:page_46"],
    tool_calls=[{"tool": "read_chapter_content", "args": {...}}],
    metadata={"pages": [45, 46, 47]}
)
```

**实现策略**:
1. 对每个章节调用 `read_chapter_content`
2. 如果内容过长，使用 `read_page_range` 分段获取
3. 合并所有章节内容

---

### 3.3 FindTablesSubagent（查找表格）

**功能**: 查找并提取相关表格数据

**输入**:
- `query`: 查询关键词
- `reg_id`: 规程ID
- `chapter_scope`: 可选的章节范围

**工具白名单**:
- `search_tables`: 搜索表格
- `get_table_by_id`: 获取表格详情
- `smart_search`: 语义搜索（table 模式）

**输出**:
```python
SubagentResult(
    content="找到相关表格：表6-1 母线失压处理流程",
    sources=["angui_2024:table_001"],
    tool_calls=[{"tool": "search_tables", "args": {...}}],
    metadata={"table_ids": ["table_001"], "table_pages": [46]}
)
```

**实现策略**:
1. 调用 `search_tables` 搜索相关表格
2. 对每个表格调用 `get_table_by_id` 获取详情
3. 返回表格内容和位置信息

---

### 3.4 ResolveReferencesSubagent（解析引用）

**功能**: 解析交叉引用和注释

**输入**:
- `reference_text`: 引用文本（如 "见第六章"、"注1"）
- `reg_id`: 规程ID
- `page_hint`: 页码提示

**工具白名单**:
- `resolve_reference`: 解析交叉引用
- `lookup_annotation`: 查找注释
- `search_annotations`: 搜索注释

**输出**:
```python
SubagentResult(
    content="注1：母线失压是指...",
    sources=["angui_2024:page_45:annotation_1"],
    tool_calls=[{"tool": "lookup_annotation", "args": {...}}],
    metadata={"annotation_id": "annotation_1"}
)
```

**实现策略**:
1. 识别引用类型（章节引用 vs 注释引用）
2. 调用相应工具解析引用
3. 返回引用目标内容

---

### 3.5 SemanticSearchSubagent（语义搜索）

**功能**: 基于语义相似度查找相关内容

**输入**:
- `query`: 查询描述
- `reg_id`: 规程ID
- `chapter_scope`: 可选的章节范围

**工具白名单**:
- `smart_search`: 智能搜索（semantic 模式）
- `find_similar_content`: 查找相似内容
- `compare_sections`: 比较章节

**输出**:
```python
SubagentResult(
    content="找到相关内容：母线失压处理流程...",
    sources=["angui_2024:page_45", "angui_2024:page_46"],
    tool_calls=[{"tool": "smart_search", "args": {...}}],
    metadata={"similarity_scores": [0.92, 0.87]}
)
```

**实现策略**:
1. 调用 `smart_search` 进行语义搜索
2. 按相似度排序结果
3. 返回最相关的内容片段


## 4. OrchestratorAgent LLM 推理设计

### 4.1 规划推理（_plan_subtasks_with_llm）

**目标**: 使用 LLM 分析用户查询，确定需要哪些 L1 子任务

**输入**:
- `query`: 用户查询
- `context_info`: 上下文信息（reg_id + hints）
- `available_subagents`: 可用的 L1 子智能体列表

**LLM Prompt 结构**:
```
你是一个任务规划专家。用户提出了一个关于电力系统安全规程的查询。

可用的子任务类型：
1. locate_chapters: 定位相关章节
2. fetch_content: 获取章节内容
3. find_tables: 查找表格
4. resolve_references: 解析引用
5. semantic_search: 语义搜索

用户查询：{query}
规程ID：{reg_id}

请分析查询，确定需要执行哪些子任务，以及执行顺序。
返回 JSON 格式的任务列表。
```

**输出**:
```python
[
    {
        "type": "locate_chapters",
        "params": {"query": "锦苏直流闭锁故障", "reg_id": "angui_2024"},
        "reason": "需要先定位相关章节"
    },
    {
        "type": "fetch_content",
        "params": {"chapters": ["6", "6.1"], "reg_id": "angui_2024"},
        "reason": "获取章节详细内容"
    },
    {
        "type": "find_tables",
        "params": {"query": "安控装置动作", "reg_id": "angui_2024"},
        "reason": "查找相关表格数据"
    }
]
```

---

### 4.2 结果聚合（_aggregate_results_with_llm）

**目标**: 使用 LLM 聚合多个子任务结果，生成最终回答

**输入**:
- `subtask_results`: 子任务结果列表
- `original_query`: 原始用户查询

**LLM Prompt 结构**:
```
你是一个信息聚合专家。多个子任务已经完成，请综合这些结果回答用户的问题。

用户原始查询：{query}

子任务结果：
1. locate_chapters: 找到相关章节：第六章 母线失压处理
2. fetch_content: 第六章内容：...
3. find_tables: 找到表格：表6-1 母线失压处理流程

请基于这些信息，生成一个完整、准确的回答。
要求：
- 直接回答用户问题
- 引用具体的章节和页码
- 如果有表格，说明表格内容
- 保持专业性和准确性
```

**输出**:
```
锦苏直流系统发生闭锁故障时，安控装置的动作逻辑如下：

根据《安规》第六章第6.1节的规定：
1. 故障检测：安控装置实时监测直流系统运行状态...
2. 动作判据：当检测到闭锁信号时...
3. 切除策略：按照表6-1所示的处理流程...

稳规对此类故障的要求（第6.2节）：
- 系统稳定性要求：...
- 恢复时间要求：...

参考来源：
- 第六章 母线失压处理（第45-47页）
- 表6-1 母线失压处理流程（第46页）
```


## 5. 技术实现细节

### 5.1 框架适配

#### 5.1.1 Claude SDK 实现

```python
class ClaudeOrchestrator(OrchestratorAgent):
    async def _plan_subtasks_with_llm(self, query: str, context_info: str):
        # 构建规划 prompt
        planning_prompt = self._build_planning_prompt(query, context_info)
        
        # 调用 Claude SDK
        async with ClaudeSDKClient(options=self._options) as client:
            await client.query(planning_prompt)
            response = await client.receive_response()
            
        # 解析 JSON 响应
        subtasks = json.loads(response.content)
        return subtasks
```

#### 5.1.2 Pydantic AI 实现

```python
class PydanticOrchestrator(OrchestratorAgent):
    async def _plan_subtasks_with_llm(self, query: str, context_info: str):
        # 使用 Pydantic AI 的结构化输出
        result = await self._agent.run(
            query,
            result_type=SubtaskPlan,  # Pydantic model
        )
        return result.data.subtasks
```

#### 5.1.3 LangGraph 实现

```python
class LangGraphOrchestrator(OrchestratorAgent):
    async def _plan_subtasks_with_llm(self, query: str, context_info: str):
        # 使用 LangGraph 的状态机
        state = {"query": query, "context": context_info}
        result = await self._graph.ainvoke(state)
        return result["subtasks"]
```

---

### 5.2 工具白名单实现

```python
# SubagentConfig 中定义工具白名单
LOCATE_CHAPTERS_CONFIG = SubagentConfig(
    name="locate_chapters",
    description="定位相关章节",
    subagent_type=SubagentType.LOCATE_CHAPTERS,
    available_tools=[
        "get_toc",
        "get_chapter_structure",
    ],
)

# MCPConnectionManager 中实现工具过滤
class MCPConnectionManager:
    def __init__(self, allowed_tools: list[str] | None = None):
        self.allowed_tools = allowed_tools
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_name in self.allowed_tools
```

---

### 5.3 异步上下文管理

**问题**: SSE 客户端的 TaskGroup 异步错误

**解决方案**:
```python
class ClaudeOrchestrator(OrchestratorAgent):
    async def __aenter__(self):
        await self._ensure_initialized()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 确保在同一个 task 中退出
        if self._mcp_manager and self._mcp_manager.is_connected():
            await self._mcp_manager.close()
```

