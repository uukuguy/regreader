# Bash+FS Subagents 架构使用指南

本指南介绍如何使用 GridCode 的 Bash+FS Subagents 架构进行规程检索开发。

---

## 快速开始

### 1. 基本使用（内存模式）

最简单的使用方式，适合快速开发和测试：

```python
from grid_code.subagents import RegSearchSubagent
from grid_code.subagents.base import SubagentContext

# 创建子代理
subagent = RegSearchSubagent()

# 创建执行上下文
context = SubagentContext(
    query="母线失压如何处理",
    reg_id="angui_2024",
)

# 执行检索
result = await subagent.execute(context)
print(result.content)
```

### 2. 文件系统模式

启用文件系统模式，任务和结果通过文件传递：

```python
from pathlib import Path
from grid_code.subagents import RegSearchSubagent

# 创建子代理（启用文件系统）
subagent = RegSearchSubagent(
    use_file_system=True,
    project_root=Path.cwd(),
)

# 执行后结果自动写入文件
# - subagents/regsearch/scratch/results.json
# - subagents/regsearch/scratch/final_report.md
```

### 3. 使用 Coordinator 协调多个子代理

```python
from grid_code.orchestrator import Coordinator
from grid_code.infrastructure import EventBus
from grid_code.subagents import RegSearchSubagent
from grid_code.subagents.config import SubagentType

# 准备子代理
subagents = {
    SubagentType.REGSEARCH: RegSearchSubagent(),
}

# 创建协调器
coordinator = Coordinator(
    subagents=subagents,
    event_bus=EventBus(),
)

# 处理查询
result = await coordinator.process_query(
    query="母线失压如何处理",
    reg_id="angui_2024",
)
```

---

## 核心概念

### Bash+FS 范式

Bash+FS 范式将文件系统作为 Agent 的"虚拟工作台"：

- **目录隔离**：每个 Subagent 有独立的工作目录
- **读写分离**：通过白名单控制可读和可写路径
- **文件通信**：任务和结果通过文件传递，支持异步协作

### 两级技能结构

```
subagents/
├── regsearch/
│   └── SKILL.md              # Subagent 级：整体能力描述

skills/                        # 工作流级：可复用技能包
├── registry.yaml
├── simple_search/SKILL.md
└── table_lookup/SKILL.md
```

- **Subagent 级**：描述子代理的整体能力和内部组件
- **工作流级**：可被多个子代理复用的具体技能

---

## 组件详解

### FileContext（文件上下文）

为 Subagent 提供受控的文件系统访问：

```python
from pathlib import Path
from grid_code.infrastructure import FileContext

fc = FileContext(
    subagent_name="regsearch",
    base_dir=Path("subagents/regsearch"),
)

# 写入临时结果
fc.write_scratch("results.json", '{"status": "ok"}')

# 读取结果
content = fc.read_scratch("results.json")

# 记录日志
fc.log("任务完成", "info")
```

**默认权限**：
- 可读：工作目录 + `shared/`
- 可写：`scratch/` + `logs/`

### EventBus（事件总线）

支持 Subagent 间松耦合通信：

```python
from grid_code.infrastructure import EventBus, Event, SubagentEvent

bus = EventBus()

# 订阅事件
def handler(event):
    print(f"收到事件: {event.event_type}")

bus.subscribe(SubagentEvent.TASK_COMPLETED, handler)

# 发布事件
event = Event(
    event_type=SubagentEvent.TASK_STARTED,
    source="regsearch",
    payload={"query": "母线失压"},
)
bus.publish(event)
```

**事件类型**：
- 任务生命周期：`TASK_STARTED`, `TASK_COMPLETED`, `TASK_FAILED`
- 交接事件：`HANDOFF_REQUEST`, `HANDOFF_ACCEPTED`
- 资源事件：`RESOURCE_CREATED`, `RESOURCE_UPDATED`
- 系统事件：`SYSTEM_ERROR`, `HEARTBEAT`

### SkillLoader（技能加载器）

动态加载技能定义：

```python
from grid_code.infrastructure import SkillLoader

loader = SkillLoader()
skills = loader.load_all()

# 获取指定技能
skill = loader.get_skill("simple_search")
print(f"所需工具: {skill.required_tools}")

# 按 Subagent 类型筛选
regsearch_skills = loader.get_skills_for_subagent("regsearch")
```

### SecurityGuard（安全守卫）

实现权限控制和审计：

```python
from grid_code.infrastructure import SecurityGuard, PermissionMatrix

guard = SecurityGuard()

# 注册权限矩阵
matrix = PermissionMatrix(
    subagent_name="regsearch",
    readable_dirs=[Path("shared/")],
    writable_dirs=[Path("subagents/regsearch/scratch/")],
    allowed_tools=["smart_search", "read_page_range"],
    can_execute_scripts=False,
)
guard.register_subagent(matrix)

# 检查权限
if guard.check_file_access("regsearch", Path("shared/data.json"), "read"):
    print("允许读取")
```

---

## 目录结构

完整的项目目录结构：

```
grid-code/
├── coordinator/                 # Coordinator 工作区
│   ├── CLAUDE.md               # 项目导读入口
│   ├── plan.md                 # 任务规划（运行时）
│   ├── session_state.json      # 会话状态（运行时）
│   └── logs/                   # 日志目录
│
├── subagents/                  # Subagent 工作区
│   └── regsearch/              # RegSearch-Subagent
│       ├── SKILL.md            # 技能说明书
│       ├── scratch/            # 临时结果目录
│       │   ├── current_task.md # 当前任务（输入）
│       │   ├── results.json    # 结构化结果（输出）
│       │   └── final_report.md # 最终报告（输出）
│       └── logs/               # 日志目录
│
├── shared/                     # 共享只读资源
│   ├── data/                   # 数据目录 (→ data/storage/)
│   ├── docs/                   # 工具使用指南
│   └── templates/              # 输出模板
│
└── skills/                     # 技能库
    ├── registry.yaml           # 技能注册表
    ├── simple_search/          # 简单搜索技能
    ├── table_lookup/           # 表格查询技能
    └── cross_ref/              # 交叉引用技能
```

---

## 文件格式

### SKILL.md 格式

支持 YAML front matter：

```markdown
---
name: RegSearch-Subagent
description: 规程文档检索专家
version: "1.0.0"
required_tools:
  - smart_search
  - read_page_range
  - get_toc
subagents:
  - search
  - table
  - reference
---

# RegSearch-Subagent 技能说明

## 角色定位
规程文档检索专家，负责...

## 内部组件
- SearchAgent: 文档搜索与导航
- TableAgent: 表格处理与提取
- ReferenceAgent: 引用追踪与解析
```

### registry.yaml 格式

```yaml
skills:
  - name: simple_search
    description: 简单文本搜索技能
    entry_point: skills/simple_search/entry.py
    required_tools:
      - smart_search
      - read_page_range
    subagents:
      - regsearch
    tags:
      - search
      - basic

  - name: table_lookup
    description: 表格查询技能
    entry_point: skills/table_lookup/entry.py
    required_tools:
      - search_tables
      - get_table_by_id
    subagents:
      - regsearch
```

---

## 工作流示例

### 典型查询处理流程

```
用户查询
    │
    ▼
┌─────────────────────┐
│   Coordinator       │
│  1. 分析查询意图     │
│  2. 写入 plan.md    │
│  3. 发布事件        │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ RegSearch-Subagent  │
│  1. 读取 plan.md    │
│  2. 调用 MCP 工具   │
│  3. 写入 results    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Coordinator       │
│  1. 读取 results    │
│  2. 聚合结果        │
│  3. 更新会话状态    │
└─────────────────────┘
          │
          ▼
      返回结果
```

### 文件系统通信流程

```python
# 1. Coordinator 写入任务
plan_content = """
# 当前任务
查询: 母线失压如何处理
规程: angui_2024
"""
Path("coordinator/plan.md").write_text(plan_content)

# 2. Subagent 读取任务并执行
task = fc.get_plan()
result = await subagent.execute(context)

# 3. Subagent 写入结果
fc.write_scratch("results.json", result.to_json())

# 4. Coordinator 读取结果
result_data = coordinator.read_subagent_result("regsearch")
```

---

## 最佳实践

### 1. 向后兼容

FileContext 是可选的，不传则使用原有内存传递逻辑：

```python
# 内存模式（默认）
subagent = RegSearchSubagent()

# 文件系统模式（可选）
subagent = RegSearchSubagent(use_file_system=True)
```

### 2. 异步操作

对于 I/O 密集型操作，使用异步方法：

```python
# 异步写入（如果安装了 aiofiles）
await fc.awrite_scratch("large_result.json", content)

# 异步读取
content = await fc.aread_scratch("large_result.json")
```

### 3. 错误处理

正确处理文件访问异常：

```python
from grid_code.infrastructure.file_context import (
    FileAccessError,
    FileNotFoundInContextError,
)

try:
    content = fc.read_scratch("results.json")
except FileNotFoundInContextError:
    print("结果文件不存在")
except FileAccessError:
    print("没有读取权限")
```

### 4. 事件追踪

使用 correlation_id 追踪相关事件：

```python
import uuid

correlation_id = str(uuid.uuid4())

# 发布带关联 ID 的事件
bus.publish(Event(
    event_type=SubagentEvent.TASK_STARTED,
    source="regsearch",
    payload={"query": "..."},
    correlation_id=correlation_id,
))

# 后续查询相关事件
related = bus.get_events_by_correlation(correlation_id)
```

---

## 扩展开发

### 添加新的 Domain Subagent

1. 创建目录结构：
```bash
mkdir -p subagents/fault/{scratch,logs}
```

2. 编写 SKILL.md：
```markdown
---
name: Fault-Subagent
description: 故障研判专家
---
# Fault-Subagent 技能说明
...
```

3. 实现 Subagent 类：
```python
class FaultSubagent(BaseSubagent):
    def __init__(self):
        config = SubagentConfig(
            agent_type=SubagentType.FAULT,
            name="FaultAgent",
            ...
        )
        super().__init__(config)
```

### 添加新的技能

1. 在 `skills/registry.yaml` 中注册：
```yaml
skills:
  - name: fault_analysis
    description: 故障分析技能
    required_tools:
      - analyze_fault
    subagents:
      - fault
```

2. 或创建独立的 SKILL.md：
```bash
mkdir skills/fault_analysis
vim skills/fault_analysis/SKILL.md
```

---

## 常见问题

### Q: 如何在不安装 aiofiles 的情况下使用？

A: 异步方法会自动回退到同步实现：

```python
# 即使没有 aiofiles，这也能正常工作
await fc.awrite_scratch("test.txt", "content")
```

### Q: 如何查看 Subagent 的执行日志？

A: 日志文件位于各 Subagent 的 logs 目录：

```bash
cat subagents/regsearch/logs/$(date +%Y-%m-%d).log
```

### Q: 如何重放历史事件？

A: 使用 EventBus 的 replay_events 方法：

```python
from datetime import datetime, timedelta

since = datetime.now() - timedelta(hours=1)
events = bus.replay_events(since=since)
```

---

## 相关文档

- [API 参考](./API_REFERENCE.md)
- [架构设计](./ARCHITECTURE_DESIGN.md)
- [工作日志](./WORK_LOG.md)
