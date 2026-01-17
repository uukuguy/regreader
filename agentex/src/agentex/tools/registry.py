"""工具注册表

管理工具的注册、查找和描述生成。
"""

from typing import Any

from .base import Tool


class ToolRegistry:
    """工具注册表

    管理工具的注册和查找，支持动态添加工具。
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        """注册工具

        Args:
            tool: 工具实例

        Returns:
            self（支持链式调用）
        """
        self._tools[tool.name] = tool
        return self

    def unregister(self, name: str) -> bool:
        """注销工具

        Args:
            name: 工具名称

        Returns:
            是否成功注销
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Tool | None:
        """获取工具

        Args:
            name: 工具名称

        Returns:
            工具实例，不存在返回 None
        """
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def clear(self):
        """清空所有工具"""
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def generate_descriptions(self) -> str:
        """生成工具描述（供 LLM 使用）"""
        if not self._tools:
            return "无可用工具"

        lines = ["## 可用工具:\n"]
        for tool in self._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"{tool.description}")
            lines.append(f"参数: {tool.parameters}")
            lines.append("")

        return "\n".join(lines)

    def generate_schema(self) -> list[dict[str, Any]]:
        """生成工具 schema（供 OpenAI Function Calling 使用）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in self._tools.values()
        ]


class ToolExecutor:
    """工具执行器

    协调工具的执行和结果处理。
    """

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()

    async def execute(
        self,
        tool_name: str,
        context: dict[str, Any],
        **kwargs
    ) -> Any:
        """执行工具

        Args:
            tool_name: 工具名称
            context: Agent 上下文
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            ValueError: 工具不存在
        """
        tool = self.registry.get(tool_name)
        if tool is None:
            raise ValueError(f"工具不存在: {tool_name}")

        result = await tool.execute(context, **kwargs)
        return result.output

    def add_tool(self, tool: Tool) -> "ToolExecutor":
        """添加工具

        Returns:
            self（支持链式调用）
        """
        self.registry.register(tool)
        return self
