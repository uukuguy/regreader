"""OpenTelemetry 时间追踪后端

通过 OpenTelemetry 追踪 LLM API 调用，支持多种导出器：
- Console: 控制台输出（调试用）
- OTLP: OpenTelemetry Protocol（生产环境）
- Jaeger: Jaeger 分布式追踪
- Zipkin: Zipkin 分布式追踪

使用方式：
    backend = OTelTimingBackend(
        exporter_type="console",  # 或 "otlp", "jaeger", "zipkin"
        callback=status_callback,
    )
    http_client = backend.configure_httpx_client(httpx.AsyncClient(...))

注意：需要安装 OpenTelemetry 依赖：
    pip install grid-code[otel]
"""

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from grid_code.agents.timing.base import (
    LLMCallMetric,
    StepMetrics,
    TimingBackend,
    TimingBackendType,
)

if TYPE_CHECKING:
    import httpx

    from grid_code.agents.callbacks import StatusCallback

# 尝试导入 OpenTelemetry（可选依赖）
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentation
    from opentelemetry.trace import SpanKind, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None
    ConsoleSpanExporter = None
    BatchSpanProcessor = None
    SimpleSpanProcessor = None
    HTTPXClientInstrumentation = None


class OTelTimingBackend(TimingBackend):
    """OpenTelemetry 时间追踪后端

    通过 OpenTelemetry 追踪 API 调用，支持多种导出器。
    同时也收集统计数据供 CLI 显示使用。

    Attributes:
        exporter_type: 导出器类型（console, otlp, jaeger, zipkin）
        service_name: 服务名称（用于追踪标识）
    """

    def __init__(
        self,
        exporter_type: str = "console",
        service_name: str = "gridcode-agent",
        endpoint: str | None = None,
        callback: "StatusCallback | None" = None,
    ):
        """初始化后端

        Args:
            exporter_type: 导出器类型（console, otlp, jaeger, zipkin）
            service_name: 服务名称
            endpoint: OTLP/Jaeger/Zipkin 端点（可选）
            callback: 状态回调（可选）

        Raises:
            ImportError: 如果 OpenTelemetry 未安装
        """
        if not OTEL_AVAILABLE:
            raise ImportError(
                "OpenTelemetry is not installed. Install with: pip install grid-code[otel]"
            )

        super().__init__(TimingBackendType.OTEL, callback)

        self.exporter_type = exporter_type
        self.service_name = service_name
        self.endpoint = endpoint

        # 请求追踪（用于统计）
        self._pending: dict[int, LLMCallMetric] = {}
        self._completed: list[LLMCallMetric] = []

        # 初始化 OpenTelemetry
        self._setup_otel()

    @property
    def on_request(self):
        """Public accessor for request hook (for direct event_hooks usage)"""
        return self._on_request

    @property
    def on_response(self):
        """Public accessor for response hook (for direct event_hooks usage)"""
        return self._on_response

    def _setup_otel(self) -> None:
        """设置 OpenTelemetry TracerProvider 和 Exporter"""
        # 创建资源
        resource = Resource(attributes={SERVICE_NAME: self.service_name})

        # 创建 TracerProvider
        provider = TracerProvider(resource=resource)

        # 根据类型创建 Exporter
        exporter = self._create_exporter()

        # 使用 SimpleSpanProcessor（console）或 BatchSpanProcessor（其他）
        if self.exporter_type == "console":
            processor = SimpleSpanProcessor(exporter)
        else:
            processor = BatchSpanProcessor(exporter)

        provider.add_span_processor(processor)

        # 设置全局 TracerProvider
        trace.set_tracer_provider(provider)

        # 获取 Tracer
        self._tracer = trace.get_tracer(__name__)

        # 当前活跃的 spans
        self._active_spans: dict[int, Any] = {}

        logger.info(f"[OTelTiming] Initialized with {self.exporter_type} exporter")

    def _create_exporter(self) -> Any:
        """创建导出器

        Returns:
            OpenTelemetry Exporter 实例
        """
        if self.exporter_type == "console":
            return ConsoleSpanExporter()

        elif self.exporter_type == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                endpoint = self.endpoint or "http://localhost:4317"
                return OTLPSpanExporter(endpoint=endpoint)
            except ImportError:
                raise ImportError(
                    "OTLP exporter not installed. Install with: "
                    "pip install opentelemetry-exporter-otlp-proto-grpc"
                )

        elif self.exporter_type == "jaeger":
            try:
                from opentelemetry.exporter.jaeger.thrift import JaegerExporter

                # 解析 endpoint（格式：host:port）
                if self.endpoint:
                    host, port = self.endpoint.rsplit(":", 1)
                    return JaegerExporter(agent_host_name=host, agent_port=int(port))
                return JaegerExporter()
            except ImportError:
                raise ImportError(
                    "Jaeger exporter not installed. Install with: "
                    "pip install opentelemetry-exporter-jaeger"
                )

        elif self.exporter_type == "zipkin":
            try:
                from opentelemetry.exporter.zipkin.json import ZipkinExporter

                endpoint = self.endpoint or "http://localhost:9411/api/v2/spans"
                return ZipkinExporter(endpoint=endpoint)
            except ImportError:
                raise ImportError(
                    "Zipkin exporter not installed. Install with: "
                    "pip install opentelemetry-exporter-zipkin"
                )

        else:
            raise ValueError(f"Unknown exporter type: {self.exporter_type}")

    def configure_httpx_client(self, client: "httpx.AsyncClient") -> "httpx.AsyncClient":
        """配置 httpx 客户端以启用 OpenTelemetry 追踪

        使用 opentelemetry-instrumentation-httpx 自动注入追踪。
        同时添加自定义 hooks 来收集统计数据。

        Args:
            client: httpx 异步客户端

        Returns:
            配置后的客户端
        """
        # 使用 OpenTelemetry httpx instrumentation
        if HTTPXClientInstrumentation:
            HTTPXClientInstrumentation().instrument_client(client)

        # 添加自定义 hooks 来收集统计数据（与 httpx backend 兼容）
        existing_request_hooks = client.event_hooks.get("request", [])
        existing_response_hooks = client.event_hooks.get("response", [])

        client.event_hooks["request"] = [*existing_request_hooks, self._on_request]
        client.event_hooks["response"] = [*existing_response_hooks, self._on_response]

        return client

    async def _on_request(self, request: "httpx.Request") -> None:
        """httpx 请求发送前的回调（用于收集统计）

        Args:
            request: httpx 请求对象
        """
        request_id = id(request)

        # 获取当前 trace 和 span ID
        current_span = trace.get_current_span()
        trace_id = None
        span_id = None
        if current_span:
            ctx = current_span.get_span_context()
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")

        self._pending[request_id] = LLMCallMetric(
            start_time=time.time(),
            endpoint=str(request.url),
            trace_id=trace_id,
            span_id=span_id,
        )
        logger.debug(f"[OTelTiming] API request started: {request.url}")

    async def _on_response(self, response: "httpx.Response") -> None:
        """httpx 响应接收后的回调（用于收集统计）

        Args:
            response: httpx 响应对象
        """
        request_id = id(response.request)
        metric = self._pending.pop(request_id, None)

        if metric is None:
            logger.warning("[OTelTiming] Response without matching request")
            return

        # 计算耗时
        metric.duration_ms = (time.time() - metric.start_time) * 1000

        # 尝试提取 token 统计
        self._extract_token_usage(response, metric)

        # 记录到完成列表
        self._completed.append(metric)

        # 更新统计
        self._update_metrics(
            metric.duration_ms,
            metric.prompt_tokens,
            metric.completion_tokens,
        )

        logger.debug(
            f"[OTelTiming] API call completed: {metric.duration_ms:.0f}ms, "
            f"trace_id: {metric.trace_id}"
        )

    def _extract_token_usage(
        self, response: "httpx.Response", metric: LLMCallMetric
    ) -> None:
        """从响应中提取 token 使用信息

        Args:
            response: httpx 响应对象
            metric: 要更新的指标对象
        """
        try:
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            body = response.json()
            usage = body.get("usage", {})

            metric.prompt_tokens = usage.get("prompt_tokens")
            metric.completion_tokens = usage.get("completion_tokens")

            if model := body.get("model"):
                metric.model = model
        except Exception:
            pass

    async def on_llm_call_start(self, **kwargs: Any) -> None:
        """LLM 调用开始时的回调

        创建一个新的 OTel span。

        Args:
            **kwargs: 调用相关信息（endpoint, model 等）
        """
        call_id = kwargs.get("call_id", id(kwargs))
        endpoint = kwargs.get("endpoint", "unknown")
        model = kwargs.get("model", "unknown")

        # 创建 span
        span = self._tracer.start_span(
            name=f"llm.call.{model}",
            kind=SpanKind.CLIENT,
            attributes={
                "llm.endpoint": endpoint,
                "llm.model": model,
            },
        )
        self._active_spans[call_id] = span

    async def on_llm_call_end(
        self,
        duration_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时的回调

        结束 span 并记录统计。

        Args:
            duration_ms: 调用耗时（毫秒）
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            error: 错误信息（如果有）
            **kwargs: 其他信息
        """
        call_id = kwargs.get("call_id")
        span = self._active_spans.pop(call_id, None)

        if span:
            # 添加属性
            if prompt_tokens:
                span.set_attribute("llm.prompt_tokens", prompt_tokens)
            if completion_tokens:
                span.set_attribute("llm.completion_tokens", completion_tokens)
            span.set_attribute("llm.duration_ms", duration_ms)

            # 设置状态
            if error:
                span.set_status(Status(StatusCode.ERROR, error))
            else:
                span.set_status(Status(StatusCode.OK))

            # 结束 span
            span.end()

        # 更新统计
        self._update_metrics(duration_ms, prompt_tokens, completion_tokens)

    def reset(self) -> None:
        """重置所有统计"""
        super().reset()
        self._pending.clear()
        self._completed.clear()

    def get_completed_calls(self) -> list[LLMCallMetric]:
        """获取所有已完成的调用记录

        Returns:
            已完成的调用记录列表
        """
        return list(self._completed)

    def shutdown(self) -> None:
        """关闭 OpenTelemetry（刷新并导出所有 spans）"""
        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
        logger.info("[OTelTiming] Shutdown complete")
