"""框架集成

提供多种 Agent 框架的统一接口。
"""

# 显式导入子模块以触发框架注册
from . import claude
from . import pydantic
from . import langgraph

from .base import (
    FrameworkType,
    FrameworkFactory,
    create_agent,
)

__all__ = [
    "FrameworkType",
    "FrameworkFactory",
    "create_agent",
]
