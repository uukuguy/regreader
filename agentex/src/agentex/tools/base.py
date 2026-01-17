"""工具抽象基类

定义统一的工具接口。
"""

from abc import ABC, abstractmethod
from typing import Any

from ..types import ToolResult, Context


class Tool(ABC):
    """工具抽象基类

    所有工具必须继承此类并实现 execute 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（英文，无特殊字符）"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，供 LLM 理解工具用途"""
        ...

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema 格式的参数定义"""
        return {"type": "object", "properties": {}}

    @property
    def return_type(self) -> str:
        """返回类型描述"""
        return "any"

    async def execute(self, context: Context, **kwargs: Any) -> ToolResult:
        """执行工具

        Args:
            context: Agent 上下文（包含对话历史等）
            **kwargs: 工具参数

        Returns:
            ToolResult: 执行结果
        """
        try:
            result = await self._run(context, **kwargs)
            return ToolResult(name=self.name, output=result, success=True)
        except Exception as e:
            return ToolResult(
                name=self.name,
                output=None,
                success=False,
                error=str(e)
            )

    @abstractmethod
    async def _run(self, context: Context, **kwargs: Any) -> Any:
        """实际执行逻辑（子类实现）"""
        ...

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式（供工具描述使用）"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class FunctionTool(Tool):
    """基于函数的工具

    简化工具创建，允许直接传入异步函数。
    """

    def __init__(
        self,
        name: str,
        description: str,
        func: callable,
        parameters: dict[str, Any] = None
    ):
        self._name = name
        self._description = description
        self._func = func
        self._parameters = parameters or {"type": "object", "properties": {}}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def _run(self, context: Context, **kwargs: Any) -> Any:
        return await self._func(context, **kwargs)


class ToolResultParser:
    """工具结果解析器

    统一解析不同工具的返回结果。
    """

    @staticmethod
    def parse_result(tool_name: str, result: Any) -> dict[str, Any]:
        """解析工具结果

        Args:
            tool_name: 工具名称
            result: 工具返回结果

        Returns:
            解析后的结果摘要
        """
        if result is None:
            return {"type": "null", "content": None}

        if isinstance(result, dict):
            return {
                "type": "dict",
                "keys": list(result.keys()),
                "has_source": "source" in result,
            }

        if isinstance(result, list):
            return {
                "type": "list",
                "length": len(result),
                "first_type": type(result[0]).__name__ if result else "empty",
            }

        if isinstance(result, str):
            return {
                "type": "string",
                "length": len(result),
                "preview": result[:100],
            }

        return {
            "type": type(result).__name__,
            "str_repr": str(result)[:100],
        }
