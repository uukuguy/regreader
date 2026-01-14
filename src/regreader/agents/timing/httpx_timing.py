"""httpx 事件钩子时间追踪后端

通过 httpx event hooks 精确测量 LLM API 调用的 HTTP 往返时间。
这是默认后端，适用于 CLI 显示场景。

使用方式：
    backend = HttpxTimingBackend(callback=status_callback)
    http_client = backend.configure_httpx_client(httpx.AsyncClient(...))
"""

import time
from typing import TYPE_CHECKING, Any

from loguru import logger

from regreader.agents.timing.base import (
    LLMCallMetric,
    StepMetrics,
    TimingBackend,
    TimingBackendType,
)

if TYPE_CHECKING:
    import httpx

    from regreader.agents.callbacks import StatusCallback


class HttpxTimingBackend(TimingBackend):
    """httpx 事件钩子时间追踪后端

    通过 httpx event hooks 精确测量 API 调用时间。
    支持步骤累计模式，用于处理步骤间多次 LLM 调用的场景。

    Attributes:
        callback: 状态回调，用于发送 LLM_API_CALL 事件
    """

    def __init__(self, callback: "StatusCallback | None" = None):
        """初始化后端

        Args:
            callback: 状态回调（可选），用于实时发送事件
        """
        super().__init__(TimingBackendType.HTTPX, callback)

        # 请求追踪（request_id -> LLMCallMetric）
        self._pending: dict[int, LLMCallMetric] = {}

        # 完成的调用记录
        self._completed: list[LLMCallMetric] = []

    @property
    def on_request(self):
        """Public accessor for request hook (for direct event_hooks usage)"""
        return self._on_request

    @property
    def on_response(self):
        """Public accessor for response hook (for direct event_hooks usage)"""
        return self._on_response

    def configure_httpx_client(self, client: "httpx.AsyncClient") -> "httpx.AsyncClient":
        """配置 httpx 客户端以启用时间追踪

        通过添加 event_hooks 来拦截请求和响应。

        Args:
            client: httpx 异步客户端

        Returns:
            配置后的客户端（同一个对象，已添加 hooks）
        """
        # 添加事件钩子
        existing_request_hooks = client.event_hooks.get("request", [])
        existing_response_hooks = client.event_hooks.get("response", [])

        client.event_hooks["request"] = [*existing_request_hooks, self._on_request]
        client.event_hooks["response"] = [*existing_response_hooks, self._on_response]

        return client

    async def _on_request(self, request: "httpx.Request") -> None:
        """httpx 请求发送前的回调

        Args:
            request: httpx 请求对象
        """
        request_id = id(request)
        self._pending[request_id] = LLMCallMetric(
            start_time=time.time(),
            endpoint=str(request.url),
        )
        logger.debug(f"[HttpxTiming] API request started: {request.url}")

    async def _on_response(self, response: "httpx.Response") -> None:
        """httpx 响应接收后的回调

        Args:
            response: httpx 响应对象
        """
        request_id = id(response.request)
        metric = self._pending.pop(request_id, None)

        if metric is None:
            logger.warning("[HttpxTiming] Response without matching request")
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
            f"[HttpxTiming] API call completed: {metric.duration_ms:.0f}ms, "
            f"tokens: {metric.prompt_tokens=}/{metric.completion_tokens=}"
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
            # 检查 Content-Type
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return

            # 解析 JSON
            body = response.json()
            usage = body.get("usage", {})

            metric.prompt_tokens = usage.get("prompt_tokens")
            metric.completion_tokens = usage.get("completion_tokens")

            # 尝试提取模型名称
            if model := body.get("model"):
                metric.model = model
        except Exception:
            # 忽略解析错误（可能是流式响应或非标准格式）
            pass

    async def on_llm_call_start(self, **kwargs: Any) -> None:
        """LLM 调用开始时的回调（httpx hooks 自动处理，此方法不需要）"""
        pass

    async def on_llm_call_end(
        self,
        duration_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        error: str | None = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束时的回调（httpx hooks 自动处理，此方法不需要）"""
        pass

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


# 为了向后兼容，保留旧的类名和数据类
LLMTimingCollector = HttpxTimingBackend
