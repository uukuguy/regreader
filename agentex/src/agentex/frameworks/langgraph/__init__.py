"""LangGraph Agent 实现

使用 LangGraph 框架实现 Agent。
"""

from typing import AsyncGenerator

from agentex.agent import BaseAgent
from agentex.config import AgentConfig
from agentex.shared import AgentMemory, StatusCallback, NullCallback
from agentex.shared.events import Event, EventType
from agentex.types import AgentResponse, AgentEvent, Context


class LangGraphAgent(BaseAgent):
    """基于 LangGraph 的 Agent 实现

    使用 LangGraph 的 StateGraph 实现复杂的工作流。
    """

    def __init__(
        self,
        config: AgentConfig,
        status_callback: StatusCallback | None = None,
    ):
        """初始化 LangGraph Agent

        Args:
            config: Agent 配置
            status_callback: 状态回调
        """
        self.config = config
        self.status_callback = status_callback or NullCallback()
        self._memory = AgentMemory() if config.memory_enabled else None

        # 初始化 LangGraph（延迟导入）
        self._init_graph()
        self._connected = False

    def _init_graph(self):
        """初始化 LangGraph"""
        try:
            from langgraph.graph import StateGraph, END, START
        except ImportError:
            raise ImportError(
                "LangGraph not installed. "
                "Run: pip install langgraph"
            )

        llm = self.config.llm
        model_name = llm.model if llm else "gpt-4"

        # 导入消息类型
        from typing import TypedDict, Annotated
        from langchain_core.messages import BaseMessage, HumanMessage
        from langgraph.graph.message import add_messages

        class AgentState(TypedDict):
            messages: Annotated[list[BaseMessage], add_messages]
            input: str
            output: str

        # 创建图
        builder = StateGraph(AgentState)

        # 添加节点
        async def call_model(state: AgentState) -> AgentState:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage

            llm_config = self.config.llm
            model = ChatOpenAI(
                model=model_name,
                api_key=llm_config.api_key if llm_config else None,
                base_url=llm_config.base_url if llm_config else None,
            )

            # 构建消息
            messages = state["messages"]
            if self.config.system_prompt:
                messages = [SystemMessage(content=self.config.system_prompt)] + messages

            response = await model.ainvoke(messages)

            return {
                **state,
                "output": response.content,
                "messages": messages + [response],
            }

        builder.add_node("call_model", call_model)
        builder.add_edge(START, "call_model")
        builder.add_edge("call_model", END)

        self._graph = builder.compile()
        self._AgentState = AgentState

    @property
    def name(self) -> str:
        """获取 Agent 名称"""
        return self.config.name

    @property
    def model(self) -> str:
        """获取模型名称"""
        return self.config.llm.model if self.config.llm else "unknown"

    async def _ensure_connected(self):
        """确保已连接"""
        if not self._connected:
            self._connected = True

    async def chat(
        self,
        message: str,
        context: Context | None = None
    ) -> AgentResponse:
        """发送消息并获取响应"""
        await self._ensure_connected()

        # 发送思考开始事件
        await self.status_callback.on_event(
            AgentEvent(event_type="thinking_start", data={"message": message})
        )

        try:
            from langchain_core.messages import HumanMessage, AIMessage

            # 构建消息列表（包含历史）
            if self._memory:
                history = self._memory.get_messages()
                messages = [
                    HumanMessage(content=item["content"]) if item["role"] == "user"
                    else AIMessage(content=item["content"])
                    for item in history
                ]
                messages.append(HumanMessage(content=message))
            else:
                messages = [HumanMessage(content=message)]

            result = await self._graph.ainvoke({
                "messages": messages,
                "input": message,
                "output": "",
            })

            output = result.get("output", "")

            # 添加用户消息到记忆（如果使用内存）
            if self._memory is not None:
                self._memory.add("user", message)

            # 添加助手回复到记忆
            if self._memory is not None:
                self._memory.add("assistant", output)

            # 发送思考结束事件
            await self.status_callback.on_event(
                AgentEvent(event_type="thinking_end", data={})
            )

            return AgentResponse(
                content=output,
                sources=[],
                metadata={"framework": "langgraph"}
            )

        except Exception as e:
            await self.status_callback.on_event(
                AgentEvent(event_type="error", data={"error": str(e)})
            )
            raise

    async def stream(
        self,
        message: str,
        context: Context | None = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式响应"""
        await self._ensure_connected()

        yield Event(EventType.THINKING_START)

        try:
            from langchain_core.messages import HumanMessage

            async for chunk in self._graph.astream_events(
                {
                    "messages": [HumanMessage(content=message)],
                    "input": message,
                    "output": "",
                },
                version="v1"
            ):
                # 处理流式事件
                if chunk["event"] == "on_chat_model_stream":
                    content = chunk["data"]["chunk"].content
                    if content:
                        yield Event(
                            EventType.TEXT_DELTA,
                            data={"text": content}
                        )
        finally:
            yield Event(EventType.THINKING_END)

    async def reset(self):
        """重置对话历史"""
        if self._memory:
            self._memory.clear()

    async def close(self):
        """释放资源"""
        self._connected = False


# 注册到工厂
from agentex.frameworks.base import FrameworkFactory, FrameworkType
FrameworkFactory.register(FrameworkType.LANGGRAPH)(LangGraphAgent)
