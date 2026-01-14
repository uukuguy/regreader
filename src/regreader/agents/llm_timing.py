"""LLM API 调用时间收集器（兼容层）

此模块已迁移到 regreader.agents.timing 包。
保留此文件以保持向后兼容性。

新代码应使用：
    from regreader.agents.timing import (
        create_timing_backend,
        TimingBackend,
        HttpxTimingBackend,
        LLMCallMetric,
        StepMetrics,
    )
"""

# 从新模块导入，保持向后兼容
from regreader.agents.timing import (
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
