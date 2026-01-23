"""AgentEx 异常定义

定义统一的异常层次结构。
"""


class AgentExError(Exception):
    """AgentEx 基础异常"""

    pass


class AgentError(AgentExError):
    """Agent 执行错误"""

    pass


class ToolError(AgentExError):
    """工具执行错误"""

    pass


class ConfigurationError(AgentExError):
    """配置错误"""

    pass


class ConnectionError(AgentExError):
    """连接错误"""

    pass


class TimeoutError(AgentExError):
    """超时错误"""

    pass


class ValidationError(AgentExError):
    """验证错误"""

    pass


class FrameworkNotFoundError(AgentExError):
    """框架未找到错误"""

    pass
