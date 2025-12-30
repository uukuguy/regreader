"""会话管理器

管理 Agent 会话状态，支持多会话隔离和持久化。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionState:
    """会话状态"""

    session_id: str
    """会话唯一标识"""

    created_at: datetime
    """创建时间"""

    last_active: datetime
    """最后活跃时间"""

    message_count: int = 0
    """消息计数"""

    tool_calls: list[dict] = field(default_factory=list)
    """工具调用记录"""

    sources: list[str] = field(default_factory=list)
    """来源引用列表"""

    def add_tool_call(self, name: str, input_data: dict, output: any = None) -> None:
        """添加工具调用记录"""
        self.tool_calls.append({
            "name": name,
            "input": input_data,
            "output": output,
        })

    def add_source(self, source: str) -> None:
        """添加来源引用（自动去重）"""
        if source and source not in self.sources:
            self.sources.append(source)

    def reset_per_query(self) -> None:
        """重置单次查询的临时状态"""
        self.tool_calls = []
        self.sources = []

    def update_active(self) -> None:
        """更新活跃时间"""
        self.last_active = datetime.now()
        self.message_count += 1


class SessionManager:
    """会话管理器

    管理多个会话的生命周期，支持：
    - 会话创建和获取
    - 会话重置和删除
    - 会话列表查询
    """

    def __init__(self, default_session_id: str | None = None):
        """初始化会话管理器

        Args:
            default_session_id: 默认会话 ID，如果不指定则自动生成
        """
        self._sessions: dict[str, SessionState] = {}
        self._default_id = default_session_id or f"gridcode-{uuid.uuid4().hex[:8]}"

    @property
    def default_session_id(self) -> str:
        """获取默认会话 ID"""
        return self._default_id

    def get_or_create(self, session_id: str | None = None) -> SessionState:
        """获取或创建会话

        Args:
            session_id: 会话 ID，如果为 None 则使用默认会话

        Returns:
            会话状态对象
        """
        sid = session_id or self._default_id

        if sid not in self._sessions:
            now = datetime.now()
            self._sessions[sid] = SessionState(
                session_id=sid,
                created_at=now,
                last_active=now,
            )

        session = self._sessions[sid]
        session.update_active()
        return session

    def reset(self, session_id: str | None = None) -> None:
        """重置会话

        删除指定会话的所有状态，下次访问时会创建新会话。

        Args:
            session_id: 会话 ID，如果为 None 则重置默认会话
        """
        sid = session_id or self._default_id
        if sid in self._sessions:
            del self._sessions[sid]

    def reset_all(self) -> None:
        """重置所有会话"""
        self._sessions.clear()

    def get_all_sessions(self) -> list[str]:
        """获取所有活跃会话 ID

        Returns:
            会话 ID 列表
        """
        return list(self._sessions.keys())

    def get_session_info(self, session_id: str | None = None) -> dict | None:
        """获取会话信息

        Args:
            session_id: 会话 ID

        Returns:
            会话信息字典，如果会话不存在返回 None
        """
        sid = session_id or self._default_id
        session = self._sessions.get(sid)

        if session is None:
            return None

        return {
            "session_id": session.session_id,
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat(),
            "message_count": session.message_count,
            "tool_call_count": len(session.tool_calls),
            "source_count": len(session.sources),
        }

    def __contains__(self, session_id: str) -> bool:
        """检查会话是否存在"""
        return session_id in self._sessions

    def __len__(self) -> int:
        """返回活跃会话数量"""
        return len(self._sessions)
