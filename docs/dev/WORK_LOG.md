# RegReader 开发工作日志 (dev 分支)

## 2026-01-12 集成 Claude Agent SDK `preset: "claude_code"`

### 会话概述

实现 Claude Agent SDK 的 `preset: "claude_code"` 支持，将 Claude 从简单的"聊天机器人"升级为"自主编程代理"，同时保持RegReader的领域特定知识。

### 背景

RegReader 的 Claude Agent SDK 实现一直使用手动编写的系统提示词（约1760字），需要持续维护和调优。`preset: "claude_code"` 是 Anthropic 官方提供的预配置提示词包，包含：
- 工具使用最佳实践
- 任务规划和分解能力
- 智能错误恢复策略
- 代码理解和生成优化

集成 preset 可以：
1. 减少提示词维护负担 60-80%
2. 自动获得 Anthropic 的最佳实践更新
3. 提升工具使用效率和任务规划能力

### 完成的工作

#### 1. 深度分析与方案设计

**现状分析**:
- 审计当前实现：`subagents.py`、`orchestrator.py`、`prompts.py`
- 确认未使用 preset，完全依赖手动提示词
- 测量提示词长度：4个Subagent共约1760字

**方案设计**:
- **方案A（保守）**：仅 Orchestrator 使用 preset
- **方案B（混合）**：Orchestrator + Subagent 都使用 preset + 精简领域指令 ⭐ **推荐**
- **方案C（激进）**：完全依赖 preset，最小化自定义

**选择依据**:
- 方案B 平衡收益与风险
- 保留电力规程领域知识
- 通过 `use_preset` 参数支持向后兼容

#### 2. 核心代码实现

**修改文件总览**:
- `src/regreader/agents/claude/subagents.py` (核心实现)
- `src/regreader/agents/claude/orchestrator.py` (参数传递)
- `tests/bash-fs-paradiam/test_claude_preset.py` (测试脚本)

**关键实现**:

1. **BaseClaudeSubagent 增强** (`subagents.py`):
   ```python
   def __init__(self, config, model, mcp_manager, use_preset: bool = False):
       self._use_preset = use_preset  # 新增参数
   ```

2. **双模式提示词生成**:
   - `_build_system_prompt()`: 传统手动模式（保留）
   - `_build_domain_prompt()`: Preset模式专用（新增，约500-700字）

   领域提示词包含：
   - 角色定位
   - 电力规程领域知识（章节格式、表格规则、注释语法）
   - 工具使用约束
   - 检索策略
   - 执行上下文注入

3. **智能选项构建** (`_build_options()`):
   ```python
   if self._use_preset:
       options_kwargs["preset"] = "claude_code"
       options_kwargs["system_prompt"] = self._build_domain_prompt(context)
       logger.debug(f"Using preset: 'claude_code' with domain prompt")
   else:
       options_kwargs["system_prompt"] = self._build_system_prompt(context)
       logger.debug(f"Using manual system prompt")
   ```

4. **ClaudeOrchestrator 集成**:
   - 新增 `use_preset` 参数（默认 `False` 保持向后兼容）
   - 传递参数到所有 Subagent 创建过程
   - 日志记录 preset 模式状态

5. **工厂函数更新**:
   ```python
   def create_claude_subagent(config, model, mcp_manager, use_preset: bool = False):
       return subagent_class(config, model, mcp_manager, use_preset)
   ```

#### 3. 测试脚本开发

**文件**: `tests/bash-fs-paradiam/test_claude_preset.py`

**测试覆盖**:

1. **基本功能测试** (`test_preset_basic_functionality`):
   - 验证 `use_preset` 参数传递正确
   - 测试默认值（向后兼容）

2. **提示词生成测试** (`test_domain_prompt_generation`):
   - 验证领域提示词包含关键信息（规程ID、章节范围、hints）
   - 验证领域知识要素（章节格式、表格规则）
   - 对比提示词长度（domain vs manual）

3. **对比测试框架** (`test_preset_vs_manual_comparison`):
   - 4类测试查询：简单检索、表格查询、章节导航、多跳推理
   - 度量指标：工具调用数、响应时间、来源准确性、内容长度
   - 生成详细对比报告
   - **注**: 需要实际 MCP 服务器和规程数据，默认跳过

**测试查询设计**:
```python
TEST_QUERIES = [
    "母线失压如何处理？",              # 简单检索
    "表6-2中注1的内容是什么？",          # 表格查询
    "第2.1.4.1.6节的详细说明",          # 章节导航
    "查找所有关于事故处理的表格...",    # 多跳推理
]
```

#### 4. 架构设计亮点

**向后兼容**:
- `use_preset` 默认 `False`，现有代码无需修改
- 手动模式保持完整功能
- 可以在任何时候切换回手动模式

**领域知识保留**:
- 领域特定提示词（500-700字）专注于电力规程知识
- 通用逻辑交给 preset 处理
- 工具约束和检索策略明确指定

**灵活配置**:
- Orchestrator 和 Subagent 独立控制 preset
- 支持部分Subagent使用preset，其他使用手动模式
- 日志记录方便调试和监控

### 技术细节

#### 提示词对比

**手动模式（原有）**:
```
SEARCH_AGENT_PROMPT (540字)
+ context injection (reg_id, chapter_scope, hints)
= 约 600-700 字
```

**Preset模式（新增）**:
```
preset: "claude_code" (Anthropic维护，约500 tokens)
+ _build_domain_prompt (500-700字)
= 约 1000-1200 字总量，但通用逻辑由官方优化
```

**关键差异**:
- 手动模式：所有逻辑自己编写和维护
- Preset模式：通用逻辑自动优化，只维护领域知识

#### 配置参数

```python
# 使用 preset 模式
orchestrator = ClaudeOrchestrator(
    reg_id="angui_2024",
    use_preset=True,  # 启用 preset
)

# 传统手动模式（默认）
orchestrator = ClaudeOrchestrator(
    reg_id="angui_2024",
    use_preset=False,  # 或省略此参数
)
```

### 预期效果

#### 量化指标

| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| 提示词维护负担 | 1760字 | 500-700字 | ⏳ 待验证 |
| 上下文 Token 占用 | 800 tokens | 1000-1200 tokens | ⏳ 待测量 |
| 工具调用效率 | 基准 | +20% | ⏳ 待测试 |
| 检索准确率 | 基准 | 不降低 | ⏳ 待验证 |

#### 定性收益

- ✅ **代码就绪**: 所有核心代码已实现并集成
- ⏳ **测试待完成**: 需要实际API调用进行对比测试
- ⏳ **性能待验证**: Token占用和响应质量需要实测
- ✅ **向后兼容**: 默认保持手动模式，无breaking change

### 后续工作

#### 短期（1周内）

1. **实际对比测试**:
   - 运行 MCP 服务器
   - 导入测试规程数据
   - 执行 `test_preset_vs_manual_comparison()`
   - 收集性能指标

2. **Token 占用测量**:
   - 对比 preset vs 手动模式的实际 token 消耗
   - 验证是否在可接受范围（1300 tokens 以内）

3. **响应质量评估**:
   - 人工评估检索准确率
   - 对比答案完整性和相关性
   - 检查是否有功能退化

#### 中期（2周内）

1. **A/B 测试优化**:
   - 根据测试结果调整领域提示词
   - 优化工具使用策略描述
   - 平衡token占用和功能完整性

2. **文档完善**:
   - 更新 CLAUDE.md 的技术栈约束
   - 添加 preset 使用指南
   - 记录最佳实践和注意事项

3. **生产部署准备**:
   - 制定回滚方案
   - 设置监控指标
   - 准备渐进式推进策略

#### 长期（1个月内）

1. **配置化控制**:
   - 添加全局配置开关 `use_claude_code_preset`
   - 支持环境变量配置
   - 实现 Orchestrator 和 Subagent 独立控制

2. **监控告警**:
   - 添加工具调用失败率监控
   - 对比 preset vs 手动模式的成功率
   - 设置性能退化告警

3. **持续优化**:
   - 跟踪 Anthropic 的 preset 更新
   - 持续精简领域特定提示词
   - 积累最佳实践案例

### 关键文件变更

```
src/regreader/agents/claude/
├── subagents.py              # 核心实现：preset 支持 + 领域提示词
├── orchestrator.py           # 参数传递：use_preset 集成
tests/bash-fs-paradiam/
└── test_claude_preset.py     # 测试框架：对比测试 + 功能验证
```

**变更统计**:
- 3 个文件修改
- 1 个文件新增
- 约 400 行代码新增/修改
- 100% 向后兼容

### 风险与缓解

#### 风险1：与专门化策略冲突

**风险描述**: Preset 可能鼓励"全能"行为，与 Subagent 专门化冲突

**缓解措施**:
- ✅ `allowed_tools` 强制限制可用工具
- ✅ 领域提示词明确"你只能使用以下MCP工具"
- ⏳ 实际测试验证 preset + 工具过滤的兼容性

#### 风险2：上下文膨胀

**风险描述**: Preset 可能占用 200-500 tokens，削弱上下文优化效果

**分析**:
- ✅ 即使 +500 tokens，总量 1300 tokens 仍远低于 4000 tokens
- ✅ 价值交换合理：用 500 tokens 换更智能的工具使用
- ⏳ 需要实测验证实际 token 占用

#### 风险3：领域特异性丢失

**风险描述**: Preset 不了解电力规程领域细节

**缓解措施**:
- ✅ Preset + 自定义提示词分层设计
- ✅ 领域提示词保留所有领域知识
- ✅ 章节格式、表格规则、检索策略明确指定

### 技术债务

无新增技术债务。实现保持了良好的代码质量和向后兼容性。

### 学习与收获

1. **架构灵活性**: 通过参数化设计实现了 preset 和手动模式的无缝切换
2. **领域知识分离**: 将通用逻辑和领域知识分层，提高了可维护性
3. **测试驱动**: 测试脚本先于全面集成完成，便于快速验证

### 附录：使用示例

#### 启用 Preset 模式

```python
from regreader.agents.claude.orchestrator import ClaudeOrchestrator

# 创建启用 preset 的 Orchestrator
async with ClaudeOrchestrator(
    reg_id="angui_2024",
    use_preset=True,  # 启用 Claude Code preset
) as agent:
    response = await agent.chat("母线失压如何处理？")
    print(response.content)
```

#### 运行对比测试

```bash
# 运行完整对比测试（需要 MCP 服务器）
uv run pytest tests/bash-fs-paradiam/test_claude_preset.py::test_preset_vs_manual_comparison -xvs

# 运行基本功能测试（无需 API）
uv run pytest tests/bash-fs-paradiam/test_claude_preset.py::test_preset_basic_functionality -xvs

# 运行提示词生成测试
uv run pytest tests/bash-fs-paradiam/test_claude_preset.py::test_domain_prompt_generation -xvs
```

#### CLI 使用（待实现）

```bash
# 使用 preset 模式进行查询
regreader chat -r angui_2024 --agent claude --use-preset

# 保持手动模式（默认）
regreader chat -r angui_2024 --agent claude
```

---

## 2026-01-11 文档更新：反映 Bash+FS 架构演进

### 会话概述

对项目核心文档进行全面更新，使其准确反映最新的 Bash+FS Subagents 架构实现状态。

### 背景

RegReader 已经完成了重大架构演进：
1. **Phase 5**: Subagents 架构（上下文隔离，~4000 → ~800 tokens）
2. **Phase 6**: Bash+FS 范式（Infrastructure层、Coordinator、RegSearch-Subagent）
3. **Makefile 模块化重构**

现有文档（CLAUDE.md, README.md）未能充分反映这些变化。

### 完成的工作

#### 1. 深度代码分析

**Git 提交历史分析**:
- 识别关键提交：`3603d45` (Bash+FS), `347bc3b` (Subagents), `cea46da` (Multi-Reg)
- 分析变更统计：36 个文件，7984+ 行新增
- 确认新增模块：infrastructure/, orchestrator/, subagents/regsearch/

**代码结构探索**:
- 使用 Explore 子代理进行彻底的代码库探索
- 生成完整的架构探索报告，涵盖所有 7 个架构层
- 识别关键组件职责和依赖关系

**文档差异识别**:
- 对比现有文档与实际实现
- 识别缺失的架构层（Infrastructure, Orchestrator）
- 确认新功能：Orchestrator 模式、技能系统、事件总线

#### 2. CLAUDE.md 更新（项目开发指南）

**更新的章节**:

1. **Project Overview**:
   - 添加 Bash+FS Subagents 范式说明
   - 新增分层架构原则（7层架构）
   - 强调上下文隔离和文件通信

2. **Architecture Layers**:
   - 新增完整的 7 层架构图
   - 说明各层职责和token消耗

3. **Project Structure**:
   - 完整重写，反映实际目录结构
   - 添加 Bash+FS 工作区（coordinator/, subagents/, shared/, skills/）
   - 详细列出新增模块（infrastructure/, orchestrator/, subagents/regsearch/）
   - 包含 makefiles/ 模块化结构
   - 添加 tests/bash-fs-paradiam/ 测试套件

4. **Key Components** (新增章节):
   - **Infrastructure Layer**: FileContext, SkillLoader, EventBus, SecurityGuard
   - **Orchestrator Layer**: Coordinator, QueryAnalyzer, SubagentRouter, ResultAggregator
   - **Subagents Layer**: RegSearch-Subagent, 内部组件（SEARCH/TABLE/REFERENCE/DISCOVERY）
   - **Agent Framework Implementations**: 三框架的统一抽象

5. **Key Data Models**:
   - 添加 Infrastructure 模型（Skill, Event）
   - 添加 Orchestrator 模型（QueryIntent, SessionState）
   - 添加 Subagent 模型（SubagentContext, SubagentResult）

6. **Development Constraints**:
   - 新增 Subagent 相关约束
   - 添加 Infrastructure 组件要求
   - 扩展架构扩展指南（添加 Subagent、添加 Skill）

7. **CLI Commands Reference**:
   - 添加 Orchestrator 模式命令（--orchestrator, -o）
   - 添加框架特定简写命令（chat-claude-orch等）
   - 添加 Makefile 命令参考
   - 添加 enrich-metadata 命令

8. **Documentation Paths**:
   - 重组为三个分类（架构文档/开发文档/初步设计）
   - 添加 bash-fs-paradiam/ 文档路径
   - 添加 subagents/ 文档路径

9. **Architecture Evolution** (新增章节):
   - 完整记录 Phase 1-6 的演进历程
   - 明确当前状态（Phase 6）
   - 规划未来阶段（Exec-Subagent, Validator-Subagent）

#### 3. README.md 更新（用户文档）

**更新的章节**:

1. **Why RegReader?**:
   - 添加"上下文过载"和"可扩展性"对比
   - 展示 Subagents 带来的优势

2. **Design Philosophy**:
   - 更新架构图为 8 层（包含 Business, Orchestrator, Infrastructure）
   - 显示各层的 token 消耗情况

3. **Core Principles**:
   - 扩展为 8 条原则
   - 新增：Context Isolation, Orchestrator Pattern, Bash+FS Paradigm
   - 强调多框架统一抽象

4. **Agent Setup**:
   - 完全重写，区分 Standard Mode 和 Orchestrator Mode
   - 详细说明两种模式的使用场景和优势
   - 为每个框架添加 Orchestrator 模式示例
   - 添加简写命令（-o, chat-*-orch）

5. **Architecture Note**:
   - 更新架构图，展示 Optional Orchestrator Layer
   - 说明 MCP Server 拥有 16+ 工具

6. **Project Status**:
   - 更新为完整的 Phase 1-6 检查列表
   - 添加最新特性列表
   - 明确标记已完成和待完成项

#### 4. 关键改进点

**一致性提升**:
- 所有文档使用统一的架构层次术语
- 统一 token 消耗数据（~4000 → ~800）
- 统一目录路径表示

**完整性提升**:
- 覆盖所有新增组件（Infrastructure 4个, Orchestrator 4个）
- 文档化 Bash+FS 工作区结构
- 包含所有 CLI 命令变体

**准确性提升**:
- 反映实际代码结构（非设想）
- 基于 git diff 确认变更
- 引用真实文件路径

### 技术细节

**分析方法**:
1. Git 历史分析：`git log --oneline -20`, `git diff --stat main..HEAD`
2. 代码探索：Task tool with Explore subagent (very thorough mode)
3. 文档比对：逐章节识别差异
4. 结构化更新：保持原有章节组织，扩展内容

**更新的文件**:
| 文件 | 更新内容 | 行数变化 |
|------|---------|---------|
| `CLAUDE.md` | 完整架构重写，新增 3 个章节 | +350 行 |
| `README.md` | 架构图更新，Orchestrator 模式说明 | +80 行 |
| `docs/dev/WORK_LOG.md` | 本次更新记录 | +100 行 |

**涉及的架构层**:
- ✅ Infrastructure Layer (4 components documented)
- ✅ Orchestrator Layer (4 components documented)
- ✅ Subagents Layer (RegSearch + 4 internal components)
- ✅ Agent Framework Layer (3 frameworks with Orchestrator support)
- ✅ MCP Tool Layer (16+ tools organized)
- ✅ Storage & Index Layer (existing, confirmed)

### 验证

**文档一致性检查**:
- ✅ CLAUDE.md 的项目结构与 `tree` 命令输出一致
- ✅ README.md 的 CLI 命令与 `regreader --help` 一致
- ✅ 架构图与代码模块对应
- ✅ Token 消耗数据与实际 prompt 长度匹配

**完整性检查**:
- ✅ 所有新增目录（coordinator/, subagents/, shared/, skills/）已文档化
- ✅ 所有新增模块（infrastructure/, orchestrator/）已说明
- ✅ 所有 Orchestrator 命令已列出
- ✅ Phase 6 特性完整描述

### 相关文件

**已更新**:
- `CLAUDE.md` - 项目开发指南（英文）
- `README.md` - 用户文档（英文）
- `docs/dev/WORK_LOG.md` - 开发日志（中文）

**参考文档**（保持不变，已是最新）:
- `docs/bash-fs-paradiam/ARCHITECTURE_DESIGN.md` - Bash+FS 架构设计
- `docs/bash-fs-paradiam/API_REFERENCE.md` - API 参考
- `docs/bash-fs-paradiam/USER_GUIDE.md` - 用户指南
- `docs/bash-fs-paradiam/WORK_LOG.md` - Bash+FS 工作日志
- `docs/subagents/SUBAGENTS_ARCHITECTURE.md` - Subagents 架构文档

### 下一步

**推荐操作**:
1. ✅ 审查更新的文档内容
2. ✅ 确认架构描述准确性
3. ⏳ 根据需要创建中文版 README_CN.md
4. ⏳ 考虑为 bash-fs-paradiam 分支创建单独的 README

**未来文档工作**:
- 创建快速入门指南（Quick Start Guide）
- 编写 Orchestrator 模式最佳实践
- 补充性能基准测试文档
- 添加故障排查指南

### 备注

- 本次更新基于 bash-fs-paradiam 分支的最新代码（commit ee00825）
- 所有文档更新遵循用户的 CLAUDE.md 规范（文档使用中文，代码注释使用英文）
- 保持了原有文档的组织结构和风格
- 所有新增章节都有明确的标识（NEW）

---

## 2026-01-04 LLM API 时间追踪与 OpenTelemetry 集成

### 会话概述

实现了双轨 LLM API 时间追踪架构，支持 httpx hooks（CLI 显示）和 OpenTelemetry（生产环境监控）两种后端，并解决了最后答案生成步骤的 LLM 调用未显示问题。

### 背景问题

用户报告了以下问题：
1. 最后一步生成答案时，虽然有 LLM API 调用，但 CLI 没有明确显示
2. 需要评估 OpenTelemetry 方案用于生产环境追踪
3. 希望支持 httpx 和 OTel 双轨追踪，可通过配置切换

### 完成的工作

#### Phase 1: 答案生成事件

**events.py 更新**
- 添加 `ANSWER_GENERATION_START` 和 `ANSWER_GENERATION_END` 事件类型
- 创建 `answer_generation_start_event()` 和 `answer_generation_end_event()` 工厂函数

**pydantic_agent.py / langgraph_agent.py 更新**
- 在工具调用完成后发送 `ANSWER_GENERATION_START` 事件
- 在最终答案生成完成后发送 `ANSWER_GENERATION_END` 事件，包含思考耗时和 API 调用信息

**display.py 更新**
- 添加 `_format_answer_generation_start()` 和 `_format_answer_generation_end()` 方法
- 修复汇总条件：现在只要有任何活动（工具调用/LLM调用/API调用）就显示汇总

#### Phase 2: 双轨时间追踪架构

**新建 `src/regreader/agents/timing/` 模块**

```
timing/
├── __init__.py          # 工厂函数和导出
├── base.py              # 抽象接口 TimingBackend
├── httpx_timing.py      # HttpxTimingBackend (CLI 显示用)
└── otel_timing.py       # OTelTimingBackend (生产监控)
```

**base.py - 抽象接口**
```python
class TimingBackend(ABC):
    @abstractmethod
    def configure_httpx_client(self, client) -> client: ...
    @abstractmethod
    async def on_llm_call_start(self, **kwargs) -> None: ...
    @abstractmethod
    async def on_llm_call_end(self, duration_ms, **kwargs) -> None: ...
    def start_step(self) -> None: ...
    def get_step_metrics(self) -> StepMetrics: ...
    def get_total_metrics(self) -> dict: ...
```

**httpx_timing.py - httpx 事件钩子实现**
- 使用 `event_hooks` 拦截 HTTP 请求/响应
- 精确测量每次 LLM API 调用的 TTFT（首字节时间）和总耗时
- 保留 `LLMTimingCollector` 别名确保向后兼容

**otel_timing.py - OpenTelemetry 实现**
- 使用 `opentelemetry-instrumentation-httpx` 自动追踪
- 支持多种导出器：console, otlp, jaeger, zipkin
- 创建结构化 spans 包含模型名称、tokens 等属性

**工厂函数**
```python
def create_timing_backend(backend_type: str = "httpx", **kwargs) -> TimingBackend
def create_timing_backend_from_config(callback=None) -> TimingBackend
```

#### Phase 2.5: 配置更新

**config.py 新增配置项**
```python
timing_backend: str = "httpx"           # httpx 或 otel
otel_exporter_type: str = "console"     # console, otlp, jaeger, zipkin
otel_service_name: str = "regreader-agent"
otel_endpoint: str | None = None        # OTLP/Jaeger/Zipkin 端点
```

**pyproject.toml 新增可选依赖**
```toml
otel = ["opentelemetry-api>=1.27.0", "opentelemetry-sdk>=1.27.0", "opentelemetry-instrumentation-httpx>=0.48b0"]
otel-otlp = [...]   # + opentelemetry-exporter-otlp-proto-grpc
otel-jaeger = [...] # + opentelemetry-exporter-jaeger
otel-zipkin = [...] # + opentelemetry-exporter-zipkin
```

#### Phase 3: Claude Agent SDK OTel 集成

**新建 `src/regreader/agents/otel_hooks.py`**

为 Claude Agent SDK 的 hooks 机制提供 OTel 支持：

```python
async def otel_pre_tool_hook(input_data, tool_use_id, context) -> dict:
    """工具调用开始时创建 span"""

async def otel_post_tool_hook(input_data, tool_use_id, context) -> dict:
    """工具调用结束时结束 span"""

def get_otel_hooks(service_name, exporter_type, endpoint) -> dict:
    """获取 OTel hooks 配置"""

def get_combined_hooks(enable_audit, enable_otel, ...) -> dict:
    """获取组合的 hooks 配置（审计 + OTel）"""
```

**claude_agent.py 更新**

修改 `_build_hooks()` 方法使用组合 hooks 工厂：

```python
def _build_hooks(self):
    settings = get_settings()
    enable_otel = settings.timing_backend == "otel"

    from regreader.agents.otel_hooks import get_combined_hooks
    combined = get_combined_hooks(
        enable_audit=True,
        enable_otel=enable_otel,
        otel_service_name=settings.otel_service_name,
        otel_exporter_type=settings.otel_exporter_type,
        otel_endpoint=settings.otel_endpoint,
    )
    # 转换为 HookMatcher 格式...
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/agents/events.py` | 添加 ANSWER_GENERATION 事件 |
| `src/regreader/agents/pydantic_agent.py` | 发送答案生成事件 |
| `src/regreader/agents/langgraph_agent.py` | 发送答案生成事件 |
| `src/regreader/agents/display.py` | 处理答案生成事件，修复汇总条件 |
| `src/regreader/agents/timing/__init__.py` | 新建 - 工厂函数 |
| `src/regreader/agents/timing/base.py` | 新建 - 抽象接口 |
| `src/regreader/agents/timing/httpx_timing.py` | 新建 - httpx 后端 |
| `src/regreader/agents/timing/otel_timing.py` | 新建 - OTel 后端 |
| `src/regreader/agents/llm_timing.py` | 更新为兼容层 |
| `src/regreader/agents/otel_hooks.py` | 新建 - Claude SDK OTel hooks |
| `src/regreader/agents/claude_agent.py` | 使用组合 hooks |
| `src/regreader/config.py` | 添加 OTel 配置项 |
| `pyproject.toml` | 添加 otel 可选依赖 |

### 使用示例

```bash
# 使用 httpx 后端（默认，CLI 显示）
export REGREADER_TIMING_BACKEND=httpx
regreader chat -r angui_2024

# 使用 OTel 后端（控制台输出）
export REGREADER_TIMING_BACKEND=otel
export REGREADER_OTEL_EXPORTER_TYPE=console
regreader chat -r angui_2024

# 使用 OTel 后端（OTLP 导出到 Jaeger）
pip install regreader[otel-otlp]
export REGREADER_TIMING_BACKEND=otel
export REGREADER_OTEL_EXPORTER_TYPE=otlp
export REGREADER_OTEL_ENDPOINT=http://localhost:4317
regreader chat -r angui_2024
```

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Layer                              │
├─────────────────────────────────────────────────────────────┤
│  PydanticAIAgent  │  LangGraphAgent  │  ClaudeAgent         │
│       │                   │                 │                │
│       ▼                   ▼                 ▼                │
│  ┌─────────────────────────────┐    ┌─────────────────┐     │
│  │     TimingBackend           │    │   SDK Hooks     │     │
│  │  ┌─────────┬──────────┐    │    │ ┌─────────────┐ │     │
│  │  │ httpx   │   otel   │    │    │ │ otel_hooks  │ │     │
│  │  │ hooks   │ instrumt │    │    │ └─────────────┘ │     │
│  │  └─────────┴──────────┘    │    └─────────────────┘     │
│  └─────────────────────────────┘                            │
├─────────────────────────────────────────────────────────────┤
│                    Display/Callback                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  StatusDisplay: ANSWER_GENERATION_START/END events  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 验证结果

```
Testing imports...
✓ timing module
✓ llm_timing backward compatibility
✓ otel_hooks (OTEL_AVAILABLE=True)
✓ get_combined_hooks (audit only)
✓ claude_agent
✓ config (timing_backend=httpx)

All imports successful!
```

### 技术亮点

1. **双轨架构**：同时支持 httpx 和 OTel 两种追踪方式，可通过配置切换
2. **向后兼容**：保留 `LLMTimingCollector` 别名，旧代码无需修改
3. **可插拔导出**：OTel 支持 console/otlp/jaeger/zipkin 四种导出方式
4. **统一接口**：所有后端实现相同的 `TimingBackend` 抽象接口
5. **组合 Hooks**：Claude SDK 可同时启用审计和 OTel hooks

### 后续建议

1. 为 pydantic_agent 和 langgraph_agent 添加 OTel timing 后端支持
2. 考虑添加 Prometheus metrics 导出
3. 添加 trace context propagation 支持分布式追踪
4. 为 timing 模块添加单元测试

---

## 2026-01-04 Ollama 后端支持与 httpx 传输修复

### 会话概述

解决了 PydanticAIAgent 和 LangGraphAgent 在使用 Ollama 后端时出现的 502 Bad Gateway 错误。通过深入调试发现根本原因是 httpx 默认传输配置与 Ollama 不兼容，实现了自定义 httpx 客户端方案。

### 背景问题

用户报告 PydanticAIAgent 在使用 Ollama 后端（Qwen3-4B-Instruct-2507:Q8_0）时返回 502 错误：
- OpenAI API 后端正常工作
- Ollama 后端在流式和非流式模式下均失败
- curl 直接调用 Ollama API 正常（包括工具调用）

### 问题调试过程

#### 1. 初步尝试（失败）
- 尝试使用 `OllamaProvider`：仍然 502
- 设置 `openai_supports_strict_tool_definition=False`：仍然 502
- 确保 base_url 包含 `/v1` 后缀：仍然 502

#### 2. 系统测试隔离
- ✅ curl 直接调用 Ollama - 成功
- ✅ curl 调用 Ollama + tools - 成功
- ✅ curl 调用 Ollama + streaming + tools - 成功
- ❌ pydantic-ai 最小化测试 - 502
- ❌ OpenAI SDK 直接调用 - 502
- ❌ httpx 默认配置 - 502
- ✅ httpx + explicit AsyncHTTPTransport() - 成功！
- ✅ requests 库 - 成功
- ✅ Python subprocess + curl - 成功

#### 3. 根本原因确定

**发现**：httpx 的默认传输配置与 Ollama 存在兼容性问题。

**解决方案**：创建显式的 `httpx.AsyncHTTPTransport()`：

```python
self._ollama_http_client = httpx.AsyncClient(
    transport=httpx.AsyncHTTPTransport()
)
```

### 完成的工作

#### 1. 配置层增强 (`src/regreader/config.py`)

添加 Ollama 后端检测和配置支持：

```python
# Ollama 专用配置
ollama_disable_streaming: bool = Field(
    default=False,
    description="Ollama 后端是否禁用流式（某些模型不支持流式+工具）",
)

def is_ollama_backend(self) -> bool:
    """检测是否使用 Ollama 后端

    通过 base_url 中是否包含 Ollama 默认端口(11434)或 'ollama' 关键词来判断。
    """
    base_url = self.llm_base_url.lower()
    return ":11434" in base_url or "ollama" in base_url
```

#### 2. PydanticAIAgent 修复 (`src/regreader/agents/pydantic_agent.py`)

**核心修改**：
```python
if self._is_ollama:
    # Ollama 专用配置：使用 OpenAIChatModel + OpenAIProvider + 自定义 httpx client
    # 关键修复：httpx 默认配置与 Ollama 不兼容，需要显式创建 transport
    ollama_base = settings.llm_base_url
    if not ollama_base.endswith("/v1"):
        ollama_base = ollama_base.rstrip("/") + "/v1"

    # 创建自定义 httpx client（解决 502 问题）
    self._ollama_http_client = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport()
    )

    ollama_model = OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(
            base_url=ollama_base,
            api_key="ollama",  # Ollama 不需要真实 API key
            http_client=self._ollama_http_client,
        ),
        profile=OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
        ),
    )
    self._model = ollama_model
    self._model_name = f"ollama:{model_name}"
```

**流式降级策略**：
```python
# Ollama 流式策略：
# 1. 如果配置了禁用流式，直接使用非流式模式
# 2. 否则尝试流式，失败时降级到非流式
use_streaming = not (self._is_ollama and self._ollama_disable_streaming)

if use_streaming:
    try:
        result = await self._agent.run(
            message, deps=deps,
            message_history=self._message_history,
            event_stream_handler=event_handler,
        )
    except Exception as streaming_error:
        if self._is_ollama:
            logger.warning(
                f"Ollama streaming failed, falling back to non-streaming: {streaming_error}"
            )
            result = await self._agent.run(
                message, deps=deps,
                message_history=self._message_history,
                # 不传 event_stream_handler，使用非流式模式
            )
        else:
            raise
```

**资源清理**：
```python
async def close(self) -> None:
    """关闭 Agent 连接，并清理资源"""
    if self._connected:
        await self._agent.__aexit__(None, None, None)
        self._connected = False

    # 关闭 Ollama httpx client
    if self._ollama_http_client is not None:
        await self._ollama_http_client.aclose()
        self._ollama_http_client = None
```

#### 3. LangGraphAgent 修复 (`src/regreader/agents/langgraph_agent.py`)

应用相同的 httpx transport 修复：

```python
llm_base_url = settings.llm_base_url
if self._is_ollama:
    # Ollama 需要 /v1 后缀
    if not llm_base_url.endswith("/v1"):
        llm_base_url = llm_base_url.rstrip("/") + "/v1"
    # 关键修复：httpx 默认配置与 Ollama 不兼容，需要显式创建 transport
    self._ollama_http_client = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport()
    )
    self._llm = ChatOpenAI(
        model=self._model_name,
        api_key=settings.llm_api_key or "ollama",
        base_url=llm_base_url,
        max_tokens=4096,
        streaming=True,
        http_async_client=self._ollama_http_client,
    )
    logger.info(f"Using Ollama backend: model={self._model_name}, base_url={llm_base_url}")
else:
    self._ollama_http_client = None
    self._llm = ChatOpenAI(
        model=self._model_name,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_tokens=4096,
        streaming=True,
    )
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/config.py` | 添加 `is_ollama_backend()` 方法和 `ollama_disable_streaming` 配置 |
| `src/regreader/agents/pydantic_agent.py` | Ollama 检测、自定义 httpx client、流式降级策略、资源清理 |
| `src/regreader/agents/langgraph_agent.py` | Ollama 检测、自定义 httpx client、资源清理 |

### 环境变量配置

支持使用现有的 `OPENAI_*` 环境变量（通过 `validation_alias`）：

```bash
# Ollama 后端配置（两种方式均可）
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# 或使用 REGREADER_ 前缀
export REGREADER_LLM_BASE_URL=http://localhost:11434/v1
export REGREADER_LLM_MODEL_NAME=Qwen3-4B-Instruct-2507:Q8_0

# 可选：禁用流式（某些小模型可能需要）
export REGREADER_OLLAMA_DISABLE_STREAMING=true
```

Ollama 自动检测规则：
- base_url 包含 `:11434` → 自动识别为 Ollama
- base_url 包含 `ollama` 关键词 → 自动识别为 Ollama

### 使用示例

```bash
# PydanticAIAgent with Ollama
regreader chat -r angui_2024 --agent pydantic

# LangGraphAgent with Ollama
regreader chat -r angui_2024 --agent langgraph

# 单次查询
regreader ask "特高压南阳站稳态过电压控制装置1发生故障时，系统应如何处理？" \
  -r angui_2024 --agent pydantic -v
```

### 技术亮点

1. **问题隔离方法论**：
   - 从应用层（pydantic-ai）→ SDK层（OpenAI SDK）→ HTTP层（httpx）逐层隔离
   - 对比测试不同 HTTP 客户端（httpx vs requests vs curl）
   - 最小化复现测试（移除 MCP 工具依赖）

2. **httpx 传输机制理解**：
   - httpx 默认传输配置在某些场景下存在兼容性问题
   - 显式创建 `AsyncHTTPTransport()` 可绕过默认配置问题
   - 适用于 Ollama 等本地部署的 LLM 服务

3. **优雅的降级策略**：
   - 首先尝试流式，失败时自动降级到非流式
   - 提供配置选项可直接禁用流式（避免无意义重试）
   - 保留完整的错误日志便于调试

4. **资源管理**：
   - 正确实现 httpx client 的生命周期管理
   - 在 `close()` 方法中清理自定义 httpx 客户端
   - 避免资源泄漏

### 后续建议

1. 考虑向 httpx 或 pydantic-ai 项目报告此兼容性问题
2. 监控 Ollama 官方文档更新，确认是否有官方推荐配置
3. 添加 Ollama 后端的集成测试用例
4. 考虑支持更多本地部署 LLM 服务（如 LM Studio、LocalAI）

---

## 2026-01-02 代码分析与文档更新

### 会话概述

对当前代码实现进行全面分析，更新 CLAUDE.md 项目指南，并生成最新的系统设计与实现文档。

### 完成的工作

#### 1. 全面代码分析

对项目各模块进行了深入分析：

**Parser 层**
- `docling_parser.py` - 文档解析器，支持 OCR 和表格结构提取
- `page_extractor.py` - 页面内容提取器
- `table_registry_builder.py` - 跨页表格处理

**Storage 层**
- `models.py` - 核心数据模型 (PageDocument, ContentBlock, DocumentStructure, TableRegistry 等)
- `page_store.py` - 页面持久化存储管理

**Index 层**
- `base.py` - 抽象基类定义
- `hybrid_search.py` - RRF 混合检索器
- `table_search.py` - 表格混合检索
- `keyword/` - FTS5/Tantivy/Whoosh 关键词索引实现
- `vector/` - LanceDB/Qdrant 向量索引实现

**Embedding 层**
- `base.py` - 嵌入抽象接口
- `sentence_transformer.py` - SentenceTransformer 后端
- `flag.py` - FlagEmbedding 后端

**MCP 层**
- `tools.py` - 工具实现（4 阶段分类：基础/多跳/上下文/发现）
- `server.py` - FastMCP Server 创建
- `tool_metadata.py` - 工具元数据
- `client.py` - MCP 客户端

**Agent 层**
- `base.py` - Agent 抽象基类
- `claude_agent.py` - Claude Agent SDK 实现
- `pydantic_agent.py` - Pydantic AI 实现
- `langgraph_agent.py` - LangGraph 实现
- `memory.py` - 对话历史管理
- `display.py` - 状态显示回调
- `mcp_connection.py` - MCP 连接配置

#### 2. CLAUDE.md 更新

更新了项目开发指南，包括：

- **项目结构**: 更新为完整的目录树，包含所有子模块和文件
- **技术栈**: 添加 Embedding 层（SentenceTransformer/FlagEmbedding）
- **数据模型**: 扩展为三个分类（页面级/结构/检索）
- **MCP 工具接口**: 按 Phase 0-3 分类展示全部工具
- **开发约束**: 添加 Embedding 层扩展指南
- **CLI 命令**: 完整列出所有命令及示例
- **配置系统**: 添加完整环境变量参考
- **异常体系**: 列出完整异常类层次结构
- **文档路径**: 更新为 dev 分支路径

#### 3. 设计实施文档

创建 `docs/dev/DESIGN_DOCUMENT.md`，包含：

- **项目概述**: 定位、设计理念、技术栈架构图
- **数据模型设计**: 核心模型层级、章节结构模型、检索模型
- **存储层实现**: PageStore、TableRegistry 详细设计
- **索引层实现**: 抽象接口、关键词/向量索引实现、混合检索
- **Embedding 层实现**: 抽象接口和具体实现
- **MCP 工具层实现**: 工具分类体系、核心工具实现、Server 实现
- **Agent 层实现**: 抽象基类、三种框架实现、对话历史管理
- **CLI 实现**: 命令结构和完整命令列表
- **配置系统**: RegReaderSettings 详细配置
- **异常体系**: 完整异常类定义
- **实现状态汇总**: 已完成模块和可选模块状态
- **技术亮点**: 架构设计、数据处理、检索优化、工具设计
- **附录**: 依赖清单、环境变量参考

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `CLAUDE.md` | 全面更新项目开发指南 |
| `docs/dev/DESIGN_DOCUMENT.md` | 新建 - 系统设计与实现文档 |
| `docs/dev/WORK_LOG.md` | 更新工作日志 |

### 技术亮点总结

1. **Page-Based 架构**: 保留文档原始结构，支持跨页内容处理
2. **可插拔索引**: 支持多种关键词和向量索引后端
3. **MCP 协议标准化**: 工具接口统一，多 Agent 框架复用
4. **三框架并行**: 同时支持 Claude SDK、Pydantic AI、LangGraph
5. **分阶段工具体系**: 基础 → 多跳 → 上下文 → 发现
6. **RRF 混合检索**: 结合关键词和语义检索优势

### 后续建议

1. 补充单元测试覆盖率
2. 添加集成测试用例
3. 完善 README.md 用户文档
4. 考虑添加性能基准测试

---

## 2025-12-30 Agent MCP 架构重构

### 会话概述

重构了三个 Agent 框架的 MCP 连接管理，实现统一的 `MCPConnectionConfig` 和 `MCPConnectionManager` 机制，支持 stdio（子进程）和 SSE（共享服务）两种传输方式，解决了原有架构中各 Agent 独立创建 MCP 连接的资源浪费问题。

### 背景问题

用户提出三个架构问题：
1. 3个Agent和客户端是什么关系？
2. 为什么在CLI中调用agent循环，但各自还要创建MCP server？
3. Agent设计是否与regreader的整体架构适配？

分析后发现原有设计的问题：
- 三个 Agent 各自独立创建 MCP 连接配置
- 无法在运行时切换传输模式
- CLI 全局 MCP 配置无法传递给 Agent

### 完成的工作

#### 1. 核心模块 (新建)

创建 `src/regreader/agents/mcp_connection.py`：

**MCPConnectionConfig** - MCP 连接配置类
```python
@dataclass
class MCPConnectionConfig:
    transport: Literal["stdio", "sse"] = "stdio"
    server_url: str | None = None
    server_name: str = MCP_SERVER_NAME

    @classmethod
    def from_settings(cls) -> MCPConnectionConfig:
        """从全局配置创建"""

    @classmethod
    def stdio(cls) -> MCPConnectionConfig:
        """创建 stdio 模式配置"""

    @classmethod
    def sse(cls, server_url: str | None = None) -> MCPConnectionConfig:
        """创建 SSE 模式配置"""
```

**MCPConnectionManager** - MCP 连接管理器（单例模式）
```python
class MCPConnectionManager:
    def get_claude_sdk_config(self) -> dict[str, Any]:
        """获取 Claude Agent SDK 格式的 MCP 配置"""

    def get_pydantic_mcp_server(self):
        """获取 Pydantic AI 的 MCP Server 对象"""

    def get_langgraph_client(self) -> RegReaderMCPClient:
        """获取 LangGraph 使用的 MCP 客户端"""
```

**便捷函数**
```python
def get_mcp_manager(config: MCPConnectionConfig | None = None) -> MCPConnectionManager
def configure_mcp(transport: Literal["stdio", "sse"] = "stdio", server_url: str | None = None) -> None
```

#### 2. Agent 改造

为三个 Agent 添加 `mcp_config` 参数：

**ClaudeAgent** (`src/regreader/agents/claude_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_claude_sdk_config()` 获取配置
- SSE 模式自动回退到 stdio（Claude SDK 限制）

**PydanticAIAgent** (`src/regreader/agents/pydantic_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_pydantic_mcp_server()` 获取 MCP Server
- 支持 stdio 和 SSE 两种模式

**LangGraphAgent** (`src/regreader/agents/langgraph_agent.py`)
- 添加 `mcp_config: MCPConnectionConfig | None = None` 参数
- 使用 `self._mcp_manager.get_langgraph_client()` 获取 MCP Client
- 完整支持 stdio 和 SSE 两种模式

#### 3. CLI 集成

修改 `src/regreader/cli.py` 的 `chat` 命令：
```python
# 构建 MCP 配置（从全局状态）
if state.mcp_transport == "sse" and state.mcp_url:
    mcp_config = MCPConnectionConfig.sse(state.mcp_url)
else:
    mcp_config = MCPConnectionConfig.stdio()

# 传递给 Agent
agent = ClaudeAgent(reg_id=reg_id, mcp_config=mcp_config)
```

#### 4. 模块导出

更新 `src/regreader/agents/__init__.py`：
```python
from .mcp_connection import MCPConnectionConfig, MCPConnectionManager, configure_mcp, get_mcp_manager

__all__ = [
    # ... existing exports ...
    # MCP Connection
    "MCPConnectionConfig",
    "MCPConnectionManager",
    "configure_mcp",
    "get_mcp_manager",
]
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/agents/mcp_connection.py` | 新建 - MCPConnectionConfig + MCPConnectionManager |
| `src/regreader/agents/claude_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/regreader/agents/pydantic_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/regreader/agents/langgraph_agent.py` | 添加 mcp_config 参数，使用统一管理器 |
| `src/regreader/agents/__init__.py` | 导出新的 MCP 连接管理类 |
| `src/regreader/cli.py` | chat 命令传递 MCP 配置 |
| `tests/dev/test_mcp_connection.py` | 新建 - 13 个单元测试 |

### 测试结果

```
tests/dev/test_mcp_connection.py - 13 passed
```

测试覆盖：
- ✅ MCPConnectionConfig 默认配置
- ✅ stdio/sse 工厂方法
- ✅ 单例模式
- ✅ 配置覆盖
- ✅ Claude SDK 配置获取（含 SSE 回退）
- ✅ LangGraph 客户端获取
- ✅ configure_mcp 便捷函数

### 使用示例

```python
# 方式1: 使用默认配置（stdio）
agent = ClaudeAgent(reg_id="angui_2024")

# 方式2: 显式指定 stdio 配置
from regreader.agents import MCPConnectionConfig
config = MCPConnectionConfig.stdio()
agent = ClaudeAgent(reg_id="angui_2024", mcp_config=config)

# 方式3: 使用 SSE 配置
config = MCPConnectionConfig.sse("http://localhost:8080/sse")
agent = LangGraphAgent(reg_id="angui_2024", mcp_config=config)

# 方式4: 全局配置
from regreader.agents import configure_mcp
configure_mcp(transport="sse", server_url="http://localhost:8080/sse")
agent = PydanticAIAgent(reg_id="angui_2024")  # 自动使用 SSE
```

### 架构关系说明

```
CLI (regreader chat)
    │
    ├─→ MCPConnectionConfig.sse() / .stdio()
    │
    └─→ Agent.__init__(mcp_config=...)
            │
            └─→ MCPConnectionManager (单例)
                    │
                    ├─→ get_claude_sdk_config()    → Claude SDK
                    ├─→ get_pydantic_mcp_server()  → Pydantic AI
                    └─→ get_langgraph_client()     → LangGraph
                            │
                            └─→ RegReaderMCPClient
                                    │
                                    └─→ MCP Server (stdio/sse)
                                            │
                                            └─→ PageStore
```

### 设计决策

1. **单例模式**：MCPConnectionManager 使用单例确保全局配置一致性
2. **框架适配**：每个框架使用独立的适配方法，保持原生特性
3. **SSE 回退**：Claude SDK 不支持 SSE 时自动回退到 stdio，并记录警告
4. **向后兼容**：不传 mcp_config 时使用默认 stdio 配置

### 后续建议

1. 考虑添加连接池复用机制（多 Agent 共享连接）
2. 监控 MCP 连接状态，实现自动重连
3. 添加 MCP 调用超时配置

---

## 2025-12-30 MCP 模式支持与 Makefile 更新

### 会话概述

实现了 CLI 的 MCP 模式支持，允许通过全局 `--mcp` 选项使用 MCP 协议调用工具。同时更新 Makefile 支持便捷切换 local/mcp-stdio/mcp-sse 模式，并修复了 SSE 连接的 502 Bad Gateway 问题。

### 完成的工作

#### 1. CLI MCP 模式支持

添加全局选项支持 MCP 远程调用：

```bash
# stdio 模式（自动启动子进程）
regreader --mcp list

# SSE 模式（连接外部服务器）
regreader --mcp --mcp-transport sse --mcp-url http://localhost:8080/sse list
```

新增文件：
- `src/regreader/mcp/protocol.py` - MCP 模式配置 dataclass
- `src/regreader/mcp/factory.py` - 工具工厂，根据模式创建本地或远程工具
- `src/regreader/mcp/adapter.py` - MCP 工具适配器，封装异步 MCP 调用为同步接口

#### 2. Makefile 模式切换支持

新增 MODE 变量实现便捷模式切换：

```makefile
# 可选值: local (默认), mcp-stdio, mcp-sse
MODE ?= local
MCP_URL ?= http://127.0.0.1:8080/sse

ifeq ($(MODE),mcp-stdio)
    MCP_FLAGS := --mcp
else ifeq ($(MODE),mcp-sse)
    MCP_FLAGS := --mcp --mcp-transport sse --mcp-url $(MCP_URL)
else
    MCP_FLAGS :=
endif
```

使用示例：
```bash
make list                        # 本地模式
make list MODE=mcp-stdio         # MCP stdio 模式
make list MODE=mcp-sse           # MCP SSE 模式

# 便捷快捷方式
make list-mcp                    # 等价于 MODE=mcp-stdio
make list-mcp-sse                # 等价于 MODE=mcp-sse
```

更新了 15 个业务命令 target 添加 `$(MCP_FLAGS)` 支持。

#### 3. Server 端口配置修复

修复了 `make serve` 端口参数不生效的问题：

- 问题：FastMCP 需要在构造函数中设置 host/port，而非 run() 方法
- 解决：修改 `create_mcp_server()` 接受 host/port 参数，CLI 端动态创建服务器

修改文件：
- `src/regreader/mcp/server.py` - create_mcp_server() 添加 host/port 参数
- `src/regreader/cli.py` - serve 命令动态创建服务器

#### 4. SSE 502 Bad Gateway 修复

修复了 MCP SSE 模式返回 502 错误的问题：

- 根因：httpx 默认 `trust_env=True` 会读取 HTTP_PROXY 环境变量
- 表现：SSE 请求经过代理后返回 502，但 curl 直接请求正常
- 解决：在 `adapter.py` 中添加自定义 httpx 客户端工厂，设置 `trust_env=False`

```python
def _no_proxy_httpx_client_factory(**kwargs) -> httpx.AsyncClient:
    """创建不使用环境代理的 httpx AsyncClient"""
    return httpx.AsyncClient(trust_env=False, **kwargs)

# 使用自定义工厂
transport = await stack.enter_async_context(
    sse_client(self.server_url, httpx_client_factory=_no_proxy_httpx_client_factory)
)
```

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/mcp/protocol.py` | 新建 - MCP 模式配置 dataclass |
| `src/regreader/mcp/factory.py` | 新建 - 工具工厂 |
| `src/regreader/mcp/adapter.py` | 新建 - MCP 工具适配器 + trust_env 修复 |
| `src/regreader/mcp/server.py` | create_mcp_server() 添加 host/port 参数 |
| `src/regreader/cli.py` | 添加全局 --mcp 选项，修改 serve 命令 |
| `Makefile` | 添加 MODE/MCP_FLAGS 变量，更新业务命令 |

### 测试结果

- ✅ `make list MODE=mcp-sse` - SSE 模式列出规程正常
- ✅ `make toc MODE=mcp-sse REG_ID=angui_2024` - SSE 模式获取目录正常
- ✅ `make serve PORT=8080` - 服务器正确监听 8080 端口
- ✅ `make list-mcp` - stdio 快捷方式正常

---

## 2024-12-29 MCP工具集扩展与CLI命令实现

### 会话概述

完成了MCP工具集的扩展实现，包括8个新工具的开发、CLI命令接口创建和Makefile更新。

### 完成的工作

#### 1. MCP工具集实现 (8个新工具)

**Phase 1: 核心多跳工具 (P0)**
- `lookup_annotation` - 注释查找（支持"注1"、"方案A"等变体匹配）
- `search_tables` - 表格搜索（按标题或单元格内容搜索）
- `resolve_reference` - 交叉引用解析（解析"见第六章"、"参见表6-2"等）

**Phase 2: 上下文工具 (P1)**
- `search_annotations` - 注释搜索（搜索所有匹配的注释）
- `get_table_by_id` - 获取完整表格（含跨页合并）
- `get_block_with_context` - 获取块上下文

**Phase 3: 发现工具 (P2)**
- `find_similar_content` - 相似内容发现
- `compare_sections` - 章节比较

#### 2. CLI命令接口 (12个新命令)

为所有MCP工具创建了对应的CLI命令，便于直接测试：

| 命令 | 功能 |
|------|------|
| `toc` | 获取规程目录树（增强版，带树状显示） |
| `read-pages` | 读取页面范围 |
| `chapter-structure` | 获取章节结构 |
| `page-info` | 获取页面章节信息 |
| `lookup-annotation` | 注释查找 |
| `search-tables` | 表格搜索 |
| `resolve-reference` | 交叉引用解析 |
| `search-annotations` | 注释搜索 |
| `get-table` | 获取完整表格 |
| `get-block-context` | 获取块上下文 |
| `find-similar` | 相似内容发现 |
| `compare-sections` | 章节比较 |

#### 3. TOC命令显示增强

使用Rich库实现美观的树状显示：
- 层级图标: 📚 (根) → 📖 (章) → 📑 (节) → 📄 (条) → 📝 (款) → • (项)
- 层级颜色: bold cyan → bold green → yellow → white → dim
- 页码显示 (dim cyan)
- Panel边框带标题和副标题
- 选项: `--expand/-e` 展开所有层级, `--level/-l` 最大深度
- 折叠节点指示器 [+N]
- 底部图例说明

#### 4. Makefile更新

添加了所有新CLI命令对应的Make目标：
- 更新.PHONY声明
- 添加MCP Tools CLI节（基础工具、Phase 1-3）
- 更新help说明添加MCP Tools Testing示例

### 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/mcp/tools.py` | 新增8个工具方法 + ReferenceResolver类 |
| `src/regreader/mcp/server.py` | 注册8个新MCP工具 |
| `src/regreader/exceptions.py` | 新增3个异常类 |
| `src/regreader/agents/prompts.py` | 更新系统提示词 |
| `src/regreader/cli.py` | 新增12个CLI命令 + 增强toc命令 |
| `Makefile` | 添加新命令对应的Make目标 |

### 测试结果

- ✅ `uv run regreader --help` - 显示所有新命令
- ✅ `make help` - 显示所有Make目标
- ✅ `uv run regreader toc angui_2024` - 树状显示正常工作

### 设计文档

详细设计文档保存在: `docs/dev/MCP_TOOLS_DESIGN.md`

### 后续建议

1. 使用实际数据对所有CLI命令进行集成测试
2. 根据测试结果调整工具参数和返回格式
3. 考虑为其他命令（如chapter-structure）也添加美化显示
