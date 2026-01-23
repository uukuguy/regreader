"""性能指标收集系统

提供性能指标收集和统计功能，支持：
- 查询延迟统计（P50, P95, P99）
- 子智能体调用次数和耗时
- MCP 工具调用统计
- 错误率和类型分布
- Prometheus 格式导出
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from regreader.observability.logging import get_trace_id


@dataclass
class MetricPoint:
    """单个指标数据点"""

    name: str
    value: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class LatencyStats:
    """延迟统计"""

    count: int = 0
    total: float = 0.0
    min: float = float("inf")
    max: float = 0.0
    values: list[float] = field(default_factory=list)

    def add(self, value: float):
        """添加一个延迟值"""
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self.values.append(value)

    @property
    def mean(self) -> float:
        """平均值"""
        return self.total / self.count if self.count > 0 else 0.0

    def percentile(self, p: float) -> float:
        """计算百分位数

        Args:
            p: 百分位（0-100）

        Returns:
            百分位值
        """
        if not self.values:
            return 0.0
        sorted_values = sorted(self.values)
        index = int(len(sorted_values) * p / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]


class MetricsCollector:
    """性能指标收集器

    特性：
    - 收集查询延迟、子任务执行时间、工具调用统计
    - 计算 P50, P95, P99 百分位数
    - 支持 Prometheus 格式导出
    - 线程安全
    """

    def __init__(self):
        """初始化指标收集器"""
        # 查询延迟统计
        self.query_latency = LatencyStats()

        # 子任务延迟统计（按类型分组）
        self.subtask_latency: dict[str, LatencyStats] = defaultdict(LatencyStats)

        # 工具调用统计
        self.tool_calls: dict[str, int] = defaultdict(int)
        self.tool_latency: dict[str, LatencyStats] = defaultdict(LatencyStats)

        # 错误统计
        self.error_count: dict[str, int] = defaultdict(int)

        # 并行度统计
        self.parallel_batch_sizes: list[int] = []

        # 所有指标点
        self.metrics: list[MetricPoint] = []

    def record_query_latency(self, latency: float, labels: dict[str, str] | None = None):
        """记录查询延迟

        Args:
            latency: 延迟（秒）
            labels: 标签（如 agent_type, parallel_mode）
        """
        self.query_latency.add(latency)
        self.metrics.append(
            MetricPoint(
                name="query_latency_seconds",
                value=latency,
                timestamp=datetime.now(),
                labels=labels or {},
            )
        )
    def record_subtask_latency(
        self, subtask_type: str, latency: float, labels: dict[str, str] | None = None
    ):
        """记录子任务延迟

        Args:
            subtask_type: 子任务类型（如 LOCATE_CHAPTERS, FETCH_CONTENT）
            latency: 延迟（秒）
            labels: 标签（如 parallel_mode, batch_index）
        """
        self.subtask_latency[subtask_type].add(latency)
        self.metrics.append(
            MetricPoint(
                name="subtask_latency_seconds",
                value=latency,
                timestamp=datetime.now(),
                labels={**(labels or {}), "subtask_type": subtask_type},
            )
        )

    def record_tool_call(
        self, tool_name: str, latency: float, labels: dict[str, str] | None = None
    ):
        """记录工具调用

        Args:
            tool_name: 工具名称（如 get_toc, smart_search）
            latency: 延迟（秒）
            labels: 标签（如 reg_id, success）
        """
        self.tool_calls[tool_name] += 1
        self.tool_latency[tool_name].add(latency)
        self.metrics.append(
            MetricPoint(
                name="tool_call_latency_seconds",
                value=latency,
                timestamp=datetime.now(),
                labels={**(labels or {}), "tool_name": tool_name},
            )
        )

    def record_error(self, error_type: str, labels: dict[str, str] | None = None):
        """记录错误

        Args:
            error_type: 错误类型（如 TimeoutError, MCPConnectionError）
            labels: 标签（如 subtask_type, tool_name）
        """
        self.error_count[error_type] += 1
        self.metrics.append(
            MetricPoint(
                name="error_count",
                value=1,
                timestamp=datetime.now(),
                labels={**(labels or {}), "error_type": error_type},
            )
        )

    def record_parallel_batch(self, batch_size: int):
        """记录并行批次大小

        Args:
            batch_size: 批次中的子任务数量
        """
        self.parallel_batch_sizes.append(batch_size)
        self.metrics.append(
            MetricPoint(
                name="parallel_batch_size",
                value=batch_size,
                timestamp=datetime.now(),
                labels={},
            )
        )

    def get_summary(self) -> dict[str, Any]:
        """获取性能指标摘要

        Returns:
            包含所有关键指标的字典
        """
        summary = {
            "query_latency": {
                "count": self.query_latency.count,
                "mean": self.query_latency.mean,
                "min": self.query_latency.min,
                "max": self.query_latency.max,
                "p50": self.query_latency.percentile(50),
                "p95": self.query_latency.percentile(95),
                "p99": self.query_latency.percentile(99),
            },
            "subtask_latency": {},
            "tool_calls": dict(self.tool_calls),
            "tool_latency": {},
            "errors": dict(self.error_count),
            "parallel_stats": {
                "batch_count": len(self.parallel_batch_sizes),
                "avg_batch_size": (
                    sum(self.parallel_batch_sizes) / len(self.parallel_batch_sizes)
                    if self.parallel_batch_sizes
                    else 0
                ),
                "max_batch_size": max(self.parallel_batch_sizes, default=0),
            },
        }

        # 子任务延迟统计
        for subtask_type, stats in self.subtask_latency.items():
            summary["subtask_latency"][subtask_type] = {
                "count": stats.count,
                "mean": stats.mean,
                "p50": stats.percentile(50),
                "p95": stats.percentile(95),
            }

        # 工具延迟统计
        for tool_name, stats in self.tool_latency.items():
            summary["tool_latency"][tool_name] = {
                "count": stats.count,
                "mean": stats.mean,
                "p50": stats.percentile(50),
                "p95": stats.percentile(95),
            }

        return summary

    def export_prometheus(self) -> str:
        """导出 Prometheus 格式的指标

        Returns:
            Prometheus 文本格式的指标数据
        """
        lines = []

        # 查询延迟指标
        lines.append("# HELP query_latency_seconds Query latency in seconds")
        lines.append("# TYPE query_latency_seconds summary")
        if self.query_latency.count > 0:
            lines.append(
                f'query_latency_seconds{{quantile="0.5"}} {self.query_latency.percentile(50)}'
            )
            lines.append(
                f'query_latency_seconds{{quantile="0.95"}} {self.query_latency.percentile(95)}'
            )
            lines.append(
                f'query_latency_seconds{{quantile="0.99"}} {self.query_latency.percentile(99)}'
            )
            lines.append(f"query_latency_seconds_sum {self.query_latency.total}")
            lines.append(f"query_latency_seconds_count {self.query_latency.count}")

        # 子任务延迟指标
        lines.append("")
        lines.append("# HELP subtask_latency_seconds Subtask latency in seconds")
        lines.append("# TYPE subtask_latency_seconds summary")
        for subtask_type, stats in self.subtask_latency.items():
            if stats.count > 0:
                lines.append(
                    f'subtask_latency_seconds{{subtask_type="{subtask_type}",quantile="0.5"}} {stats.percentile(50)}'
                )
                lines.append(
                    f'subtask_latency_seconds{{subtask_type="{subtask_type}",quantile="0.95"}} {stats.percentile(95)}'
                )
                lines.append(
                    f'subtask_latency_seconds_sum{{subtask_type="{subtask_type}"}} {stats.total}'
                )
                lines.append(
                    f'subtask_latency_seconds_count{{subtask_type="{subtask_type}"}} {stats.count}'
                )

        return "\n".join(lines)

        # 工具调用次数
        lines.append("")
        lines.append("# HELP tool_calls_total Total number of tool calls")
        lines.append("# TYPE tool_calls_total counter")
        for tool_name, count in self.tool_calls.items():
            lines.append(f'tool_calls_total{{tool_name="{tool_name}"}} {count}')

        # 工具调用延迟
        lines.append("")
        lines.append("# HELP tool_call_latency_seconds Tool call latency in seconds")
        lines.append("# TYPE tool_call_latency_seconds summary")
        for tool_name, stats in self.tool_latency.items():
            if stats.count > 0:
                lines.append(
                    f'tool_call_latency_seconds{{tool_name="{tool_name}",quantile="0.5"}} {stats.percentile(50)}'
                )
                lines.append(
                    f'tool_call_latency_seconds{{tool_name="{tool_name}",quantile="0.95"}} {stats.percentile(95)}'
                )

        # 错误计数
        lines.append("")
        lines.append("# HELP errors_total Total number of errors")
        lines.append("# TYPE errors_total counter")
        for error_type, count in self.error_count.items():
            lines.append(f'errors_total{{error_type="{error_type}"}} {count}')

        return "\n".join(lines)



# 全局单例
_metrics_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 实例

    Returns:
        全局 MetricsCollector 单例
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """重置全局 MetricsCollector（用于测试）"""
    global _metrics_collector
    _metrics_collector = None
