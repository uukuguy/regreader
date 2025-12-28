"""Pydantic AI Agent 实现

使用 Pydantic AI 框架实现 GridCode Agent，支持多模型。
"""

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from loguru import logger

from grid_code.agents.base import AgentResponse, BaseGridCodeAgent
from grid_code.agents.prompts import SYSTEM_PROMPT
from grid_code.config import get_settings
from grid_code.mcp.tools import GridCodeTools


class PydanticAIAgent(BaseGridCodeAgent):
    """基于 Pydantic AI 的 Agent 实现

    支持多模型切换：Claude、GPT、Qwen 等
    """

    def __init__(
        self,
        reg_id: str | None = None,
        model: str | None = None,
        provider: str = "anthropic",
    ):
        """
        初始化 Pydantic AI Agent

        Args:
            reg_id: 默认规程标识
            model: 模型名称
            provider: 模型提供商 ('anthropic', 'openai')
        """
        super().__init__(reg_id)

        settings = get_settings()
        self._model_name = model or settings.default_model
        self.provider = provider
        self.tools = GridCodeTools()
        self._tool_calls: list[dict] = []
        self._sources: list[str] = []

        # 创建模型实例
        if provider == "anthropic":
            api_key = settings.anthropic_api_key
            if not api_key:
                raise ValueError("未配置 Anthropic API Key")
            model_instance = AnthropicModel(self._model_name, api_key=api_key)
        elif provider == "openai":
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("未配置 OpenAI API Key")
            model_instance = OpenAIModel(self._model_name, api_key=api_key)
        else:
            raise ValueError(f"不支持的 provider: {provider}")

        # 创建 Agent
        self.agent = Agent(
            model_instance,
            system_prompt=SYSTEM_PROMPT,
        )

        # 注册工具
        self._register_tools()

    @property
    def name(self) -> str:
        return f"PydanticAIAgent({self.provider})"

    @property
    def model(self) -> str:
        return self._model_name

    def _register_tools(self):
        """注册工具到 Agent"""

        @self.agent.tool
        async def get_toc(ctx: RunContext[None], reg_id: str) -> dict:
            """获取安规的章节目录树及页码范围。"""
            result = self.tools.get_toc(reg_id)
            self._tool_calls.append({"name": "get_toc", "input": {"reg_id": reg_id}, "output": result})
            return result

        @self.agent.tool
        async def smart_search(
            ctx: RunContext[None],
            query: str,
            reg_id: str,
            chapter_scope: str | None = None,
            limit: int = 10,
        ) -> list[dict]:
            """在安规中执行混合检索（关键词+语义）。"""
            # 使用默认 reg_id
            if self.reg_id and not reg_id:
                reg_id = self.reg_id

            result = self.tools.smart_search(query, reg_id, chapter_scope, limit)
            self._tool_calls.append({
                "name": "smart_search",
                "input": {"query": query, "reg_id": reg_id, "chapter_scope": chapter_scope},
                "output": result,
            })

            # 收集来源
            for item in result:
                if "source" in item:
                    self._sources.append(item["source"])

            return result

        @self.agent.tool
        async def read_page_range(
            ctx: RunContext[None],
            reg_id: str,
            start_page: int,
            end_page: int,
        ) -> dict:
            """读取连续页面的完整 Markdown 内容。"""
            if self.reg_id and not reg_id:
                reg_id = self.reg_id

            result = self.tools.read_page_range(reg_id, start_page, end_page)
            self._tool_calls.append({
                "name": "read_page_range",
                "input": {"reg_id": reg_id, "start_page": start_page, "end_page": end_page},
                "output": result,
            })

            if "source" in result:
                self._sources.append(result["source"])

            return result

        @self.agent.tool
        async def list_regulations(ctx: RunContext[None]) -> list[dict]:
            """列出所有已入库的规程。"""
            result = self.tools.list_regulations()
            self._tool_calls.append({"name": "list_regulations", "input": {}, "output": result})
            return result

    async def chat(self, message: str) -> AgentResponse:
        """
        与 Agent 对话

        Args:
            message: 用户消息

        Returns:
            AgentResponse
        """
        # 重置调用记录
        self._tool_calls = []
        self._sources = []

        # 运行 Agent
        result = await self.agent.run(message)

        return AgentResponse(
            content=result.data,
            sources=list(set(self._sources)),
            tool_calls=self._tool_calls,
        )

    async def reset(self):
        """重置对话历史"""
        # Pydantic AI 每次 run 都是独立的，无需显式重置
        self._tool_calls = []
        self._sources = []
