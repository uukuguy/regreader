"""结构化日志系统

提供基于 loguru 的结构化日志功能，支持：
- trace_id 追踪完整请求链路
- 上下文信息自动注入
- JSON 格式输出
- 日志分级（DEBUG / INFO / WARNING / ERROR）
"""

import contextvars
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

# 上下文变量：存储当前请求的 trace_id
_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)

# 上下文变量：存储当前 agent_id
_agent_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agent_id", default=None
)


class StructuredLogger:
    """结构化日志记录器

    特性：
    - 自动注入 trace_id 和 agent_id
    - 支持 JSON 格式输出
    - 支持文件和控制台双输出
    - 支持日志分级过滤
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        json_format: bool = False,
        level: str = "INFO",
    ):
        """初始化结构化日志记录器

        Args:
            log_dir: 日志目录（None 表示只输出到控制台）
            json_format: 是否使用 JSON 格式
            level: 日志级别（DEBUG / INFO / WARNING / ERROR）
        """
        self.log_dir = log_dir
        self.json_format = json_format
        self.level = level

        # 移除默认 handler
        logger.remove()

        # 添加控制台 handler
        self._add_console_handler()

        # 添加文件 handler（如果指定了日志目录）
        if log_dir:
            self._add_file_handler()

    def _add_console_handler(self):
        """添加控制台 handler"""
        if self.json_format:
            # JSON 格式
            logger.add(
                sys.stderr,
                format=self._json_formatter,
                level=self.level,
                colorize=False,
            )
        else:
            # 人类可读格式 - 使用自定义格式化函数处理可选字段
            def format_func(record):
                trace_id = record["extra"].get("trace_id", "N/A")
                agent_id = record["extra"].get("agent_id", "N/A")
                # 转义消息中的花括号，避免格式化错误
                message = str(record["message"]).replace("{", "{{").replace("}", "}}")
                return (
                    f"<green>{record['time']:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                    f"<level>{record['level'].name: <8}</level> | "
                    f"<cyan>{trace_id}</cyan> | "
                    f"<blue>{agent_id}</blue> | "
                    f"<level>{message}</level>\n"
                )

            logger.add(
                sys.stderr,
                format=format_func,
                level=self.level,
                colorize=True,
            )

    def _add_file_handler(self):
        """添加文件 handler"""
        if not self.log_dir:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 按日期轮转的日志文件
        log_file = self.log_dir / "regreader_{time:YYYY-MM-DD}.log"

        if self.json_format:
            # JSON 格式
            logger.add(
                log_file,
                format=self._json_formatter,
                level=self.level,
                rotation="00:00",  # 每天轮转
                retention="30 days",  # 保留 30 天
                compression="zip",  # 压缩旧日志
            )
        else:
            # 人类可读格式 - 使用自定义格式化函数处理可选字段
            def format_func(record):
                trace_id = record["extra"].get("trace_id", "N/A")
                agent_id = record["extra"].get("agent_id", "N/A")
                # 转义消息中的花括号，避免格式化错误
                message = str(record["message"]).replace("{", "{{").replace("}", "}}")
                return (
                    f"{record['time']:YYYY-MM-DD HH:mm:ss.SSS} | "
                    f"{record['level'].name: <8} | "
                    f"{trace_id} | "
                    f"{agent_id} | "
                    f"{record['name']}:{record['function']}:{record['line']} - {message}\n"
                )

            logger.add(
                log_file,
                format=format_func,
                level=self.level,
                rotation="00:00",
                retention="30 days",
                compression="zip",
            )

    def _json_formatter(self, record: dict) -> str:
        """JSON 格式化器"""
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "trace_id": record["extra"].get("trace_id", "N/A"),
            "agent_id": record["extra"].get("agent_id", "N/A"),
            "module": record["name"],
            "function": record["function"],
            "line": record["line"],
            "message": record["message"],
        }

        # 添加异常信息（如果有）
        if record["exception"]:
            log_entry["exception"] = {
                "type": record["exception"].type.__name__,
                "value": str(record["exception"].value),
                "traceback": record["exception"].traceback,
            }

        return json.dumps(log_entry, ensure_ascii=False) + "\n"


# === 上下文管理函数 ===


def set_trace_id(trace_id: str | None = None) -> str:
    """设置当前请求的 trace_id

    Args:
        trace_id: trace_id（None 表示自动生成）

    Returns:
        设置的 trace_id
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    """获取当前请求的 trace_id

    Returns:
        trace_id（如果未设置则返回 "N/A"）
    """
    return _trace_id_var.get() or "N/A"


def set_agent_id(agent_id: str):
    """设置当前 agent_id

    Args:
        agent_id: agent_id
    """
    _agent_id_var.set(agent_id)


def get_agent_id() -> str:
    """获取当前 agent_id

    Returns:
        agent_id（如果未设置则返回 "N/A"）
    """
    return _agent_id_var.get() or "N/A"


def bind_context(**kwargs: Any) -> logger:
    """绑定上下文信息到日志

    Args:
        **kwargs: 要绑定的上下文信息

    Returns:
        绑定了上下文的 logger
    """
    # 自动注入 trace_id 和 agent_id
    context = {
        "trace_id": get_trace_id(),
        "agent_id": get_agent_id(),
        **kwargs,
    }
    return logger.bind(**context)


# === 全局 logger 实例 ===

_global_logger: StructuredLogger | None = None


def get_logger(
    log_dir: Path | None = None,
    json_format: bool = False,
    level: str = "INFO",
) -> logger:
    """获取全局 logger 实例

    Args:
        log_dir: 日志目录
        json_format: 是否使用 JSON 格式
        level: 日志级别

    Returns:
        配置好的 logger 实例
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = StructuredLogger(
            log_dir=log_dir,
            json_format=json_format,
            level=level,
        )

    return bind_context()


# === 使用示例 ===

if __name__ == "__main__":
    # 初始化 logger
    log = get_logger(level="DEBUG")

    # 设置 trace_id
    trace_id = set_trace_id()
    set_agent_id("orchestrator-001")

    # 记录日志
    log.info(f"Request started with trace_id: {trace_id}")
    log.debug("Processing subtasks...")
    log.warning("Subtask execution took longer than expected")

    try:
        raise ValueError("Test exception")
    except Exception as e:
        log.error(f"Error occurred: {e}")
