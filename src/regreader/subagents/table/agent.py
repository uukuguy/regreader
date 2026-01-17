"""TableAgent: 表格子智能体

负责表格搜索和数据提取的原子级任务执行。
"""

from pathlib import Path
from typing import Any

from loguru import logger
from regreader.subagents.bash_fs_base import BaseSubagentFS, SubagentResult


class TableAgent(BaseSubagentFS):
    """表格子智能体

    职责：
    1. 接收主智能体的任务（如"查找并提取相关的表格数据"）
    2. 主动拆解为原子操作（search_tables → get_table_by_id）
    3. 调用 MCP 工具执行
    4. 记录过程到 steps.md
    5. 返回结果摘要
    """

    def __init__(
        self,
        workspace: Path,
        reg_id: str,
        framework: str = "claude",
        mcp_transport: str | None = None,
        mcp_host: str | None = None,
        mcp_port: int | None = None,
    ):
        """初始化 TableAgent

        Args:
            workspace: 工作区路径
            reg_id: 规程 ID
            framework: 框架类型
            mcp_transport: MCP 传输方式（可选，从 CLI 传递）
            mcp_host: MCP 主机地址（可选，从 CLI 传递）
            mcp_port: MCP 端口（可选，从 CLI 传递）
        """
        super().__init__(
            workspace,
            reg_id,
            framework,
            mcp_transport=mcp_transport,
            mcp_host=mcp_host,
            mcp_port=mcp_port,
        )

        # 获取配置
        from regreader.core.config import get_settings
        settings = get_settings()

        # MCP 客户端（用于调用工具）
        from regreader.mcp.client import RegReaderMCPClient

        # 使用传递的 MCP 配置或默认配置
        transport = self.mcp_transport or settings.mcp_transport
        server_url = f"http://{self.mcp_host}:{self.mcp_port}/sse"

        # 创建 MCP 客户端（但不立即连接）
        self.mcp_client = RegReaderMCPClient(
            transport=transport,
            server_url=server_url,
        )

        logger.info(
            f"TableAgent 初始化: framework={framework}, reg_id={reg_id}, mcp_transport={transport}"
        )

    def decompose_task(self, task: str) -> list[dict[str, Any]]:
        """将任务拆解为原子操作

        Args:
            task: 任务描述

        Returns:
            原子操作列表
        """
        steps = []

        # 规则 1: 如果任务涉及"搜索表格"、"查找表格"
        if any(keyword in task for keyword in ["表格", "table"]):
            # 提取搜索关键词
            query = task
            for word in ["查找", "提取", "相关", "表格"]:
                query = query.replace(word, "")

            steps.append(
                {
                    "step": 1,
                    "description": f"搜索表格: {query}",
                    "action": "search_tables",
                    "params": {
                        "query": query.strip(),
                        "reg_id": self.reg_id,
                        "mode": "hybrid",
                    },
                }
            )

        # 如果没有匹配，默认使用 search_tables
        if not steps:
            steps.append(
                {
                    "step": 1,
                    "description": "搜索表格",
                    "action": "search_tables",
                    "params": {
                        "query": task,
                        "reg_id": self.reg_id,
                    },
                }
            )

        logger.info(f"TableAgent 拆解完成，共 {len(steps)} 个原子操作")
        return steps

    async def execute_atomic_step(self, step: dict[str, Any]) -> Any:
        """执行单个原子操作（异步）

        Args:
            step: 原子操作定义

        Returns:
            操作结果
        """
        action = step["action"]
        params = step["params"]

        logger.info(f"TableAgent 执行操作: {action} with params={params}")

        # 使用 MCP 客户端调用工具（异步方法）
        try:
            async with self.mcp_client:
                result = await self.mcp_client.call_tool(action, params)
                logger.info(f"TableAgent 操作成功: {action}")
                return result
        except Exception as e:
            logger.error(f"TableAgent 操作失败: {action}, error={e}")
            return {"error": str(e), "action": action, "params": params}
