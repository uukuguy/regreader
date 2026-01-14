"""公共基础设施层

提供 Bash+FS 范式所需的核心组件：
- FileContext: 文件上下文管理器，实现读写隔离
- SkillLoader: 技能加载器，动态加载 SKILL.md 定义
- EventBus: 事件总线，支持 Subagent 间松耦合通信
- SecurityGuard: 安全守卫，实现目录隔离和权限控制
"""

from regreader.infrastructure.event_bus import Event, EventBus, SubagentEvent
from regreader.infrastructure.file_context import FileContext
from regreader.infrastructure.security_guard import PermissionMatrix, SecurityGuard
from regreader.infrastructure.skill_loader import Skill, SkillLoader

__all__ = [
    # FileContext
    "FileContext",
    # SkillLoader
    "Skill",
    "SkillLoader",
    # EventBus
    "SubagentEvent",
    "Event",
    "EventBus",
    # SecurityGuard
    "PermissionMatrix",
    "SecurityGuard",
]
