# Bash+FS Subagents 架构 API 参考

本文档提供 RegReader Bash+FS Subagents 架构的公共 API 参考。

---

## 目录

1. [基础设施层 (Infrastructure)](#基础设施层-infrastructure)
   - [FileContext](#filecontext)
   - [SkillLoader](#skillloader)
   - [EventBus](#eventbus)
   - [SecurityGuard](#securityguard)
2. [领域子代理 (Domain Subagents)](#领域子代理-domain-subagents)
   - [RegSearchSubagent](#regsearchsubagent)
3. [协调层 (Orchestration)](#协调层-orchestration)
   - [Coordinator](#coordinator)

---

## 基础设施层 (Infrastructure)

导入方式：

```python
from regreader.infrastructure import (
    FileContext,
    SkillLoader,
    Skill,
    EventBus,
    Event,
    SubagentEvent,
    SecurityGuard,
    PermissionMatrix,
)
```

---

### FileContext

文件上下文管理器，为 Subagent 提供受控的文件系统访问，实现读写隔离。

**模块路径**: `regreader.infrastructure.file_context`

#### 构造函数

```python
FileContext(
    subagent_name: str,
    base_dir: Path,
    can_read: list[Path] = None,
    can_write: list[Path] = None,
    project_root: Path = None,
)
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `subagent_name` | `str` | Subagent 标识名 |
| `base_dir` | `Path` | Subagent 工作目录根路径 |
| `can_read` | `list[Path]` | 可读路径白名单（默认：工作目录 + shared/） |
| `can_write` | `list[Path]` | 可写路径白名单（默认：scratch/ + logs/） |
| `project_root` | `Path` | 项目根目录（默认：当前目录） |

#### 同步方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `read_skill()` | `str` | 读取 SKILL.md 技能说明 |
| `read_scratch(filename)` | `str` | 读取 scratch 目录中的文件 |
| `write_scratch(filename, content)` | `Path` | 写入 scratch 目录 |
| `read_shared(path)` | `str` | 读取共享资源（相对于 shared/） |
| `get_plan()` | `dict` | 读取 Coordinator 下发的任务规划 |
| `update_todo(items)` | `None` | 更新待办事项列表 |
| `log(message, level)` | `None` | 记录日志（info/warning/error/debug） |
| `list_scratch()` | `list[str]` | 列出 scratch 目录中的文件 |
| `clear_scratch()` | `None` | 清空 scratch 目录 |

#### 异步方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `aread_scratch(filename)` | `str` | 异步读取 scratch 文件 |
| `awrite_scratch(filename, content)` | `Path` | 异步写入 scratch 目录 |
| `alog(message, level)` | `None` | 异步记录日志 |

#### 工具方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `get_scratch_path(filename)` | `Path` | 获取 scratch 文件的完整路径 |
| `exists_in_scratch(filename)` | `bool` | 检查 scratch 中是否存在文件 |

#### 使用示例

```python
from pathlib import Path
from regreader.infrastructure import FileContext

# 创建文件上下文
fc = FileContext(
    subagent_name="regsearch",
    base_dir=Path("subagents/regsearch"),
    project_root=Path.cwd(),
)

# 写入临时结果
fc.write_scratch("results.json", '{"status": "ok"}')

# 读取结果
content = fc.read_scratch("results.json")

# 记录日志
fc.log("任务完成", "info")

# 异步操作
async def example():
    await fc.awrite_scratch("async_result.txt", "异步写入内容")
    content = await fc.aread_scratch("async_result.txt")
```

#### 异常

| 异常 | 说明 |
|------|------|
| `FileAccessError` | 文件访问权限错误 |
| `FileNotFoundInContextError` | 文件在上下文中不存在 |

---

### SkillLoader

技能加载器，动态加载 SKILL.md 和 skills/ 目录中定义的技能包。

**模块路径**: `regreader.infrastructure.skill_loader`

#### 构造函数

```python
SkillLoader(
    project_root: Path = None,
    skills_dir: str = "skills",
    subagents_dir: str = "subagents",
)
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `project_root` | `Path` | 项目根目录 |
| `skills_dir` | `str` | skills/ 目录相对路径 |
| `subagents_dir` | `str` | subagents/ 目录相对路径 |

#### 方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `load_all(force=False)` | `dict[str, Skill]` | 加载所有技能 |
| `get_skill(name)` | `Skill` | 获取指定技能 |
| `get_skills_for_subagent(type)` | `list[Skill]` | 获取关联指定 Subagent 的技能 |
| `get_skills_by_tool(tool_name)` | `list[Skill]` | 获取使用指定工具的技能 |
| `get_skills_by_tag(tag)` | `list[Skill]` | 获取指定标签的技能 |
| `list_skills()` | `list[str]` | 列出所有技能名称 |
| `refresh()` | `dict[str, Skill]` | 刷新技能缓存 |

#### Skill 数据类

```python
@dataclass
class Skill:
    name: str                          # 技能名称
    description: str                   # 技能描述
    entry_point: str                   # 入口点
    required_tools: list[str]          # 所需 MCP 工具
    input_schema: dict[str, Any]       # 输入参数 JSON Schema
    output_schema: dict[str, Any]      # 输出结果 JSON Schema
    examples: list[dict[str, Any]]     # 使用示例
    subagents: list[str]               # 关联的 Subagent 类型
    version: str                       # 技能版本
    tags: list[str]                    # 标签列表
    source_path: Path | None           # 来源文件路径
```

#### 使用示例

```python
from regreader.infrastructure import SkillLoader

# 创建加载器
loader = SkillLoader()

# 加载所有技能
skills = loader.load_all()

# 获取指定技能
search_skill = loader.get_skill("simple_search")
print(f"技能: {search_skill.name}")
print(f"所需工具: {search_skill.required_tools}")

# 获取 regsearch 关联的技能
regsearch_skills = loader.get_skills_for_subagent("regsearch")
```

---

### EventBus

事件总线，支持 Subagent 间松耦合通信和事件持久化。

**模块路径**: `regreader.infrastructure.event_bus`

#### 事件类型枚举

```python
class SubagentEvent(str, Enum):
    # 任务生命周期
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"

    # 交接事件
    HANDOFF_REQUEST = "handoff_request"
    HANDOFF_ACCEPTED = "handoff_accepted"
    HANDOFF_REJECTED = "handoff_rejected"

    # 资源事件
    RESOURCE_CREATED = "resource_created"
    RESOURCE_UPDATED = "resource_updated"
    RESOURCE_DELETED = "resource_deleted"

    # 进度事件
    PROGRESS_UPDATE = "progress_update"

    # 系统事件
    SYSTEM_ERROR = "system_error"
    SYSTEM_WARNING = "system_warning"
    HEARTBEAT = "heartbeat"
```

#### Event 数据类

```python
@dataclass
class Event:
    event_type: SubagentEvent     # 事件类型
    source: str                   # 来源 Subagent
    target: str | None = None     # 目标 Subagent（None 表示广播）
    payload: dict[str, Any]       # 事件负载
    timestamp: datetime           # 时间戳（自动生成）
    correlation_id: str | None    # 关联 ID（用于追踪）
```

#### EventBus 构造函数

```python
EventBus(
    project_root: Path = None,
    events_dir: str = "coordinator/logs",
    persist: bool = True,
)
```

#### 方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `publish(event)` | `None` | 发布事件（同步） |
| `publish_async(event)` | `None` | 发布事件（异步） |
| `subscribe(event_type, handler)` | `None` | 订阅指定事件类型 |
| `subscribe_all(handler)` | `None` | 订阅所有事件 |
| `subscribe_target(target, handler)` | `None` | 订阅发往指定目标的事件 |
| `unsubscribe(event_type, handler)` | `None` | 取消订阅 |
| `replay_events(since, until, types)` | `list[Event]` | 从文件重放事件 |
| `get_recent_events(count, types)` | `list[Event]` | 获取最近的事件 |
| `get_events_by_correlation(id)` | `list[Event]` | 按关联 ID 获取事件 |

#### 使用示例

```python
from regreader.infrastructure import EventBus, Event, SubagentEvent

# 创建事件总线
bus = EventBus()

# 定义事件处理器
def on_task_completed(event: Event):
    print(f"任务完成: {event.payload}")

# 订阅事件
bus.subscribe(SubagentEvent.TASK_COMPLETED, on_task_completed)

# 发布事件
event = Event(
    event_type=SubagentEvent.TASK_STARTED,
    source="regsearch",
    payload={"query": "母线失压", "reg_id": "angui_2024"},
)
bus.publish(event)

# 获取最近事件
recent = bus.get_recent_events(count=10)
```

---

### SecurityGuard

安全守卫，实现瑞士奶酪防御模型（目录隔离 + 权限控制）。

**模块路径**: `regreader.infrastructure.security_guard`

#### PermissionMatrix 数据类

```python
@dataclass
class PermissionMatrix:
    subagent_name: str              # Subagent 名称
    readable_dirs: list[Path]       # 可读目录列表
    writable_dirs: list[Path]       # 可写目录列表
    allowed_tools: list[str]        # 允许使用的工具
    can_execute_scripts: bool       # 是否可执行脚本
    max_file_size: int = 10_000_000 # 最大文件大小（字节）
```

#### SecurityGuard 构造函数

```python
SecurityGuard(
    project_root: Path = None,
    audit_log_path: str = "coordinator/logs/audit.jsonl",
)
```

#### 方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `register_subagent(matrix)` | `None` | 注册 Subagent 权限矩阵 |
| `check_file_access(subagent, path, op)` | `bool` | 检查文件访问权限 |
| `check_tool_access(subagent, tool)` | `bool` | 检查工具访问权限 |
| `check_script_execution(subagent)` | `bool` | 检查脚本执行权限 |
| `audit_log(action, subagent, details)` | `None` | 记录审计日志 |
| `get_audit_logs(since, subagent)` | `list[dict]` | 获取审计日志 |

#### 使用示例

```python
from pathlib import Path
from regreader.infrastructure import SecurityGuard, PermissionMatrix

# 创建安全守卫
guard = SecurityGuard()

# 注册 Subagent 权限
matrix = PermissionMatrix(
    subagent_name="regsearch",
    readable_dirs=[Path("shared/"), Path("coordinator/plan.md")],
    writable_dirs=[Path("subagents/regsearch/scratch/")],
    allowed_tools=["smart_search", "read_page_range", "get_toc"],
    can_execute_scripts=False,
)
guard.register_subagent(matrix)

# 检查权限
can_read = guard.check_file_access(
    "regsearch",
    Path("shared/data/index.json"),
    "read"
)
can_use_tool = guard.check_tool_access("regsearch", "smart_search")
```

---

## 领域子代理 (Domain Subagents)

### RegSearchSubagent

规程文档检索领域专家，整合搜索、表格、引用、发现功能。

**模块路径**: `regreader.subagents.regsearch`

#### 构造函数

```python
RegSearchSubagent(
    config: SubagentConfig = None,
    file_context: FileContext = None,
    mcp_client: MCPClient = None,
    use_file_system: bool = False,
    project_root: Path = None,
)
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `config` | `SubagentConfig` | 配置（默认使用 REGSEARCH_AGENT_CONFIG） |
| `file_context` | `FileContext` | 文件上下文（可选） |
| `mcp_client` | `MCPClient` | MCP 客户端 |
| `use_file_system` | `bool` | 是否启用文件系统模式 |
| `project_root` | `Path` | 项目根目录 |

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | Subagent 标识名（"regsearch"） |
| `uses_file_system` | `bool` | 是否使用文件系统模式 |
| `mcp_client` | `MCPClient` | MCP 客户端 |
| `internal_agents` | `dict` | 内部组件子代理字典 |

#### 方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `execute(context)` | `SubagentResult` | 执行规程检索任务 |
| `reset()` | `None` | 重置 Subagent 状态 |
| `register_internal_agent(name, agent)` | `None` | 注册内部组件子代理 |
| `get_internal_agent(name)` | `BaseSubagent` | 获取内部组件子代理 |

#### 使用示例

```python
from regreader.subagents import RegSearchSubagent
from regreader.subagents.base import SubagentContext

# 创建子代理（内存模式）
subagent = RegSearchSubagent()

# 创建子代理（文件系统模式）
fs_subagent = RegSearchSubagent(
    use_file_system=True,
    project_root=Path.cwd(),
)

# 执行任务
context = SubagentContext(
    query="母线失压如何处理",
    reg_id="angui_2024",
)
result = await subagent.execute(context)

print(f"结果: {result.content}")
print(f"来源: {result.sources}")
```

---

## 协调层 (Orchestration)

### Coordinator

系统的核心调度中心，整合查询分析、Subagent 路由和结果聚合。

**模块路径**: `regreader.orchestrator.coordinator`

#### SessionState 数据类

```python
@dataclass
class SessionState:
    session_id: str                   # 会话唯一标识
    started_at: datetime              # 会话开始时间
    query_count: int                  # 查询计数
    current_reg_id: str | None        # 当前规程标识
    last_query: str | None            # 最后一次查询
    last_intent: dict | None          # 最后一次意图分析结果
    accumulated_sources: list[str]    # 累积的来源（跨查询）
```

#### Coordinator 构造函数

```python
Coordinator(
    subagents: dict[SubagentType, BaseSubagent],
    work_dir: Path = None,
    event_bus: EventBus = None,
    router_mode: str = "sequential",
)
```

**参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| `subagents` | `dict` | 可用的 Subagent 实例映射 |
| `work_dir` | `Path` | 工作目录（默认 coordinator/） |
| `event_bus` | `EventBus` | 事件总线（可选） |
| `router_mode` | `str` | 路由执行模式（sequential/parallel） |

#### 方法

| 方法 | 返回类型 | 说明 |
|------|---------|------|
| `process_query(query, reg_id, ...)` | `SubagentResult` | 处理用户查询 |
| `read_subagent_result(name)` | `dict` | 读取 Subagent 的结果文件 |
| `get_subagent(type)` | `BaseSubagent` | 获取指定类型的 Subagent |
| `reset()` | `None` | 重置协调器状态 |
| `log_event(message)` | `None` | 记录事件日志 |

#### 使用示例

```python
from regreader.orchestrator import Coordinator
from regreader.infrastructure import EventBus
from regreader.subagents import RegSearchSubagent
from regreader.subagents.config import SubagentType

# 准备子代理
subagents = {
    SubagentType.REGSEARCH: RegSearchSubagent(),
}

# 创建协调器
coordinator = Coordinator(
    subagents=subagents,
    event_bus=EventBus(),
    router_mode="sequential",
)

# 处理查询
result = await coordinator.process_query(
    query="母线失压如何处理",
    reg_id="angui_2024",
)

print(f"结果: {result.content}")
print(f"会话状态: {coordinator.session_state.query_count} 次查询")
```

---

## 附录

### 目录结构

```
regreader/
├── coordinator/                 # Coordinator 工作区
│   ├── CLAUDE.md               # 项目导读入口
│   ├── plan.md                 # 任务规划（运行时生成）
│   ├── session_state.json      # 会话状态（运行时生成）
│   └── logs/                   # 日志目录
│
├── subagents/                  # Subagent 工作区
│   └── regsearch/              # RegSearch-Subagent
│       ├── SKILL.md            # 技能说明书
│       ├── scratch/            # 临时结果
│       └── logs/               # 日志
│
├── shared/                     # 共享只读资源
│   ├── data/                   # 数据目录
│   ├── docs/                   # 文档
│   └── templates/              # 模板
│
└── skills/                     # 技能库
    └── registry.yaml           # 技能注册表
```

### 权限矩阵默认值

| Subagent | 可读目录 | 可写目录 | 工具数量 |
|----------|---------|---------|---------|
| regsearch | shared/, coordinator/plan.md | regsearch/scratch/, logs/ | 15 |

### 版本信息

- 架构版本：1.0.0
- 文档更新：2026-01-11
