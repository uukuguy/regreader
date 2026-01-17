"""
自定义路由示例

展示如何创建自定义的任务路由策略。
"""

import asyncio
from typing import Callable, Awaitable, Any
from dataclasses import dataclass
from agentex.frameworks import create_agent


@dataclass
class Task:
    """任务定义"""
    id: str
    type: str
    priority: int
    content: str


class TaskRouter:
    """任务路由器基类"""

    def __init__(self):
        self.routes: dict[str, list[Callable]] = {}

    def register(self, task_type: str, handler: Callable[[Task], Awaitable[Any]]):
        """注册任务处理器"""
        if task_type not in self.routes:
            self.routes[task_type] = []
        self.routes[task_type].append(handler)

    async def route(self, task: Task) -> Any:
        """路由任务到对应的处理器"""
        if task.type in self.routes:
            for handler in self.routes[task_type]:
                return await handler(task)
        raise ValueError(f"未找到任务类型 {task.type} 的处理器")


class KeywordRouter:
    """基于关键词的任务路由器"""

    def __init__(self):
        self.agents: dict[str, Any] = {}

    def register_agent(self, keywords: list[str], agent):
        """注册关键词和对应的 Agent"""
        for keyword in keywords:
            self.agents[keyword] = agent

    def route(self, message: str) -> str:
        """根据消息内容路由到合适的 Agent"""
        message_lower = message.lower()

        for keyword, agent in self.agents.items():
            if keyword in message_lower:
                return agent.name

        return "default"


class PriorityRouter:
    """基于优先级的任务路由器"""

    def __init__(self):
        self.handlers: list[tuple[int, Callable]] = []

    def register(self, priority: int, handler: Callable):
        """注册处理器（按优先级排序）"""
        self.handlers.append((priority, handler))
        self.handlers.sort(key=lambda x: x[0], reverse=True)

    async def route(self, task: Task) -> Any:
        """按优先级路由任务"""
        for priority, handler in self.handlers:
            if await handler(task):
                return handler

        raise ValueError("没有可用的处理器")


class LoadBalancerRouter:
    """基于负载均衡的任务路由器"""

    def __init__(self):
        self.agents: dict[str, Any] = {}
        self.loads: dict[str, int] = {}

    def register_agent(self, name: str, agent):
        """注册 Agent"""
        self.agents[name] = agent
        self.loads[name] = 0

    def route(self) -> str:
        """选择负载最小的 Agent"""
        min_load = float('inf')
        selected = None

        for name, load in self.loads.items():
            if load < min_load:
                min_load = load
                selected = name

        if selected:
            self.loads[selected] += 1

        return selected


# 示例 Agent
class SummarizationAgent:
    """摘要 Agent"""

    def __init__(self):
        self.name = "summarization-agent"
        self.agent = create_agent(
            framework="claude",
            system_prompt="你是一个摘要专家。",
        )

    async def summarize(self, text: str) -> str:
        response = await self.agent.chat(f"请总结以下内容：{text}")
        return response.content


class TranslationAgent:
    """翻译 Agent"""

    def __init__(self):
        self.name = "translation-agent"
        self.agent = create_agent(
            framework="pydantic",
            system_prompt="你是一个翻译专家。",
        )

    async def translate(self, text: str, target_lang: str = "英文") -> str:
        response = await self.agent.chat(f"请将以下内容翻译成{target_lang}：{text}")
        return response.content


class AnalysisAgent:
    """分析 Agent"""

    def __init__(self):
        self.name = "analysis-agent"
        self.agent = create_agent(
            framework="langgraph",
            system_prompt="你是一个分析专家。",
        )

    async def analyze(self, text: str) -> str:
        response = await self.agent.chat(f"请分析以下内容：{text}")
        return response.content


async def main():
    """主函数"""

    print("=" * 60)
    print("自定义路由示例")
    print("=" * 60)

    # === 示例1: 关键词路由 ===
    print("\n--- 关键词路由 ---")

    summarizer = SummarizationAgent()
    translator = TranslationAgent()
    analyzer = AnalysisAgent()

    router = KeywordRouter()
    router.register_agent(["总结", "摘要", "概括"], summarizer)
    router.register_agent(["翻译", "英文", "英文"], translator)
    router.register_agent(["分析", "评估", "判断"], analyzer)

    messages = [
        "请总结这篇文章的主要内容",
        "将这段话翻译成英文",
        "分析这段文字的观点",
    ]

    for msg in messages:
        agent_name = router.route(msg)
        print(f"消息: {msg}")
        print(f"路由到: {agent_name}")

    # === 示例2: 负载均衡路由 ===
    print("\n--- 负载均衡路由 ---")

    load_router = LoadBalancerRouter()
    load_router.register_agent("agent_1", summarizer)
    load_router.register_agent("agent_2", translator)
    load_router.register_agent("agent_3", analyzer)

    for i in range(5):
        selected = load_router.route()
        print(f"请求 {i+1}: 路由到 {selected}")

    # === 示例3: 优先级路由 ===
    print("\n--- 优先级路由 ---")

    async def is_urgent(task: Task) -> bool:
        return "紧急" in task.content

    async def is_high_priority(task: Task) -> bool:
        return task.priority >= 5

    async def is_normal(task: Task) -> bool:
        return True

    priority_router = PriorityRouter()
    priority_router.register(3, is_urgent)
    priority_router.register(2, is_high_priority)
    priority_router.register(1, is_normal)

    tasks = [
        Task("t1", "normal", 3, "这是一个普通任务"),
        Task("t2", "urgent", 5, "这是一个紧急任务"),
        Task("t3", "high", 7, "这是一个高优先级任务"),
    ]

    for task in tasks:
        handler = await priority_router.route(task)
        print(f"任务 {task.id}: {task.content[:20]}...")
        print(f"  优先级: {task.priority}")
        print(f"  处理器: {handler.__name__}")

    # 清理
    await summarizer.agent.close()
    await translator.agent.close()
    await analyzer.agent.close()


if __name__ == "__main__":
    asyncio.run(main())
