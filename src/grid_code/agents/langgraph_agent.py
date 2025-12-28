"""LangGraph Agent 实现

使用 LangGraph 框架实现 GridCode Agent，支持复杂工作流。
"""

import json
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp.tools import GridCodeTools


# 定义状态类型
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    tool_calls: list[dict]
    sources: list[str]


class LangGraphAgent(BaseGridCodeAgent):
    """基于 LangGraph 的 Agent 实现

    支持复杂工作流和状态管理
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
    ):
        """
        初始化 LangGraph Agent

        Args:
            reg_id: 默认规程标识
            model: 模型名称
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.default_model

        api_key = settings.anthropic_api_key
        if not api_key:
            raise ValueError("未配置 Anthropic API Key")

        # 创建 LLM
        self.llm = ChatAnthropic(
            model=self._model_name,
            api_key=api_key,
            max_tokens=4096,
        )

        # 工具实例
        self.grid_tools = GridCodeTools()

        # 创建工具
        self._tools = self._create_tools()

        # 绑定工具到 LLM
        self.llm_with_tools = self.llm.bind_tools(self._tools)

        # 构建图
        self.graph = self._build_graph()

        # 消息历史
        self.messages: list[BaseMessage] = []

    @property
    def name(self) -> str:
        return "LangGraphAgent"

    @property
    def model(self) -> str:
        return self._model_name

    def _create_tools(self) -> list:
        """创建 LangChain 工具"""
        grid_tools = self.grid_tools
        default_reg_id = self.reg_id

        @tool
        def get_toc(reg_id: str) -> dict:
            """获取安规的章节目录树及页码范围。

            Args:
                reg_id: 规程标识，如 'angui_2024'
            """
            return grid_tools.get_toc(reg_id)

        @tool
        def smart_search(
            query: str,
            reg_id: str,
            chapter_scope: str | None = None,
            limit: int = 10,
        ) -> list[dict]:
            """在安规中执行混合检索（关键词+语义）。

            Args:
                query: 搜索查询，如 '母线失压处理'
                reg_id: 规程标识
                chapter_scope: 限定章节范围（可选）
                limit: 返回结果数量限制
            """
            if default_reg_id and not reg_id:
                reg_id = default_reg_id
            return grid_tools.smart_search(query, reg_id, chapter_scope, limit)

        @tool
        def read_page_range(reg_id: str, start_page: int, end_page: int) -> dict:
            """读取连续页面的完整 Markdown 内容。

            Args:
                reg_id: 规程标识
                start_page: 起始页码
                end_page: 结束页码
            """
            if default_reg_id and not reg_id:
                reg_id = default_reg_id
            return grid_tools.read_page_range(reg_id, start_page, end_page)

        @tool
        def list_regulations() -> list[dict]:
            """列出所有已入库的规程。"""
            return grid_tools.list_regulations()

        return [get_toc, smart_search, read_page_range, list_regulations]

    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 工作流"""

        def should_continue(state: AgentState) -> str:
            """判断是否继续工具调用"""
            messages = state["messages"]
            last_message = messages[-1]

            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        def call_model(state: AgentState) -> dict:
            """调用模型"""
            messages = state["messages"]

            # 添加系统提示（如果是第一条消息）
            if len(messages) == 1:
                messages = [HumanMessage(content=SYSTEM_PROMPT)] + messages

            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        def process_tool_results(state: AgentState) -> dict:
            """处理工具结果，收集来源"""
            messages = state["messages"]
            sources = state.get("sources", [])
            tool_calls = state.get("tool_calls", [])

            for msg in messages:
                if isinstance(msg, ToolMessage):
                    try:
                        result = json.loads(msg.content)
                        if isinstance(result, dict) and "source" in result:
                            sources.append(result["source"])
                        elif isinstance(result, list):
                            for item in result:
                                if isinstance(item, dict) and "source" in item:
                                    sources.append(item["source"])
                    except json.JSONDecodeError:
                        pass

            return {"sources": sources, "tool_calls": tool_calls}

        # 构建图
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", ToolNode(self._tools))
        workflow.add_node("process_results", process_tool_results)

        # 设置入口
        workflow.set_entry_point("agent")

        # 添加条件边
        workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        workflow.add_edge("tools", "process_results")
        workflow.add_edge("process_results", "agent")

        return workflow.compile()

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 添加用户消息
        self.messages.append(HumanMessage(content=message))

        # 运行图
        initial_state: AgentState = {
            "messages": self.messages.copy(),
            "tool_calls": [],
            "sources": [],
        }

        final_state = await self.graph.ainvoke(initial_state)

        # 提取最终回答
        final_content = ""
        for msg in reversed(final_state["messages"]):
            if isinstance(msg, AIMessage) and not msg.tool_calls:
                final_content = msg.content
                break

        # 更新消息历史
        self.messages = final_state["messages"]

        return AgentResponse(
            content=final_content,
            sources=list(set(final_state.get("sources", []))),
            tool_calls=final_state.get("tool_calls", []),
        )

    async def reset(self):
        """重置对话历史"""
        self.messages = []
