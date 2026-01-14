# RegReader Bash+FS Subagents 架构演进方案

## 一、背景与目标

### 1.1 当前状态
RegReader 已实现完善的 Subagents 架构：
- **4 种 Subagent**：SEARCH / TABLE / REFERENCE / DISCOVERY
- **协调层**：QueryAnalyzer → SubagentRouter → ResultAggregator
- **三框架并行**：Claude SDK / Pydantic AI / LangGraph
- **MCP 工具层**：16+ 工具，分为 BASE/MULTI_HOP/CONTEXT/DISCOVERY

### 1.2 演进目标
将现有架构与 Bash+FS 范式融合：
1. **规程检索作为领域子代理** - RegSearch-Subagent 封装现有 4 个 Subagent
2. **公共组件层** - 抽取可跨子代理复用的基础设施
3. **子代理编排** - 支持文件系统通信和组合编排
4. **技能系统** - SKILL.md + 脚本 + 工作流组合

---

## 二、分层架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                     业务交互层 (CLI / API)                          │
├─────────────────────────────────────────────────────────────────────┤
│                     Coordinator (协调器)                            │
│  QueryAnalyzer → SubagentRouter → ResultAggregator                  │
├─────────────────────────────────────────────────────────────────────┤
│                     Domain Subagents 层                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                │
│  │RegSearch-Sub │ │Fault-Sub     │ │Assessment-Sub│  (预留扩展)    │
│  │(规程检索)    │ │(故障研判)    │ │(运行评估)    │                │
│  │  ┌────────┐  │ └──────────────┘ └──────────────┘                │
│  │  │SEARCH  │  │                                                   │
│  │  │TABLE   │  │ ┌──────────────┐ ┌──────────────┐                │
│  │  │REFERENCE│  │ │Exec-Sub     │ │Validator-Sub │  (支撑代理)    │
│  │  │DISCOVERY│  │ │(执行代理)   │ │(验证代理)    │                │
│  │  └────────┘  │ └──────────────┘ └──────────────┘                │
│  └──────────────┘                                                   │
├─────────────────────────────────────────────────────────────────────┤
│                     公共基础设施层                                  │
│  FileContext │ SkillLoader │ EventBus │ SecurityGuard              │
├─────────────────────────────────────────────────────────────────────┤
│                     现有核心层（保持不变）                          │
│  MCP Tools │ PageStore │ HybridSearch │ Embedding                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、目录结构设计

```
regreader/
├── coordinator/                      # Coordinator 工作区（新增）
│   ├── CLAUDE.md                     # 项目导读入口
│   ├── plan.md                       # 任务规划
│   ├── session_state.json            # 会话状态
│   └── logs/
│
├── subagents/                        # Subagent 工作区（新增）
│   ├── regsearch/                    # RegSearch-Subagent
│   │   ├── SKILL.md                  # 技能说明书
│   │   ├── scripts/                  # 工作流脚本
│   │   ├── scratch/                  # 临时结果
│   │   └── logs/
│   ├── exec/                         # Exec-Subagent（预留）
│   │   ├── SKILL.md
│   │   ├── queue/                    # 执行请求队列
│   │   └── results/
│   └── validator/                    # Validator-Subagent（预留）
│       ├── rules.md
│       └── audit.log
│
├── shared/                           # 共享只读资源（新增）
│   ├── data/ → data/storage/         # 符号链接到现有数据
│   ├── docs/                         # 工具使用指南
│   └── templates/                    # 输出模板
│
├── skills/                           # 技能库（新增）
│   ├── registry.yaml                 # 技能注册表
│   ├── simple_search/
│   ├── table_lookup/
│   └── cross_ref/
│
└── src/regreader/                    # 源代码（增强）
    ├── infrastructure/               # 公共基础设施（新增）
    │   ├── file_context.py
    │   ├── skill_loader.py
    │   ├── event_bus.py
    │   └── security_guard.py
    ├── subagents/                    # 现有（增强）
    ├── orchestrator/                 # 现有（保持）
    ├── agents/                       # 现有（保持）
    ├── mcp/                          # 现有（保持）
    └── storage/                      # 现有（保持）
```

---

## 四、核心组件设计

### 4.1 FileContext（文件上下文管理器）

**职责**：实现 Bash+FS 范式的文件读写隔离

```python
# src/regreader/infrastructure/file_context.py

@dataclass
class FileContext:
    subagent_name: str
    base_dir: Path

    # 权限控制
    can_read: list[Path]    # 可读白名单
    can_write: list[Path]   # 可写白名单

    def read_skill(self) -> str
    def write_scratch(self, filename: str, content: str) -> Path
    def read_shared(self, path: str) -> str
    def get_plan(self) -> dict
    def update_todo(self, items: list[str]) -> None
    def log(self, message: str) -> None
```

### 4.2 SkillLoader（技能加载器）

**职责**：动态加载 SKILL.md 定义的技能包

```python
# src/regreader/infrastructure/skill_loader.py

@dataclass
class Skill:
    name: str
    description: str
    entry_point: str
    required_tools: list[str]
    input_schema: dict
    output_schema: dict
    examples: list[dict]

class SkillLoader:
    def load_all(self) -> dict[str, Skill]
    def get_skill(self, name: str) -> Skill
    def get_skills_for_subagent(self, subagent_type: str) -> list[Skill]
```

### 4.3 EventBus（事件总线）

**职责**：Subagent 间松耦合通信 + 文件持久化

```python
# src/regreader/infrastructure/event_bus.py

class SubagentEvent(Enum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    HANDOFF_REQUEST = "handoff_request"

@dataclass
class Event:
    event_type: SubagentEvent
    source: str
    target: str | None
    payload: dict
    timestamp: datetime

class EventBus:
    def publish(self, event: Event) -> None    # 同时写入文件
    def subscribe(self, event_type: SubagentEvent, handler: Callable)
    def replay_events(self, since: datetime) -> list[Event]  # 从文件恢复
```

### 4.4 SecurityGuard（安全守卫）

**职责**：瑞士奶酪防御（目录隔离 + 权限控制）

```python
# src/regreader/infrastructure/security_guard.py

@dataclass
class PermissionMatrix:
    subagent_name: str
    readable_dirs: list[Path]
    writable_dirs: list[Path]
    allowed_tools: list[str]
    can_execute_scripts: bool

class SecurityGuard:
    def check_file_access(self, subagent: str, path: Path, operation: str) -> bool
    def check_tool_access(self, subagent: str, tool_name: str) -> bool
    def audit_log(self, action: str, subagent: str, details: dict) -> None
```

---

## 五、RegSearch-Subagent 设计

### 5.1 整合现有 4 个 Subagent

```python
# 新增 SubagentType
class SubagentType(str, Enum):
    REGSEARCH = "regsearch"    # 新增：整合后的领域子代理
    SEARCH = "search"          # 保留：作为 RegSearch 的内部组件
    TABLE = "table"
    REFERENCE = "reference"
    DISCOVERY = "discovery"
```

### 5.2 RegSearch SKILL.md 结构

```markdown
# RegSearch-Subagent 技能说明

## 角色定位
规程文档检索专家

## 内部组件
- SearchAgent: 文档搜索与导航
- TableAgent: 表格处理
- ReferenceAgent: 引用追踪
- DiscoveryAgent: 语义分析（可选）

## 标准工作流
1. 简单查询: get_toc → smart_search → read_page_range
2. 表格查询: search_tables → get_table_by_id → lookup_annotation
3. 引用追踪: resolve_reference → read_page_range

## 输入输出规范
- 输入: scratch/current_task.md
- 输出: scratch/results.json, scratch/final_report.md
```

### 5.3 增强 BaseSubagent

```python
# src/regreader/subagents/base.py 增强

class BaseSubagent(ABC):
    def __init__(
        self,
        config: SubagentConfig,
        file_context: FileContext | None = None  # 新增
    ):
        self.config = config
        self.file_context = file_context

    async def execute(self, context: SubagentContext) -> SubagentResult:
        # 1. 从文件读取任务（如果有 FileContext）
        if self.file_context:
            task = self.file_context.read_scratch("current_task.md")

        # 2. 执行核心逻辑
        result = await self._execute_core(context)

        # 3. 写入结果文件（如果有 FileContext）
        if self.file_context:
            self.file_context.write_scratch("results.json", result.to_json())

        return result
```

### 5.4 增强 SubagentConfig

```python
# src/regreader/subagents/config.py 增强

@dataclass
class SubagentConfig:
    # 现有字段保持...

    # 新增文件系统配置
    work_dir: Path = field(default_factory=lambda: Path("subagents"))
    scratch_dir: str = "scratch"
    logs_dir: str = "logs"
    readable_dirs: list[str] = field(default_factory=lambda: ["shared/"])
    writable_dirs: list[str] = field(default_factory=list)
```

---

## 六、子代理间通信设计

### 6.1 文件系统通信（主要方式）

```
Coordinator                    RegSearch-Subagent
    │                                │
    │ 写入 plan.md                   │
    ├────────────────────────────>   │
    │                                │ 读取 plan.md
    │                                │ 执行搜索
    │                                │ 写入 scratch/results.json
    │  <─────────────────────────────┤
    │ 读取 scratch/results.json      │
```

### 6.2 权限矩阵

| Subagent | 可读目录 | 可写目录 | 可用工具 |
|----------|---------|---------|---------|
| regsearch | shared/, coordinator/plan.md | regsearch/scratch/, logs/ | 全部 16 个 |
| exec | shared/, */scratch/ | exec/results/, logs/ | 无（执行脚本） |
| validator | */scratch/, exec/results/ | validator/audit.log | 无（只验证） |

---

## 七、实施计划

### Phase 1: 基础设施层

**目标**：创建公共基础设施组件

**任务**：
1. 创建 `src/regreader/infrastructure/` 目录
2. 实现 `FileContext` - 文件上下文管理器
3. 实现 `SkillLoader` - 技能加载器
4. 实现 `EventBus` - 事件总线
5. 实现 `SecurityGuard` - 安全守卫

**关键文件**：
- `src/regreader/infrastructure/__init__.py`
- `src/regreader/infrastructure/file_context.py`
- `src/regreader/infrastructure/skill_loader.py`
- `src/regreader/infrastructure/event_bus.py`
- `src/regreader/infrastructure/security_guard.py`

### Phase 2: 目录结构

**目标**：创建 Bash+FS 范式的目录布局

**任务**：
1. 创建 `coordinator/` 工作区目录
2. 创建 `subagents/regsearch/` 目录结构
3. 创建 `shared/` 共享资源目录
4. 创建 `skills/` 技能库目录
5. 编写初始 `SKILL.md` 文件

**关键文件**：
- `coordinator/CLAUDE.md`
- `subagents/regsearch/SKILL.md`
- `skills/registry.yaml`

### Phase 3: RegSearch-Subagent 整合

**目标**：将现有 4 个 Subagent 整合为 RegSearch

**任务**：
1. 增强 `BaseSubagent` 支持 `FileContext`
2. 增强 `SubagentConfig` 添加目录配置
3. 创建 `RegSearchSubagent` 包装类
4. 更新 `SubagentType` 枚举
5. 保持现有 4 个 Subagent 作为内部组件

**关键文件**：
- `src/regreader/subagents/base.py` (增强)
- `src/regreader/subagents/config.py` (增强)
- `src/regreader/subagents/regsearch/__init__.py` (新增)
- `src/regreader/subagents/regsearch/subagent.py` (新增)

### Phase 4: Coordinator 升级

**目标**：支持文件系统任务分派

**任务**：
1. 实现 `plan.md` 生成和管理
2. 集成 `EventBus` 事件发布
3. 更新 `ResultAggregator` 支持文件读取
4. 添加任务状态持久化

**关键文件**：
- `src/regreader/orchestrator/coordinator.py` (新增)
- `src/regreader/orchestrator/aggregator.py` (增强)

### Phase 5: 测试与验证

**目标**：确保架构演进不破坏现有功能

**任务**：
1. 单元测试：各基础设施组件
2. 集成测试：RegSearch-Subagent 完整流程
3. 端到端测试：CLI 交互验证
4. 性能基准：对比演进前后

**关键文件**：
- `tests/bash-fs-paradiam/test_file_context.py`
- `tests/bash-fs-paradiam/test_skill_loader.py`
- `tests/bash-fs-paradiam/test_regsearch_subagent.py`

---

## 八、验证方案

### 8.1 单元测试

```bash
# 运行基础设施层测试
pytest tests/bash-fs-paradiam/test_infrastructure.py -xvs

# 运行 RegSearch-Subagent 测试
pytest tests/bash-fs-paradiam/test_regsearch_subagent.py -xvs
```

### 8.2 集成测试

```bash
# 验证完整工作流
regreader chat -r angui_2024 --agent pydantic
# 测试查询：母线失压如何处理?

# 验证文件系统状态
ls -la subagents/regsearch/scratch/
cat subagents/regsearch/scratch/results.json
```

### 8.3 端到端验证

```bash
# 验证 CLI 命令
regreader search "母线失压" -r angui_2024

# 验证技能加载
regreader skills list

# 验证事件日志
cat coordinator/logs/events.jsonl
```

---

## 九、关键决策点

### 9.1 保持向后兼容
- 现有 4 个 Subagent（SEARCH/TABLE/REFERENCE/DISCOVERY）作为 RegSearch 的内部组件保留
- 现有 MCP 工具层、存储层、索引层完全不变
- CLI 命令保持兼容

### 9.2 渐进式迁移
- Phase 1-2 纯新增，不修改现有代码
- Phase 3 增强现有类，添加可选参数
- Phase 4 才涉及协调层改动

### 9.3 可选性
- `FileContext` 作为可选参数，不传则使用原有逻辑
- 事件总线发布是可选的
- 技能系统是独立模块，不影响核心流程

---

## 十、预留扩展点

### 10.1 新增 Domain Subagent

```python
# 添加 Fault-Subagent 示例
class FaultSubagent(BaseSubagent):
    def __init__(self):
        config = SubagentConfig(
            agent_type=SubagentType.FAULT,
            name="FaultAgent",
            tools=["analyze_fault", "get_protection_records"],
            work_dir=Path("subagents/fault"),
        )
        file_context = FileContext(
            subagent_name="fault",
            base_dir=Path("subagents/fault"),
        )
        super().__init__(config, file_context)
```

### 10.2 新增技能

```yaml
# skills/registry.yaml
skills:
  - name: fault_analysis
    description: 故障分析技能
    entry_point: skills/fault_analysis/entry.py
    required_tools:
      - analyze_fault
      - get_protection_records
    subagents:
      - fault
```

### 10.3 Exec-Subagent 队列

```json
// subagents/exec/queue/task_001.json
{
  "task_id": "task_001",
  "requester": "regsearch",
  "command_type": "python_script",
  "script_path": "subagents/regsearch/scripts/search_workflow.py",
  "args": {"query": "母线失压", "reg_id": "angui_2024"},
  "timeout_seconds": 60
}
```

---

## 十一、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 文件系统 I/O 性能 | 使用异步文件操作，关键路径保持内存传递 |
| 目录结构复杂度 | 提供 CLI 初始化命令自动创建 |
| 安全边界模糊 | SecurityGuard 强制白名单检查 |
| 向后兼容性 | FileContext 可选，不传则使用原逻辑 |

---

## 十二、成功标准

1. ✅ RegSearch-Subagent 整合现有 4 个 Subagent，功能等价
2. ✅ 文件系统工作区正常创建和使用
3. ✅ SKILL.md 定义的技能可被加载和识别
4. ✅ 事件总线支持 Subagent 间通信
5. ✅ 现有 CLI 命令保持兼容
6. ✅ 性能无明显下降（<10% 延迟增加）

---

## 十三、用户确认的实施决策

### ✅ 实施范围：Phase 1-5 完整实施
- Phase 1: 基础设施层 (FileContext, SkillLoader, EventBus, SecurityGuard)
- Phase 2: 目录结构 (coordinator/, subagents/, shared/, skills/)
- Phase 3: RegSearch-Subagent 整合
- Phase 4: Coordinator 升级
- Phase 5: 测试与验证

### ✅ 通信模式：可选模式
- `FileContext` 作为可选参数
- 不传则保持原有内存传递逻辑
- 向后兼容，渐进式迁移

### ✅ 技能组织：两级结构
```
subagents/
├── regsearch/
│   └── SKILL.md              # Subagent 级：整体能力描述
│
skills/                        # 工作流级：可复用技能包
├── registry.yaml
├── simple_search/
│   └── SKILL.md
├── table_lookup/
│   └── SKILL.md
└── cross_ref/
    └── SKILL.md
```
