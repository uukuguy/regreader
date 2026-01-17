"""对话记忆系统

管理 Agent 的对话历史和相关上下文。
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryItem:
    """记忆条目"""
    role: str  # "user" | "assistant" | "system"
    content: str
    metadata: dict[str, Any] = None


class AgentMemory:
    """Agent 记忆

    管理对话历史和相关上下文。
    完全通用化，不包含任何领域特定逻辑。
    """

    def __init__(self, max_items: int = 50):
        self.max_items = max_items
        self._history: list[MemoryItem] = []
        self._metadata: dict[str, Any] = {}

    def add(self, role: str, content: str, metadata: dict[str, Any] | None = None):
        """添加记忆"""
        item = MemoryItem(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self._history.append(item)

        # 裁剪超出的记忆
        if len(self._history) > self.max_items:
            self._history = self._history[-self.max_items:]

    def get_history(self) -> list[MemoryItem]:
        """获取对话历史"""
        return list(self._history)

    def clear(self):
        """清空记忆"""
        self._history.clear()
        self._metadata.clear()

    def get_context(self) -> str:
        """生成记忆上下文（供提示词使用）"""
        if not self._history:
            return ""

        lines = ["## 对话历史"]
        for item in self._history[-10:]:  # 只返回最近10条
            lines.append(f"- {item.role}: {item.content[:100]}")

        return "\n".join(lines)

    def get_messages(self) -> list[dict[str, Any]]:
        """获取格式化的消息列表（供 LLM 使用）"""
        return [
            {"role": item.role, "content": item.content}
            for item in self._history
        ]

    def __len__(self):
        return len(self._history)

    def __bool__(self):
        return len(self._history) > 0


class MemoryStore:
    """持久化记忆存储

    支持将记忆保存到文件系统或数据库。
    """

    def __init__(self, storage_path: str | None = None):
        self.storage_path = storage_path
        self._cache: dict[str, AgentMemory] = {}

    def save(self, session_id: str, memory: AgentMemory) -> None:
        """保存记忆"""
        self._cache[session_id] = memory

    def load(self, session_id: str) -> AgentMemory | None:
        """加载记忆"""
        return self._cache.get(session_id)

    def delete(self, session_id: str) -> None:
        """删除记忆"""
        self._cache.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        """列出所有会话"""
        return list(self._cache.keys())
