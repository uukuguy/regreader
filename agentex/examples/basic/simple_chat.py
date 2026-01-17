"""
简单对话示例

展示如何使用 AgentEx 创建最简单的 Agent。
"""

import asyncio
from agentex.frameworks import create_agent, FrameworkType


async def main():
    """主函数"""
    # 使用工厂函数创建 Agent（API key 和 model 从环境变量读取）
    agent = create_agent(
        framework="claude",  # 可选: "claude", "pydantic", "langgraph"
        system_prompt="你是一个 helpful 的助手。",
    )

    try:
        # 单轮对话
        print("=== 单轮对话 ===")
        response = await agent.chat("你好，请介绍一下你自己。")
        print(f"Agent: {response.content}")

        # 多轮对话
        print("\n=== 多轮对话 ===")
        response2 = await agent.chat("你能做什么？")
        print(f"Agent: {response2.content}")

        # 重置对话
        await agent.reset()
        print("\n对话已重置")

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
