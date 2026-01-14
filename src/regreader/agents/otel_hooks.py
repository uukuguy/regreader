"""Claude Agent SDK OpenTelemetry Hooks

为 Claude Agent SDK 的工具调用创建 OpenTelemetry spans。
可以与现有的审计 hooks 配合使用，实现完整的可观测性。

使用方式：
    from regreader.agents.otel_hooks import get_otel_hooks

    hooks = get_otel_hooks(service_name="gridcode-agent")
    client = ClaudeSDKClient(hooks=hooks, ...)

注意：需要安装 OpenTelemetry 依赖：
    pip install grid-code[otel]
"""

import time
from typing import Any

from loguru import logger

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
    from opentelemetry.trace import SpanKind, Status, StatusCode

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None
    ConsoleSpanExporter = None
    BatchSpanProcessor = None
    SimpleSpanProcessor = None
    SpanKind = None
    Status = None
    StatusCode = None


# 全局 tracer 和 span 存储
_tracer = None
_active_spans: dict[str, Any] = {}
_span_start_times: dict[str, float] = {}


def setup_otel_tracer(
    service_name: str = "gridcode-agent",
    exporter_type: str = "console",
    endpoint: str | None = None,
) -> None:
    """设置 OpenTelemetry Tracer

    Args:
        service_name: 服务名称
        exporter_type: 导出器类型（console, otlp, jaeger, zipkin）
        endpoint: 导出端点（可选）

    Raises:
        ImportError: 如果 OpenTelemetry 未安装
    """
    global _tracer

    if not OTEL_AVAILABLE:
        raise ImportError(
            "OpenTelemetry is not installed. Install with: pip install grid-code[otel]"
        )

    # 创建资源
    resource = Resource(attributes={SERVICE_NAME: service_name})

    # 创建 TracerProvider
    provider = TracerProvider(resource=resource)

    # 创建导出器
    exporter = _create_exporter(exporter_type, endpoint)

    # 使用 SimpleSpanProcessor（console）或 BatchSpanProcessor（其他）
    if exporter_type == "console":
        processor = SimpleSpanProcessor(exporter)
    else:
        processor = BatchSpanProcessor(exporter)

    provider.add_span_processor(processor)

    # 设置全局 TracerProvider
    trace.set_tracer_provider(provider)

    # 获取 Tracer
    _tracer = trace.get_tracer(__name__)

    logger.info(f"[OTelHooks] Initialized with {exporter_type} exporter")


def _create_exporter(exporter_type: str, endpoint: str | None) -> Any:
    """创建导出器

    Args:
        exporter_type: 导出器类型
        endpoint: 导出端点

    Returns:
        OpenTelemetry Exporter 实例
    """
    if exporter_type == "console":
        return ConsoleSpanExporter()

    elif exporter_type == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            endpoint = endpoint or "http://localhost:4317"
            return OTLPSpanExporter(endpoint=endpoint)
        except ImportError:
            raise ImportError(
                "OTLP exporter not installed. Install with: "
                "pip install opentelemetry-exporter-otlp-proto-grpc"
            )

    elif exporter_type == "jaeger":
        try:
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter

            if endpoint:
                host, port = endpoint.rsplit(":", 1)
                return JaegerExporter(agent_host_name=host, agent_port=int(port))
            return JaegerExporter()
        except ImportError:
            raise ImportError(
                "Jaeger exporter not installed. Install with: "
                "pip install opentelemetry-exporter-jaeger"
            )

    elif exporter_type == "zipkin":
        try:
            from opentelemetry.exporter.zipkin.json import ZipkinExporter

            endpoint = endpoint or "http://localhost:9411/api/v2/spans"
            return ZipkinExporter(endpoint=endpoint)
        except ImportError:
            raise ImportError(
                "Zipkin exporter not installed. Install with: "
                "pip install opentelemetry-exporter-zipkin"
            )

    else:
        raise ValueError(f"Unknown exporter type: {exporter_type}")


async def otel_pre_tool_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """OpenTelemetry 工具调用前钩子

    在工具调用开始时创建 span。

    Args:
        input_data: 包含 tool_name 和 tool_input 的字典
        tool_use_id: 工具调用的唯一标识
        context: Hook 上下文

    Returns:
        空字典（不阻止调用）
    """
    global _tracer, _active_spans, _span_start_times

    if _tracer is None:
        return {}

    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    tool_id = tool_use_id or tool_name

    # 简化工具名
    simple_name = tool_name
    if "__" in tool_name:
        parts = tool_name.split("__")
        simple_name = parts[-1] if len(parts) > 1 else tool_name

    # 创建 span
    span = _tracer.start_span(
        name=f"tool.{simple_name}",
        kind=SpanKind.CLIENT,
        attributes={
            "tool.name": tool_name,
            "tool.simple_name": simple_name,
            "tool.use_id": tool_id,
        },
    )

    # 添加输入参数（截断长字符串）
    for key, value in tool_input.items():
        if isinstance(value, str):
            span.set_attribute(f"tool.input.{key}", value[:100])
        elif isinstance(value, (int, float, bool)):
            span.set_attribute(f"tool.input.{key}", value)

    # 保存 span 和开始时间
    _active_spans[tool_id] = span
    _span_start_times[tool_id] = time.time()

    logger.debug(f"[OTelHooks] Started span for {simple_name}")

    return {}


async def otel_post_tool_hook(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
) -> dict[str, Any]:
    """OpenTelemetry 工具调用后钩子

    在工具调用完成时结束 span。

    Args:
        input_data: 包含 tool_name、tool_input、tool_response 的字典
        tool_use_id: 工具调用的唯一标识
        context: Hook 上下文

    Returns:
        空字典
    """
    global _active_spans, _span_start_times

    tool_name = input_data.get("tool_name", "unknown")
    tool_response = input_data.get("tool_response", "")
    tool_id = tool_use_id or tool_name

    span = _active_spans.pop(tool_id, None)
    start_time = _span_start_times.pop(tool_id, None)

    if span is None:
        return {}

    # 计算耗时
    if start_time:
        duration_ms = (time.time() - start_time) * 1000
        span.set_attribute("tool.duration_ms", duration_ms)

    # 检查错误
    error_msg = None
    if isinstance(tool_response, dict) and "error" in tool_response:
        error_msg = tool_response.get("error", "未知错误")
    elif isinstance(tool_response, list) and tool_response:
        if isinstance(tool_response[0], dict) and "error" in tool_response[0]:
            error_msg = tool_response[0].get("error")

    if error_msg:
        span.set_status(Status(StatusCode.ERROR, str(error_msg)))
        span.set_attribute("tool.error", str(error_msg)[:200])
    else:
        span.set_status(Status(StatusCode.OK))

        # 添加结果摘要
        if isinstance(tool_response, dict):
            if "total_results" in tool_response:
                span.set_attribute("tool.result_count", tool_response["total_results"])
            if "source" in tool_response:
                span.set_attribute("tool.source", str(tool_response["source"]))
        elif isinstance(tool_response, list):
            span.set_attribute("tool.result_count", len(tool_response))

    # 结束 span
    span.end()

    # 简化工具名用于日志
    simple_name = tool_name
    if "__" in tool_name:
        parts = tool_name.split("__")
        simple_name = parts[-1] if len(parts) > 1 else tool_name

    logger.debug(f"[OTelHooks] Ended span for {simple_name}")

    return {}


def get_otel_hooks(
    service_name: str = "gridcode-agent",
    exporter_type: str = "console",
    endpoint: str | None = None,
) -> dict[str, list]:
    """获取 OpenTelemetry hooks 配置

    自动初始化 tracer（如果尚未初始化）并返回 hooks 配置。

    Args:
        service_name: 服务名称
        exporter_type: 导出器类型
        endpoint: 导出端点

    Returns:
        包含 PreToolUse 和 PostToolUse hooks 的字典

    Raises:
        ImportError: 如果 OpenTelemetry 未安装
    """
    global _tracer

    if not OTEL_AVAILABLE:
        raise ImportError(
            "OpenTelemetry is not installed. Install with: pip install grid-code[otel]"
        )

    # 初始化 tracer（如果需要）
    if _tracer is None:
        setup_otel_tracer(service_name, exporter_type, endpoint)

    return {
        "PreToolUse": [otel_pre_tool_hook],
        "PostToolUse": [otel_post_tool_hook],
    }


def get_combined_hooks(
    enable_audit: bool = True,
    enable_otel: bool = False,
    otel_service_name: str = "gridcode-agent",
    otel_exporter_type: str = "console",
    otel_endpoint: str | None = None,
) -> dict[str, list]:
    """获取组合的 hooks 配置

    可以同时启用审计 hooks 和 OTel hooks。

    Args:
        enable_audit: 是否启用审计 hooks
        enable_otel: 是否启用 OTel hooks
        otel_service_name: OTel 服务名称
        otel_exporter_type: OTel 导出器类型
        otel_endpoint: OTel 导出端点

    Returns:
        包含所有启用的 hooks 的字典
    """
    hooks: dict[str, list] = {"PreToolUse": [], "PostToolUse": []}

    if enable_audit:
        from regreader.agents.hooks import (
            post_tool_audit_hook,
            pre_tool_audit_hook,
            source_extraction_hook,
        )

        hooks["PreToolUse"].append(pre_tool_audit_hook)
        hooks["PostToolUse"].append(post_tool_audit_hook)
        hooks["PostToolUse"].append(source_extraction_hook)

    if enable_otel:
        if not OTEL_AVAILABLE:
            logger.warning(
                "[OTelHooks] OpenTelemetry not installed, skipping OTel hooks"
            )
        else:
            otel_hooks = get_otel_hooks(
                otel_service_name, otel_exporter_type, otel_endpoint
            )
            hooks["PreToolUse"].extend(otel_hooks["PreToolUse"])
            hooks["PostToolUse"].extend(otel_hooks["PostToolUse"])

    return hooks


def shutdown_otel() -> None:
    """关闭 OpenTelemetry（刷新并导出所有 spans）"""
    if not OTEL_AVAILABLE:
        return

    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()
    logger.info("[OTelHooks] Shutdown complete")


__all__ = [
    "setup_otel_tracer",
    "get_otel_hooks",
    "get_combined_hooks",
    "shutdown_otel",
    "otel_pre_tool_hook",
    "otel_post_tool_hook",
    "OTEL_AVAILABLE",
]
