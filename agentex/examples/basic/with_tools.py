"""
工具调用示例

展示如何为 Agent 添加自定义工具。
"""

import asyncio
import re
from agentex import AgentConfig
from agentex.tools import Tool
from agentex.frameworks import create_agent


class CalculatorTool(Tool):
    """计算器工具"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "执行数学计算。支持 + - * / 和括号。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2 + 3 * 4'"
                }
            },
            "required": ["expression"]
        }

    async def _run(self, context: dict, expression: str) -> str:
        """安全地计算表达式"""
        # 只允许数字和基本运算符
        if not re.match(r'^[\d\+\-\*\/\(\)\.\s]+$', expression):
            return "错误：表达式包含非法字符"

        try:
            result = eval(expression)
            return f"计算结果: {result}"
        except ZeroDivisionError:
            return "错误：除以零"
        except Exception as e:
            return f"计算错误: {e}"


async def main():
    """主函数"""
    # 使用工厂函数创建 Agent（API key 和 model 从环境变量读取）
    agent = create_agent(
        framework="claude",
        system_prompt="你是一个数学助手。请在需要时使用 calculator 工具进行计算。",
    )

    try:
        response = await agent.chat("请计算 25 * 4 + 10")
        print(f"Agent: {response.content}")

        response2 = await agent.chat("请问 100 / 7 的结果是多少？")
        print(f"Agent: {response2.content}")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
