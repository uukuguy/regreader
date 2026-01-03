"""LLM API 时间追踪模块

提供双轨时间追踪架构：
- httpx: 通过 httpx event hooks 精确测量（默认，CLI 显示用）
- otel: 通过 OpenTelemetry 追踪（生产环境，可观测性）

使用方式：
    from grid_code.agents.timing import create_timing_backend, TimingBackend

    # 使用工厂函数创建（推荐）
    backend = create_timing_backend("httpx")

    # 或直接使用配置
    from grid_code.config import settings
    backend = create_timing_backend_from_config()

    # 配置 httpx client
    http_client = backend.configure_httpx_client(httpx.AsyncClient(...))

    # 获取统计
    metrics = backend.get_step_metrics()
"""

from typing import TYPE_CHECKING

from grid_code.agents.timing.base import (
    LLMCallMetric,
    StepMetrics,
    TimingBackend,
    TimingBackendType,
)
from grid_code.agents.timing.httpx_timing import HttpxTimingBackend, LLMTimingCollector

if TYPE_CHECKING:
    from grid_code.agents.callbacks import StatusCallback


def create_timing_backend(
    backend_type: str | TimingBackendType = "httpx",
    callback: "StatusCallback | None" = None,
    **kwargs,
) -> TimingBackend:
    """创建时间追踪后端

    工厂函数，根据类型创建对应的后端实例。

    Args:
        backend_type: 后端类型（"httpx" 或 "otel"）
        callback: 状态回调（可选）
        **kwargs: 传递给后端构造函数的额外参数
            - otel 专用: exporter_type, service_name, endpoint

    Returns:
        TimingBackend 实例

    Raises:
        ValueError: 如果后端类型无效
        ImportError: 如果选择 otel 但未安装依赖

    Examples:
        # 创建 httpx 后端（默认）
        backend = create_timing_backend("httpx")

        # 创建 OTel 后端（控制台输出）
        backend = create_timing_backend("otel", exporter_type="console")

        # 创建 OTel 后端（OTLP 导出）
        backend = create_timing_backend(
            "otel",
            exporter_type="otlp",
            endpoint="http://localhost:4317",
        )
    """
    # 标准化类型
    if isinstance(backend_type, str):
        backend_type = backend_type.lower()
        if backend_type == "httpx":
            backend_type = TimingBackendType.HTTPX
        elif backend_type == "otel":
            backend_type = TimingBackendType.OTEL
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")

    if backend_type == TimingBackendType.HTTPX:
        return HttpxTimingBackend(callback=callback)

    elif backend_type == TimingBackendType.OTEL:
        # 延迟导入 OTel 后端（可选依赖）
        try:
            from grid_code.agents.timing.otel_timing import OTelTimingBackend
        except ImportError as e:
            raise ImportError(
                "OpenTelemetry timing backend requires additional dependencies. "
                "Install with: pip install grid-code[otel]"
            ) from e

        return OTelTimingBackend(
            exporter_type=kwargs.get("exporter_type", "console"),
            service_name=kwargs.get("service_name", "gridcode-agent"),
            endpoint=kwargs.get("endpoint"),
            callback=callback,
        )

    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


def create_timing_backend_from_config(
    callback: "StatusCallback | None" = None,
) -> TimingBackend:
    """根据配置创建时间追踪后端

    从 settings 读取配置，自动创建对应的后端实例。

    Args:
        callback: 状态回调（可选）

    Returns:
        TimingBackend 实例
    """
    from grid_code.config import settings

    return create_timing_backend(
        backend_type=settings.timing_backend,
        callback=callback,
        exporter_type=settings.otel_exporter_type,
        service_name=settings.otel_service_name,
        endpoint=settings.otel_endpoint,
    )


__all__ = [
    # 基础类型
    "TimingBackend",
    "TimingBackendType",
    "LLMCallMetric",
    "StepMetrics",
    # 后端实现
    "HttpxTimingBackend",
    "LLMTimingCollector",  # 向后兼容
    # 工厂函数
    "create_timing_backend",
    "create_timing_backend_from_config",
]
