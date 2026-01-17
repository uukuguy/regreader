"""
LangGraph 集成示例

展示如何直接使用 LangGraph 风格的 AgentEx。
"""

import asyncio
from agentex.frameworks import create_agent


async def main():
    """主函数"""
    # API key 和 model 从环境变量读取（OPENAI_*）

    print("=" * 60)
    print("LangGraph 集成示例")
    print("=" * 60)

    # === 示例1: 使用工厂函数创建 LangGraph Agent ===
    print("\n--- 基础 LangGraph Agent ---\n")

    agent = create_agent(
        framework="langgraph",
        system_prompt="你是一个helpful的AI助手。",
    )

    response = await agent.chat("你好，请介绍一下你自己。")
    print(f"Agent: {response.content}")

    # === 示例2: 自定义系统提示词 ===
    print("\n--- 自定义系统提示词 ---\n")

    agent2 = create_agent(
        framework="langgraph",
        system_prompt="你是一个专业的顾问。擅长提供生活和工作建议。",
    )

    response2 = await agent2.chat("如何在工作中提高效率？")
    print(f"Agent: {response2.content}")

    # === 示例3: 获取模型信息 ===
    print("\n--- 模型信息 ---\n")

    print(f"Agent 名称: {agent.name}")
    print(f"Agent 模型: {agent.model}")

    # === 示例4: 多轮对话 ===
    print("\n--- 多轮对话 ---\n")

    await agent.chat("我想学习游泳。")
    response3 = await agent.chat("我刚才说我想学什么？")
    print(f"Agent: {response3.content}")

    # === 示例5: 重置对话 ===
    print("\n--- 重置对话 ---\n")

    await agent.reset()
    response4 = await agent.chat("我们之前讨论过什么？")
    print(f"Agent: {response4.content}")

    # === 清理 ===
    await agent.close()
    await agent2.close()

    print("\n" + "=" * 60)
    print("LangGraph 集成示例完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
