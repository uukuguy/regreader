"""Subagent 基类和上下文定义

定义所有 Subagent 的抽象基类和通用数据结构。
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger

from regreader.orchestration.result import SubagentResult

if TYPE_CHECKING:
    from regreader.orchestration.hierarchy_manager import HierarchyManager
    from regreader.subagents.config import SubagentConfig, SubagentType


@dataclass
class SubagentContext:
    """Subagent 执行上下文

    包含 Subagent 执行所需的所有上下文信息。

    Attributes:
        query: 用户查询
        reg_id: 规程ID（可选）
        chapter_scope: 章节范围（可选）
        hints: 额外提示信息
        max_iterations: 最大工具调用迭代次数
        previous_results: 前序 Subagent 的结果（用于上下文传递）
    """

    query: str
    """用户查询"""

    reg_id: str | None = None
    """规程ID（如 'angui_2024'）"""

    chapter_scope: str | None = None
    """章节范围（如 '第六章'、'2.1.4'）"""

    hints: dict[str, Any] = field(default_factory=dict)
    """额外提示信息

    可能包含：
    - table_hint: 表格提示（如 '表6-2'）
    - annotation_hint: 注释提示（如 '注1'）
    - reference_text: 引用文本（如 '见第六章'）
    - block_types: 搜索的块类型（如 ['text', 'table']）
    - page_hint: 页面提示（如 45）
    """

    max_iterations: int = 5
    """最大工具调用迭代次数"""

    previous_results: list[SubagentResult] = field(default_factory=list)
    """前序 Subagent 的结果（用于多跳查询的上下文传递）"""

    @property
    def has_reg_id(self) -> bool:
        """是否指定了规程ID"""
        return self.reg_id is not None

    @property
    def has_chapter_scope(self) -> bool:
        """是否指定了章节范围"""
        return self.chapter_scope is not None

    def get_hint(self, key: str, default: Any = None) -> Any:
        """获取提示信息

        Args:
            key: 提示键
            default: 默认值

        Returns:
            提示值
        """
        return self.hints.get(key, default)


class BaseSubagent(ABC):
    """Subagent 抽象基类

    所有 Subagent 实现（包括三个框架）必须继承此类。

    关键职责：
    - 定义统一的执行接口 `execute()`
    - 提供配置和上下文管理
    - 支持异步执行
    - 集成 HierarchyManager 进行父子追踪
    """

    def __init__(
        self,
        config: "SubagentConfig",
        hierarchy_manager: "HierarchyManager | None" = None,
        parent_id: str | None = None,
    ):
        """初始化 Subagent

        Args:
            config: Subagent 配置
            hierarchy_manager: 层级管理器（用于父子追踪）
            parent_id: 父 agent ID（用于追踪调用栈）
        """
        self.config = config
        self.hierarchy_manager = hierarchy_manager
        self.parent_id = parent_id
        self.agent_id = f"{config.agent_type.value}_{uuid.uuid4().hex[:8]}"
        self._registered = False

    @property
    def agent_type(self) -> "SubagentType":
        """Subagent 类型"""
        return self.config.agent_type

    @property
    def name(self) -> str:
        """Subagent 名称"""
        return self.config.name

    @property
    def tools(self) -> list[str]:
        """可用工具列表"""
        return self.config.tools

    def register_to_hierarchy(self, user_input: str) -> None:
        """注册到 HierarchyManager

        Args:
            user_input: 用户输入（子任务描述）
        """
        if self.hierarchy_manager is not None and not self._registered:
            self.hierarchy_manager.push_agent(
                agent_id=self.agent_id,
                agent_name=self.name,
                parent_id=self.parent_id,
                level=1,  # L1 子智能体
                user_input=user_input,
            )
            self._registered = True
            logger.debug(
                f"Registered {self.name} (id={self.agent_id}) to HierarchyManager, "
                f"parent_id={self.parent_id}"
            )

    def unregister_from_hierarchy(self) -> None:
        """从 HierarchyManager 注销"""
        if self.hierarchy_manager is not None and self._registered:
            self.hierarchy_manager.pop_agent(self.agent_id)
            self._registered = False
            logger.debug(f"Unregistered {self.name} (id={self.agent_id}) from HierarchyManager")

    def update_status(
        self, status: str, thinking: str | None = None, output: str | None = None
    ) -> None:
        """更新 agent 状态到 HierarchyManager

        Args:
            status: 状态（如 "running", "completed", "failed"）
            thinking: 思考过程
            output: 输出结果
        """
        if self.hierarchy_manager is not None and self._registered:
            self.hierarchy_manager.update_agent_status(
                agent_id=self.agent_id,
                status=status,
                thinking=thinking,
                output=output,
            )

    @abstractmethod
    async def execute(self, context: SubagentContext) -> SubagentResult:
        """执行 Subagent 任务

        Args:
            context: 执行上下文

        Returns:
            执行结果

        Raises:
            任何执行过程中的异常
        """
        pass

    def validate_context(self, context: SubagentContext) -> None:
        """验证上下文有效性

        Args:
            context: 执行上下文

        Raises:
            ValueError: 上下文无效
        """
        if not context.query or not context.query.strip():
            raise ValueError("Query cannot be empty")

        # 工具特定验证
        required_tools = self.config.tools
        if not required_tools:
            raise ValueError(f"{self.name} has no tools configured")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.agent_type.value}, name={self.name})"
