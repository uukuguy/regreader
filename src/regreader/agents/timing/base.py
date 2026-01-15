"""LLM API 时间追踪抽象接口

定义了时间追踪后端的统一接口，支持多种实现：
- HttpxTimingBackend: 通过 httpx event hooks 精确测量（默认）
- OTelTimingBackend: 通过 OpenTelemetry 追踪（生产环境）

使用方式：
    from regreader.agents.timing import create_timing_backend, TimingBackend

    # 使用工厂函数创建
    backend = create_timing_backend("httpx")  # 或 "otel"

    # 配置 httpx client
    http_client = backend.configure_httpx_client(httpx.AsyncClient(...))
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

    from regreader.agents.shared.callbacks import StatusCallback


class TimingBackendType(str, Enum):
    """时间追踪后端类型"""

    HTTPX = "httpx"  # httpx event hooks（默认，CLI 显示用）
    OTEL = "otel"  # OpenTelemetry（生产环境，可观测性）


@dataclass
class LLMCallMetric:
    """单次 LLM API 调用的指标"""

    start_time: float
    duration_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    endpoint: str = ""
    model: str = ""
    error: str | None = None
    # OTel 专用字段
    trace_id: str | None = None
    span_id: str | None = None


@dataclass
class StepMetrics:
    """单个步骤（工具调用间隔）的 API 调用统计"""

    api_calls: int = 0
    api_duration_ms: float = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0


class TimingBackend(ABC):
    """时间追踪后端抽象基类

    定义了时间追踪后端的统一接口，所有具体实现必须继承此类。

    Attributes:
        backend_type: 后端类型标识
        callback: 状态回调，用于发送事件
    """

    def __init__(
        self,
        backend_type: TimingBackendType,
        callback: "StatusCallback | None" = None,
    ):
        """初始化后端

        Args:
            backend_type: 后端类型
            callback: 状态回调（可选）
        """
        self.backend_type = backend_type
        self.callback = callback

        # 当前步骤的累计统计
        self._step_metrics = StepMetrics()

        # 全局统计
        self._total_api_calls: int = 0
        self._total_api_duration_ms: float = 0
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0

    @abstractmethod
    def configure_httpx_client(self, client: "httpx.AsyncClient") -> "httpx.AsyncClient":
        """配置 httpx 客户端以启用时间追踪

        Args:
            client: httpx 异步客户端

        Returns:
            配置后的客户端（可能是同一个对象或新对象）
        """
        ...

    @abstractmethod
    async def on_llm_call_start(self, **kwargs: Any) -> None:
        """LLM 调用开始时的回调

        Args:
            **kwargs: 调用相关信息（endpoint, model 等）
        """
        ...

    @abstractmethod
    async def on_llm_call_end(
        self,
        duration_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时的回调

        Args:
            duration_ms: 调用耗时（毫秒）
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            error: 错误信息（如果有）
            **kwargs: 其他信息
        """
        ...

    def start_step(self) -> None:
        """开始新步骤，重置步骤累计计数器

        在每个工具调用开始时调用。
        """
        self._step_metrics = StepMetrics()

    def end_step(self) -> StepMetrics:
        """结束当前步骤，返回该步骤的 API 统计

        在每个工具调用结束时调用。

        Returns:
            当前步骤的 API 调用统计
        """
        return self._step_metrics

    def get_step_metrics(self) -> StepMetrics:
        """获取当前步骤的 API 调用统计（不重置）

        Returns:
            当前步骤的 API 调用统计
        """
        return self._step_metrics

    def get_total_metrics(self) -> dict:
        """获取全局统计

        Returns:
            包含总调用次数、总耗时、总 token 数的字典
        """
        return {
            "total_api_calls": self._total_api_calls,
            "total_api_duration_ms": self._total_api_duration_ms,
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
        }

    def reset(self) -> None:
        """重置所有统计

        在新查询开始时调用。
        """
        self._step_metrics = StepMetrics()
        self._total_api_calls = 0
        self._total_api_duration_ms = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    def _update_metrics(
        self,
        duration_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        """更新步骤和全局统计

        Args:
            duration_ms: 调用耗时（毫秒）
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
        """
        # 更新步骤统计
        self._step_metrics.api_calls += 1
        self._step_metrics.api_duration_ms += duration_ms
        if prompt_tokens:
            self._step_metrics.total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self._step_metrics.total_completion_tokens += completion_tokens

        # 更新全局统计
        self._total_api_calls += 1
        self._total_api_duration_ms += duration_ms
        if prompt_tokens:
            self._total_prompt_tokens += prompt_tokens
        if completion_tokens:
            self._total_completion_tokens += completion_tokens
