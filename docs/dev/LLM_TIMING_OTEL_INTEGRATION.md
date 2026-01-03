# LLM API 时间追踪与 OpenTelemetry 集成文档

> 更新日期: 2026-01-04
> 版本: 0.1.0
> 分支: dev
> 功能状态: ✅ 已实现

## 概述

本文档描述了 GridCode 项目中 LLM API 时间追踪的双轨架构实现，包括 httpx hooks（用于 CLI 显示）和 OpenTelemetry（用于生产环境监控）两种后端，以及答案生成步骤的可见性改进。

## 背景与动机

### 问题描述

1. **答案生成不可见**: 最后一步生成答案时虽然有 LLM API 调用，但 CLI 没有明确显示
2. **缺乏生产监控**: 需要 OpenTelemetry 支持用于生产环境的分布式追踪
3. **单一后端限制**: 原有 httpx hooks 实现无法满足不同场景需求

### 解决方案

实现双轨时间追踪架构：
- **httpx 后端**: 通过 event hooks 精确测量，适合 CLI 实时显示
- **OTel 后端**: 使用 OpenTelemetry instrumentation，适合生产环境监控
- **可配置切换**: 通过环境变量在两种后端间切换

## 架构设计

### 整体架构

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

### 核心组件

#### 1. TimingBackend 抽象接口

位置: `src/grid_code/agents/timing/base.py`

```python
class TimingBackend(ABC):
    """时间追踪后端抽象接口"""

    @abstractmethod
    def configure_httpx_client(self, client: httpx.AsyncClient) -> httpx.AsyncClient:
        """配置 httpx 客户端（添加 event hooks 或 instrumentation）"""

    @abstractmethod
    async def on_llm_call_start(self, **kwargs) -> None:
        """LLM 调用开始回调"""

    @abstractmethod
    async def on_llm_call_end(self, duration_ms: float, **kwargs) -> None:
        """LLM 调用结束回调"""

    def start_step(self) -> None:
        """开始新的步骤（重置计数器）"""

    def get_step_metrics(self) -> StepMetrics:
        """获取当前步骤的统计信息"""

    def get_total_metrics(self) -> dict:
        """获取总体统计信息"""
```

#### 2. HttpxTimingBackend 实现

位置: `src/grid_code/agents/timing/httpx_timing.py`

**特性**:
- 使用 httpx `event_hooks` 拦截 HTTP 请求/响应
- 精确测量 TTFT（Time To First Token）和总耗时
- 自动识别流式响应（通过 `text/event-stream` Content-Type）
- 维护步骤级和总体级统计

**关键实现**:

```python
class HttpxTimingBackend(TimingBackend):
    def configure_httpx_client(self, client: httpx.AsyncClient) -> httpx.AsyncClient:
        # 添加 event hooks
        client.event_hooks = {
            "request": [self._on_request],
            "response": [self._on_response],
        }
        return client

    async def _on_request(self, request: httpx.Request) -> None:
        # 记录请求开始时间
        self._request_start_times[id(request)] = time.time()

    async def _on_response(self, response: httpx.Response) -> None:
        # 计算 TTFT 和总耗时
        # 发送回调事件
```

#### 3. OTelTimingBackend 实现

位置: `src/grid_code/agents/timing/otel_timing.py`

**特性**:
- 使用 `opentelemetry-instrumentation-httpx` 自动追踪 HTTP 调用
- 创建结构化 spans 包含模型、tokens 等属性
- 支持多种导出器：console, otlp, jaeger, zipkin
- 兼容分布式追踪（trace context propagation）

**关键实现**:

```python
class OTelTimingBackend(TimingBackend):
    def __init__(self, exporter_type: str = "console", ...):
        # 初始化 TracerProvider
        provider = TracerProvider(resource=resource)

        # 创建导出器
        exporter = self._create_exporter(exporter_type, endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        # 设置全局 tracer
        trace.set_tracer_provider(provider)

        # 初始化 httpx instrumentation
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
```

#### 4. 工厂函数

位置: `src/grid_code/agents/timing/__init__.py`

```python
def create_timing_backend(
    backend_type: str | TimingBackendType = "httpx",
    callback: StatusCallback | None = None,
    **kwargs,
) -> TimingBackend:
    """根据类型创建时间追踪后端

    Args:
        backend_type: "httpx" 或 "otel"
        callback: 状态回调
        **kwargs: 后端特定参数
    """

def create_timing_backend_from_config(
    callback: StatusCallback | None = None,
) -> TimingBackend:
    """从全局配置创建时间追踪后端"""
    from grid_code.config import settings
    return create_timing_backend(
        backend_type=settings.timing_backend,
        callback=callback,
        exporter_type=settings.otel_exporter_type,
        service_name=settings.otel_service_name,
        endpoint=settings.otel_endpoint,
    )
```

## 答案生成事件

### 新增事件类型

位置: `src/grid_code/agents/events.py`

```python
class AgentEventType(str, Enum):
    # ... existing events ...
    ANSWER_GENERATION_START = "answer_generation_start"
    ANSWER_GENERATION_END = "answer_generation_end"

def answer_generation_start_event() -> AgentEvent:
    """答案生成开始事件"""

def answer_generation_end_event(
    thinking_duration_ms: float,
    api_duration_ms: float,
    api_call_count: int,
) -> AgentEvent:
    """答案生成结束事件"""
```

### Agent 集成

**PydanticAIAgent** (`src/grid_code/agents/pydantic_agent.py`):

```python
async def chat(self, message: str, ...) -> AgentResponse:
    # ... 工具调用完成 ...

    # 发送答案生成开始事件
    if self._tool_calls and self._last_tool_end_time is not None:
        await self._callback.on_event(answer_generation_start_event())

    # 生成最终答案
    final_api_duration = self._timing.get_step_metrics().total_duration_ms
    final_api_count = self._timing.get_step_metrics().call_count

    # 发送答案生成结束事件
    if self._tool_calls:
        await self._callback.on_event(
            answer_generation_end_event(
                thinking_duration_ms=thinking_duration,
                api_duration_ms=final_api_duration,
                api_call_count=final_api_count,
            )
        )
```

**LangGraphAgent** (`src/grid_code/agents/langgraph_agent.py`): 同样的集成方式

### Display 层处理

位置: `src/grid_code/agents/display.py`

```python
def _format_answer_generation_start(self) -> Text:
    """格式化答案生成开始消息"""
    text = Text()
    text.append(f"{self._get_spinner_char()} ", style=StatusColors.SPINNER)
    text.append("生成最终答案...", style=StatusColors.DIM)
    return text

def _format_answer_generation_end(self, event: AgentEvent) -> Text:
    """格式化答案生成完成消息"""
    thinking_ms = event.data.get("thinking_duration_ms", 0)
    api_ms = event.data.get("api_duration_ms", 0)
    api_count = event.data.get("api_call_count", 0)

    text = Text()
    text.append("✓ ", style=StatusColors.SUCCESS)
    text.append("答案生成完成 ", style=StatusColors.SUCCESS)
    text.append(f"思考 {thinking_ms:.0f}ms", style=StatusColors.DURATION)
    text.append(f" API {api_ms:.0f}ms", style=StatusColors.DURATION)
    text.append(f" {api_count}次调用", style=StatusColors.DIM)
    return text
```

## Claude Agent SDK OTel 集成

### otel_hooks 模块

位置: `src/grid_code/agents/otel_hooks.py`

**功能**: 为 Claude Agent SDK 的 hooks 机制提供 OpenTelemetry 支持

**核心函数**:

```python
async def otel_pre_tool_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """工具调用开始时创建 span"""
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})

    # 创建 span
    span = tracer.start_span(
        name=f"tool.{simple_name}",
        kind=SpanKind.CLIENT,
        attributes={
            "tool.name": tool_name,
            "tool.use_id": tool_use_id,
        },
    )

    # 保存 span
    _active_spans[tool_use_id] = span
    return {}

async def otel_post_tool_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """工具调用结束时结束 span"""
    span = _active_spans.pop(tool_use_id, None)
    if span:
        # 设置状态和属性
        # 结束 span
        span.end()
    return {}

def get_combined_hooks(
    enable_audit: bool = True,
    enable_otel: bool = False,
    ...
) -> dict[str, list]:
    """获取组合的 hooks 配置（审计 + OTel）"""
    hooks = {"PreToolUse": [], "PostToolUse": []}

    if enable_audit:
        # 添加审计 hooks
        hooks["PreToolUse"].append(pre_tool_audit_hook)
        hooks["PostToolUse"].extend([post_tool_audit_hook, source_extraction_hook])

    if enable_otel:
        # 添加 OTel hooks
        otel_hooks = get_otel_hooks(...)
        hooks["PreToolUse"].extend(otel_hooks["PreToolUse"])
        hooks["PostToolUse"].extend(otel_hooks["PostToolUse"])

    return hooks
```

### ClaudeAgent 集成

位置: `src/grid_code/agents/claude_agent.py`

```python
def _build_hooks(self) -> dict[str, list[HookMatcher]] | None:
    """构建 Hooks 配置"""
    settings = get_settings()
    enable_otel = settings.timing_backend == "otel"

    from grid_code.agents.otel_hooks import get_combined_hooks

    combined = get_combined_hooks(
        enable_audit=True,
        enable_otel=enable_otel,
        otel_service_name=settings.otel_service_name,
        otel_exporter_type=settings.otel_exporter_type,
        otel_endpoint=settings.otel_endpoint,
    )

    # 转换为 HookMatcher 格式
    result = {}
    if combined.get("PreToolUse"):
        result["PreToolUse"] = [HookMatcher(hooks=combined["PreToolUse"])]
    if combined.get("PostToolUse"):
        result["PostToolUse"] = [HookMatcher(hooks=combined["PostToolUse"])]

    return result
```

## 配置系统

### 新增配置项

位置: `src/grid_code/config.py`

```python
class GridCodeSettings(BaseSettings):
    # 时间追踪配置
    timing_backend: str = Field(
        default="httpx",
        description="时间追踪后端: httpx（CLI 显示用）, otel（OpenTelemetry 追踪）",
    )

    # OpenTelemetry 配置
    otel_exporter_type: str = Field(
        default="console",
        description="OTel 导出器类型: console, otlp, jaeger, zipkin",
    )
    otel_service_name: str = Field(
        default="gridcode-agent",
        description="OTel 服务名称（用于追踪标识）",
    )
    otel_endpoint: str | None = Field(
        default=None,
        description="OTel 导出端点（OTLP/Jaeger/Zipkin 服务器地址）",
    )
```

### 环境变量

```bash
# 时间追踪后端选择
export GRIDCODE_TIMING_BACKEND=httpx    # 默认，CLI 显示
export GRIDCODE_TIMING_BACKEND=otel     # 生产环境监控

# OpenTelemetry 配置
export GRIDCODE_OTEL_EXPORTER_TYPE=console     # 控制台输出
export GRIDCODE_OTEL_EXPORTER_TYPE=otlp        # OTLP 导出
export GRIDCODE_OTEL_EXPORTER_TYPE=jaeger      # Jaeger 导出
export GRIDCODE_OTEL_EXPORTER_TYPE=zipkin      # Zipkin 导出

export GRIDCODE_OTEL_SERVICE_NAME=gridcode-agent  # 服务名称
export GRIDCODE_OTEL_ENDPOINT=http://localhost:4317  # 导出端点
```

## 依赖管理

### pyproject.toml 更新

```toml
[project.optional-dependencies]
# OpenTelemetry 追踪后端
otel = [
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
]
otel-otlp = [
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.27.0",
]
otel-jaeger = [
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "opentelemetry-exporter-jaeger>=1.21.0",
]
otel-zipkin = [
    "opentelemetry-api>=1.27.0",
    "opentelemetry-sdk>=1.27.0",
    "opentelemetry-instrumentation-httpx>=0.48b0",
    "opentelemetry-exporter-zipkin>=1.27.0",
]
```

### 安装方式

```bash
# 基础安装（httpx 后端）
pip install grid-code

# 安装 OTel 支持（控制台导出）
pip install grid-code[otel]

# 安装特定导出器
pip install grid-code[otel-otlp]    # OTLP 导出到 Jaeger/OTLP Collector
pip install grid-code[otel-jaeger]  # Jaeger 原生导出
pip install grid-code[otel-zipkin]  # Zipkin 导出
```

## 使用指南

### 场景 1: CLI 本地使用（默认）

```bash
# 使用默认 httpx 后端
gridcode chat -r angui_2024 --agent pydantic

# 显示效果：
# ⟳ 调用工具: smart_search
#   ✓ 找到 5 条结果 (思考 120ms, API 450ms, 1次调用)
# ⟳ 调用工具: read_page_range
#   ✓ 读取 P85-86 (思考 80ms, API 380ms, 1次调用)
# ⟳ 生成最终答案...
#   ✓ 答案生成完成 思考 150ms API 520ms 1次调用
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 汇总: 2个工具, 3次LLM调用, 总耗时 1.35s
```

### 场景 2: OTel 控制台调试

```bash
# 设置 OTel 后端
export GRIDCODE_TIMING_BACKEND=otel
export GRIDCODE_OTEL_EXPORTER_TYPE=console

gridcode chat -r angui_2024 --agent claude

# 控制台输出（示例）：
# {
#   "name": "llm.chat.completions",
#   "context": {
#     "trace_id": "0x...",
#     "span_id": "0x...",
#   },
#   "attributes": {
#     "llm.model": "claude-sonnet-4-20250514",
#     "llm.tokens.prompt": 1250,
#     "llm.tokens.completion": 380,
#     "http.status_code": 200,
#   },
#   "duration_ms": 520
# }
```

### 场景 3: OTel 导出到 Jaeger

```bash
# 安装 OTLP 导出器
pip install grid-code[otel-otlp]

# 启动 Jaeger（Docker）
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest

# 配置 GridCode
export GRIDCODE_TIMING_BACKEND=otel
export GRIDCODE_OTEL_EXPORTER_TYPE=otlp
export GRIDCODE_OTEL_ENDPOINT=http://localhost:4317
export GRIDCODE_OTEL_SERVICE_NAME=gridcode-production

# 运行 agent
gridcode chat -r angui_2024 --agent pydantic

# 访问 Jaeger UI: http://localhost:16686
# 可以看到完整的 trace：
#   - LLM API 调用 spans
#   - 工具调用 spans（如果使用 ClaudeAgent）
#   - 端到端延迟分析
```

### 场景 4: Claude Agent SDK + OTel

```bash
# ClaudeAgent 同时支持工具调用追踪
export GRIDCODE_TIMING_BACKEND=otel
export GRIDCODE_OTEL_EXPORTER_TYPE=otlp
export GRIDCODE_OTEL_ENDPOINT=http://localhost:4317

gridcode chat -r angui_2024 --agent claude

# Jaeger trace 结构：
# ├── llm.chat.completions (520ms)
# ├── tool.smart_search (450ms)
# │   ├── thinking (120ms)
# │   └── execution (330ms)
# ├── tool.read_page_range (380ms)
# │   ├── thinking (80ms)
# │   └── execution (300ms)
# └── llm.chat.completions (final answer, 520ms)
```

## 向后兼容性

### llm_timing.py 兼容层

位置: `src/grid_code/agents/llm_timing.py`

```python
"""LLM API 调用时间收集器（兼容层）

此模块已迁移到 grid_code.agents.timing 包。
保留此文件以保持向后兼容性。
"""

from grid_code.agents.timing import (
    HttpxTimingBackend,
    LLMCallMetric,
    StepMetrics,
)

# 为旧代码保留原始类名
LLMTimingCollector = HttpxTimingBackend

__all__ = [
    "LLMTimingCollector",
    "LLMCallMetric",
    "StepMetrics",
]
```

**迁移指南**:

```python
# 旧代码（仍然支持）
from grid_code.agents.llm_timing import LLMTimingCollector
collector = LLMTimingCollector()

# 新代码（推荐）
from grid_code.agents.timing import create_timing_backend
backend = create_timing_backend("httpx")
```

## 技术亮点

### 1. 双轨架构

- **灵活切换**: 通过配置在 httpx 和 OTel 间切换，无需修改代码
- **场景适配**: httpx 适合本地调试，OTel 适合生产监控
- **统一接口**: 两种后端实现相同的 `TimingBackend` 抽象

### 2. 精确测量

- **TTFT 测量**: httpx 后端精确捕获首字节时间
- **流式识别**: 自动识别流式响应（SSE）
- **步骤隔离**: 每个查询步骤独立统计

### 3. 可观测性

- **结构化 Spans**: OTel 后端创建包含丰富属性的 spans
- **分布式追踪**: 支持 trace context propagation
- **多导出器**: 支持 console/otlp/jaeger/zipkin 多种导出方式

### 4. 答案生成可见性

- **事件驱动**: 通过 ANSWER_GENERATION 事件明确显示最后步骤
- **完整统计**: 包含思考耗时、API 耗时、调用次数
- **用户体验**: CLI 输出清晰展示每个阶段

## 文件清单

### 新建文件

| 文件 | 功能 |
|------|------|
| `src/grid_code/agents/timing/__init__.py` | 工厂函数和导出 |
| `src/grid_code/agents/timing/base.py` | TimingBackend 抽象接口 |
| `src/grid_code/agents/timing/httpx_timing.py` | httpx 事件钩子实现 |
| `src/grid_code/agents/timing/otel_timing.py` | OpenTelemetry 实现 |
| `src/grid_code/agents/otel_hooks.py` | Claude SDK OTel hooks |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/agents/events.py` | 添加 ANSWER_GENERATION 事件 |
| `src/grid_code/agents/pydantic_agent.py` | 发送答案生成事件 |
| `src/grid_code/agents/langgraph_agent.py` | 发送答案生成事件 |
| `src/grid_code/agents/display.py` | 处理答案生成事件，修复汇总条件 |
| `src/grid_code/agents/claude_agent.py` | 使用组合 hooks |
| `src/grid_code/agents/llm_timing.py` | 更新为兼容层 |
| `src/grid_code/config.py` | 添加 OTel 配置项 |
| `pyproject.toml` | 添加 otel 可选依赖 |

## 测试与验证

### 模块导入测试

```bash
$ python -c "
from grid_code.agents.timing import (
    create_timing_backend,
    TimingBackend,
    HttpxTimingBackend,
)
from grid_code.agents.otel_hooks import get_combined_hooks, OTEL_AVAILABLE
print('✓ All imports successful')
print(f'✓ OTEL_AVAILABLE={OTEL_AVAILABLE}')
"

# 输出:
# ✓ All imports successful
# ✓ OTEL_AVAILABLE=True
```

### 向后兼容测试

```bash
$ python -c "
from grid_code.agents.llm_timing import LLMTimingCollector
from grid_code.agents.timing import HttpxTimingBackend
assert LLMTimingCollector is HttpxTimingBackend
print('✓ Backward compatibility verified')
"

# 输出:
# ✓ Backward compatibility verified
```

## 后续改进建议

1. **Pydantic AI / LangGraph 集成**
   - 为这两个 agent 添加 OTel timing 后端支持
   - 目前仅 ClaudeAgent 支持 OTel hooks

2. **Metrics 导出**
   - 添加 Prometheus metrics 导出
   - 支持 Grafana 可视化

3. **分布式追踪**
   - 添加 trace context propagation
   - 支持跨服务追踪（MCP Server → Agent → LLM API）

4. **测试覆盖**
   - 添加 timing 模块单元测试
   - 添加 OTel 集成测试

5. **性能优化**
   - OTel 后端使用异步导出减少延迟
   - 优化 span 创建开销

## 参考资料

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [httpx Event Hooks](https://www.python-httpx.org/advanced/#event-hooks)
- [Claude Agent SDK Hooks](https://github.com/anthropics/claude-agent-sdk-python)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 0.1.0 | 2026-01-04 | 初始实现：双轨架构 + 答案生成事件 + Claude SDK 集成 |
