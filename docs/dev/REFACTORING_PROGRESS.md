# RegReader 项目结构重构进度报告

## 执行时间
- 开始时间: 2026-01-15
- 当前状态: 进行中（阶段 5-6 待完成）

## 重构目标

### 主要目标
1. **消除代码重复**: 通过 BaseOrchestrator 抽象基类消除 ~900 行重复代码
2. **清晰的层次结构**: 按照 7 层架构组织代码
3. **模式分离**: 普通模式和 Orchestrator 模式清晰分离

### 预期收益
- 代码重复: 900 行 → 0 行（100% 消除）
- 代码行数: 减少 300-400 行
- 可维护性: 统一基类，易于扩展
- 开发效率: 新增框架只需实现 2 个方法

## 实施进度

### ✅ 阶段 1: 准备工作 - 创建新目录结构（已完成）

**执行内容**:
- 创建核心层目录: `src/regreader/core/`
- 创建 agents 子目录: `agents/shared/`, `agents/direct/`, `agents/orchestrated/`
- 创建所有 `__init__.py` 文件

**创建的目录**:
```
src/regreader/
├── core/
│   └── __init__.py
├── agents/
│   ├── shared/
│   │   └── __init__.py
│   ├── direct/
│   │   └── __init__.py
│   └── orchestrated/
│       └── __init__.py
```

**验证结果**: ✅ 所有目录创建成功

---

### ✅ 阶段 2: 移动核心配置（已完成）

**执行内容**:
- 移动 `config.py` → `core/config.py`
- 移动 `exceptions.py` → `core/exceptions.py`
- 更新 `core/__init__.py` 导出所有配置和异常类

**影响的文件**:
- 移动: 2 个文件
- 更新导入: 25 个文件（config）+ 19 个文件（exceptions）

**关键代码**:
```python
# core/__init__.py
from .config import Config
from .exceptions import (
    RegReaderError,
    ParserError,
    StorageError,
    # ... 所有异常类
)
```

**验证结果**: ✅ 所有导入路径更新成功，无遗漏

---

### ✅ 阶段 3: 移动共享组件到 agents/shared/（已完成）

**执行内容**:
- 移动 9 个共享组件文件到 `agents/shared/`
- 更新 `agents/shared/__init__.py` 导出所有共享组件

**移动的文件**:
1. `callbacks.py` - 状态回调系统
2. `events.py` - 事件定义和工厂函数
3. `display.py` - Rich-based 状态显示
4. `memory.py` - 对话历史和 TOC 缓存
5. `result_parser.py` - 结果解析工具
6. `mcp_connection.py` - MCP 连接管理
7. `mcp_config.py` - MCP 配置
8. `llm_timing.py` - LLM API 计时
9. `otel_hooks.py` - OpenTelemetry 钩子

**影响的文件**:
- 移动: 9 个文件
- 更新导入: 57 个文件

**关键代码**:
```python
# agents/shared/__init__.py
from .callbacks import StatusCallback, NullCallback, CompositeCallback, LoggingCallback
from .events import AgentEvent, AgentEventType, thinking_event, tool_start_event, ...
from .display import AgentStatusDisplay
from .memory import AgentMemory, ContentChunk
from .result_parser import ResultParser
from .mcp_connection import MCPConnectionConfig, get_mcp_manager, ...
```

**验证结果**: ✅ 所有共享组件移动成功，导入路径更新完成

---

### ✅ 阶段 4: 实现 BaseOrchestrator 抽象基类（已完成）

**执行内容**:
- 创建 `agents/orchestrated/base.py`（260 行）
- 实现 Template Method 模式
- 提取共享方法和定义抽象方法

**核心设计**:

#### 1. 共享方法（具体实现）
```python
def _build_context_info(self, hints: dict[str, Any]) -> str:
    """构建上下文信息（100% 共享）"""
    context_parts = []
    if self.reg_id:
        context_parts.append(f"默认规程: {self.reg_id}")
    if hints:
        hints_lines = [f"- {k}: {v}" for k, v in hints.items() if v]
        if hints_lines:
            context_parts.append("查询提示:\n" + "\n".join(hints_lines))
    return "\n\n".join(context_parts) if context_parts else ""

def _extract_sources(self, result: Any) -> None:
    """递归提取来源引用（95% 共享）"""
    if isinstance(result, dict):
        if "source" in result:
            source = result["source"]
            if source and source not in self._sources:
                self._sources.append(source)
        for value in result.values():
            self._extract_sources(value)
    elif isinstance(result, list):
        for item in result:
            self._extract_sources(item)
    elif isinstance(result, str):
        try:
            parsed = json.loads(result)
            self._extract_sources(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

def _reset_tracking(self) -> None:
    """重置跟踪状态"""
    self._sources.clear()
    self._tool_calls.clear()

async def _send_event(self, event: AgentEvent) -> None:
    """发送事件到回调"""
    await self.callback.on_event(event)
```

#### 2. 抽象方法（子类实现）
```python
@abstractmethod
async def _ensure_initialized(self) -> None:
    """初始化组件（框架特定）

    子类需要实现此方法来初始化框架特定的组件：
    - Claude SDK: 创建 Agent 和 Subagent 定义
    - Pydantic AI: 创建 Agent 并注册工具
    - LangGraph: 构建 Graph 和 Subgraph
    """
    pass

@abstractmethod
async def _execute_orchestration(
    self,
    query: str,
    context_info: str,
) -> str:
    """执行编排逻辑（框架特定）

    子类需要实现此方法来执行框架特定的编排逻辑：
    - Claude SDK: 使用 Handoff Pattern
    - Pydantic AI: 使用 Delegation Pattern
    - LangGraph: 使用 Subgraph Pattern
    """
    pass
```

#### 3. 模板方法（统一流程）
```python
async def chat(self, message: str) -> AgentResponse:
    """统一的 chat 流程（模板方法）

    定义了所有 Orchestrator 的标准执行流程：
    1. 确保初始化
    2. 重置跟踪
    3. 提取提示
    4. 记录查询（如果使用 Coordinator）
    5. 构建上下文
    6. 发送思考事件
    7. 执行编排（框架特定）
    8. 发送完成事件
    9. 写入结果（如果使用 Coordinator）
    10. 返回响应
    """
    # 1. 确保初始化
    await self._ensure_initialized()

    # 2. 重置跟踪
    self._reset_tracking()

    # 3. 提取提示
    hints = QueryAnalyzer.extract_hints(message)
    logger.debug(f"Extracted hints: {hints}")

    # 4. 记录查询（如果使用 Coordinator）
    if self.use_coordinator and self.coordinator:
        self.coordinator.log_query(message)

    # 5. 构建上下文
    context_info = self._build_context_info(hints)
    if context_info:
        logger.debug(f"Context info: {context_info}")

    # 6. 发送思考事件
    await self._send_event(thinking_event("正在分析查询..."))

    # 7. 执行编排（框架特定）
    try:
        content = await self._execute_orchestration(message, context_info)
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        raise

    # 8. 发送完成事件
    await self._send_event(complete_event())

    # 9. 写入结果（如果使用 Coordinator）
    if self.use_coordinator and self.coordinator:
        self.coordinator.write_result(content, self._sources)

    # 10. 返回响应
    return AgentResponse(
        content=content,
        sources=self._sources,
        tool_calls=self._tool_calls,
    )
```

**代码统计**:
- 总行数: 260 行
- 共享方法: ~80 行
- 抽象方法: ~40 行
- 模板方法: ~60 行
- 文档字符串: ~80 行

**验证结果**: ✅ BaseOrchestrator 实现完成，接口设计合理

---

### ✅ 阶段 5: 重构 Claude Orchestrator 继承 BaseOrchestrator（已完成）

**执行内容**:
1. ✅ 修改 `agents/orchestrated/claude.py` 继承 `BaseOrchestrator`
2. ✅ 删除重复方法: `_build_context_info()`, `_extract_sources()`, `chat()`
3. ✅ 实现抽象方法: `_execute_orchestration()`
4. ✅ 简化 `__init__()` 和 `reset()` 方法

**重构结果**:
- 文件路径: `src/regreader/agents/orchestrated/claude.py`
- 重构前行数: 782 行
- 重构后行数: 667 行
- **成功删除: 115 行代码（约 15%）**
- Python 语法检查: ✅ 通过

**重构前代码结构**:
```python
class ClaudeOrchestrator(BaseRegReaderAgent):
    def __init__(self, ...):
        # 初始化代码

    def _build_context_info(self, hints: dict) -> str:
        # 重复代码（将删除）

    def _extract_sources(self, result: Any) -> None:
        # 重复代码（将删除）

    def _reset_tracking(self) -> None:
        # 重复代码（将删除）

    async def chat(self, message: str) -> AgentResponse:
        # 重复代码（将删除）

    async def _ensure_initialized(self) -> None:
        # 保留并移到抽象方法实现

    async def _execute_orchestration(self, ...) -> str:
        # 需要新增的抽象方法实现
```

**重构后代码结构**:
```python
class ClaudeOrchestrator(BaseOrchestrator):
    """Claude SDK Orchestrator（继承 BaseOrchestrator）

    使用 Handoff Pattern 实现 LLM 自主选择子智能体。
    继承 BaseOrchestrator，共享上下文构建、来源提取等基础设施。
    """

    def __init__(self, ...):
        # 调用 BaseOrchestrator 构造函数
        super().__init__(
            reg_id=reg_id,
            use_coordinator=coordinator is not None,
            callback=status_callback or NullCallback(),
        )
        # Claude SDK 特定初始化
        self._model = model or settings.anthropic_model_name or ""
        self._use_preset = use_preset
        self._enabled_subagents = set(enabled_subagents)
        # ... 其他 Claude 特定配置

    async def _ensure_initialized(self) -> None:
        """初始化 Claude SDK 组件（框架特定）"""
        if not self._initialized:
            self._subagents = self._create_subagents()
            self._initialized = True

    async def _execute_orchestration(
        self,
        query: str,
        context_info: str,
    ) -> str:
        """执行 Claude SDK 编排（Handoff Pattern）"""
        # 构建完整查询
        enhanced_message = f"{query}\n\n{context_info}" if context_info else query

        # 构建 Agent 选项
        options = self._build_main_agent_options()

        # 执行 Main Agent
        final_content = ""
        async with ClaudeSDKClient(options=options) as client:
            await client.query(enhanced_message)
            async for event in client.receive_response():
                await self._process_event(event)
                if ResultMessage is not None and isinstance(event, ResultMessage):
                    if event.result:
                        final_content = event.result
                    break

        # 发送文本事件
        if final_content:
            await self._send_event(text_delta_event(final_content))

        return final_content

    # 删除的方法（现在由 BaseOrchestrator 提供）:
    # - _build_context_info()
    # - _extract_sources()
    # - chat()
```

**关键改进**:
1. **继承关系**: `BaseRegReaderAgent` → `BaseOrchestrator`
2. **删除重复代码**: 3 个方法（~100 行）
3. **新增抽象方法实现**: `_execute_orchestration()` (~45 行）
4. **简化 __init__()**: 移除冗余实例变量（`_callback`, `_tool_calls`, `_sources`, `_initialized`）
5. **简化 reset()**: 调用父类的 `_reset_tracking()`

**验证结果**: ✅ 重构完成，语法检查通过

---

### ⏳ 阶段 6: 重构 Pydantic 和 LangGraph Orchestrator（待完成）

**计划内容**:
类似阶段 5，重构另外两个框架的 Orchestrator：
1. `agents/orchestrated/pydantic.py` (~750 行)
2. `agents/orchestrated/langgraph.py` (~750 行)

**预期效果**:
- Pydantic Orchestrator: 减少 ~140 行
- LangGraph Orchestrator: 减少 ~140 行
- 总计减少: ~430 行重复代码

**状态**: ⏳ 待执行

---

### ✅ 阶段 7: 移动普通模式 Agent 到 agents/direct/（已完成）

**执行内容**:
- 移动 3 个普通模式 Agent 文件
- 更新 `agents/direct/__init__.py`

**移动的文件**:
1. `claude_agent.py` → `agents/direct/claude.py`
2. `pydantic_agent.py` → `agents/direct/pydantic.py`
3. `langgraph_agent.py` → `agents/direct/langgraph.py`

**同时移动的 Orchestrator 文件**:
1. `agents/claude/orchestrator.py` → `agents/orchestrated/claude.py`
2. `agents/pydantic/orchestrator.py` → `agents/orchestrated/pydantic.py`
3. `agents/langgraph/orchestrator.py` → `agents/orchestrated/langgraph.py`

**删除的旧目录**:
- `agents/claude/`
- `agents/pydantic/`
- `agents/langgraph/`

**验证结果**: ✅ 所有文件移动成功，旧目录已删除

---

### ✅ 阶段 8: 批量更新所有导入路径（已完成）

**执行内容**:
- 更新 `agents/__init__.py` 使用新的导入路径
- 验证所有旧导入路径已移除

**更新的导入**:
```python
# 旧导入（已移除）
from .claude_agent import ClaudeAgent
from .pydantic_agent import PydanticAgent
from .langgraph_agent import LangGraphAgent
from .claude.orchestrator import ClaudeOrchestrator
from .pydantic.orchestrator import PydanticOrchestrator
from .langgraph.orchestrator import LangGraphOrchestrator

# 新导入（已应用）
from .direct.claude import ClaudeAgent
from .direct.pydantic import PydanticAIAgent
from .direct.langgraph import LangGraphAgent
from .orchestrated.claude import ClaudeOrchestrator
from .orchestrated.pydantic import PydanticOrchestrator
from .orchestrated.langgraph import LangGraphOrchestrator
```

**验证结果**: ✅ 所有导入路径更新成功，无遗漏

---

### ⏳ 阶段 9: 运行测试验证（待完成）

**计划内容**:

#### 1. 单元测试
```bash
# 测试 BaseOrchestrator
pytest tests/agents/orchestrated/test_base_orchestrator.py -xvs

# 测试三个框架的 Orchestrator
pytest tests/agents/orchestrated/test_claude.py -xvs
pytest tests/agents/orchestrated/test_pydantic.py -xvs
pytest tests/agents/orchestrated/test_langgraph.py -xvs

# 测试共享组件
pytest tests/agents/shared/ -xvs

# 测试普通模式 Agent
pytest tests/agents/direct/ -xvs

# 运行所有测试
pytest tests/ -xvs --cov=src/regreader --cov-report=term-missing
```

#### 2. 集成测试
```bash
# 测试 Orchestrator 模式
regreader chat-claude-orch -r angui_2024 <<EOF
母线失压如何处理？
EOF

regreader chat-pydantic-orch -r angui_2024 <<EOF
母线失压如何处理？
EOF

regreader chat-langgraph-orch -r angui_2024 <<EOF
母线失压如何处理？
EOF

# 测试普通模式
regreader chat-claude -r angui_2024 <<EOF
母线失压如何处理？
EOF
```

#### 3. 性能测试
```bash
# 对比重构前后的性能
time regreader ask "母线失压如何处理?" -r angui_2024 --agent claude --orchestrator
```

**状态**: ⏳ 待执行

---

### ⏳ 阶段 10: 更新文档（待完成）

**计划内容**:

#### 1. 更新 CLAUDE.md
- 更新项目结构图
- 更新目录说明
- 更新开发约束

#### 2. 更新 docs/ 架构文档
- `docs/subagents/SUBAGENTS_ARCHITECTURE.md`
- `docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md`
- `docs/dev/DESIGN_DOCUMENT.md`

#### 3. 更新 README.md
- 更新项目结构说明
- 更新安装和使用指南

**状态**: ⏳ 待执行

---

## 关键文件清单

### 已创建的文件
- ✅ `src/regreader/core/__init__.py`
- ✅ `src/regreader/agents/shared/__init__.py`
- ✅ `src/regreader/agents/direct/__init__.py`
- ✅ `src/regreader/agents/orchestrated/__init__.py`
- ✅ `src/regreader/agents/orchestrated/base.py` (260 行，核心)

### 已移动的文件
- ✅ `config.py` → `core/config.py`
- ✅ `exceptions.py` → `core/exceptions.py`
- ✅ 9 个共享组件 → `agents/shared/`
- ✅ 3 个普通模式 Agent → `agents/direct/`
- ✅ 3 个 Orchestrator → `agents/orchestrated/`

### 待修改的文件
- ⏳ `agents/orchestrated/claude.py` (~780 行)
- ⏳ `agents/orchestrated/pydantic.py` (~750 行)
- ⏳ `agents/orchestrated/langgraph.py` (~750 行)

### 已删除的目录
- ✅ `agents/claude/`
- ✅ `agents/pydantic/`
- ✅ `agents/langgraph/`

---

## 代码统计

### 当前状态
- **已完成阶段**: 1, 2, 3, 4, 7, 8（6/10）
- **待完成阶段**: 5, 6, 9, 10（4/10）
- **总体进度**: 60%

### 代码变化统计
- **新增代码**: ~260 行（BaseOrchestrator）
- **移动文件**: 17 个文件
- **更新导入**: ~100 个文件
- **待删除重复代码**: ~430 行（阶段 5-6）
- **预计净减少**: ~170 行

### 目录结构变化
```
重构前:
src/regreader/
├── config.py
├── exceptions.py
├── agents/
│   ├── callbacks.py
│   ├── events.py
│   ├── display.py
│   ├── memory.py
│   ├── claude_agent.py
│   ├── pydantic_agent.py
│   ├── langgraph_agent.py
│   ├── claude/
│   │   └── orchestrator.py
│   ├── pydantic/
│   │   └── orchestrator.py
│   └── langgraph/
│       └── orchestrator.py

重构后:
src/regreader/
├── core/
│   ├── config.py
│   └── exceptions.py
├── agents/
│   ├── shared/
│   │   ├── callbacks.py
│   │   ├── events.py
│   │   ├── display.py
│   │   └── memory.py
│   ├── direct/
│   │   ├── claude.py
│   │   ├── pydantic.py
│   │   └── langgraph.py
│   └── orchestrated/
│       ├── base.py (新增)
│       ├── claude.py
│       ├── pydantic.py
│       └── langgraph.py
```

---

## 遇到的问题和解决方案

### 问题 1: Edit 工具字符串匹配歧义
**描述**: 在编辑 `base.py` 时，Edit 工具发现 2 个匹配的字符串，拒绝执行。
```
Found 2 matches of the string to replace, but replace_all is false.
```

**解决方案**: 提供更多上下文来唯一标识目标位置：
```python
old_string="Raises:\n            任何执行过程中的异常\n        \"\"\"\n        pass"
```

### 问题 2: 文件读取要求
**描述**: 尝试写入 `__init__.py` 文件时，工具要求先读取文件。
```
File has not been read yet. Read it first before writing to it.
```

**解决方案**: 在所有 Write 操作前添加 Read 操作。

### 问题 3: 大文件重构策略
**描述**: 阶段 5-6 需要重构 3 个大文件（~2000 行总计），一次性完成可能导致上下文溢出。

**解决方案**:
- 先完成阶段 7-8（移动文件和更新导入）
- 将阶段 5-6 推迟到最后
- 采用分步重构策略：一次重构一个文件

---

## 下一步行动

### 立即执行（阶段 5）
1. 读取 `agents/orchestrated/claude.py`
2. 修改类继承: `BaseRegReaderAgent` → `BaseOrchestrator`
3. 删除重复方法: `_build_context_info()`, `_extract_sources()`, `_reset_tracking()`, `chat()`
4. 实现抽象方法: `_ensure_initialized()`, `_execute_orchestration()`
5. 测试 Claude Orchestrator

### 后续执行（阶段 6）
1. 重构 Pydantic Orchestrator
2. 重构 LangGraph Orchestrator
3. 测试所有 Orchestrator

### 验证执行（阶段 9）
1. 运行单元测试
2. 运行集成测试
3. 运行性能测试
4. 验证所有功能正常

### 文档更新（阶段 10）
1. 更新 CLAUDE.md
2. 更新 docs/ 架构文档
3. 更新 README.md

---

## 风险评估

### 高风险（已缓解）
- ✅ **导入路径变更**: 已通过批量 sed 命令完成，验证无遗漏

### 中风险（待缓解）
- ⚠️ **BaseOrchestrator 抽象不当**: 需要通过实际重构验证抽象合理性
- ⚠️ **测试覆盖不足**: 需要增加单元测试和集成测试

### 低风险
- ✅ **文件移动错误**: 已完成，无问题
- ✅ **目录结构混乱**: 已完成，结构清晰

---

## 预期最终效果

### 代码质量
- **代码重复**: 900 行 → 0 行（100% 消除）
- **代码行数**: 减少 300-400 行
- **可维护性**: 统一基类，易于扩展
- **可读性**: 层次清晰，职责分明

### 架构改进
- **符合 7 层架构**: 目录结构与架构文档一致
- **模式分离**: 普通模式和 Orchestrator 模式清晰分离
- **共享组件**: 所有共享代码集中管理

### 开发效率
- **新增框架**: 只需实现 2 个方法（_ensure_initialized, _execute_orchestration）
- **修改共享逻辑**: 只需修改 BaseOrchestrator
- **调试简化**: 统一的事件和日志系统

---

## 总结

### 已完成工作
1. ✅ 创建新目录结构（阶段 1）
2. ✅ 移动核心配置（阶段 2）
3. ✅ 移动共享组件（阶段 3）
4. ✅ 实现 BaseOrchestrator（阶段 4）
5. ✅ 移动普通模式 Agent（阶段 7）
6. ✅ 更新所有导入路径（阶段 8）

### 待完成工作
1. ⏳ 重构 Claude Orchestrator（阶段 5）
2. ⏳ 重构 Pydantic/LangGraph Orchestrator（阶段 6）
3. ⏳ 运行测试验证（阶段 9）
4. ⏳ 更新文档（阶段 10）

### 关键成果
- **BaseOrchestrator 抽象基类**: 260 行，提供统一的编排流程
- **清晰的目录结构**: 符合 7 层架构设计
- **模式分离**: direct/ 和 orchestrated/ 清晰分离
- **共享组件集中**: shared/ 目录统一管理

### 下一步
继续执行**阶段 5：重构 Claude Orchestrator 继承 BaseOrchestrator**。
