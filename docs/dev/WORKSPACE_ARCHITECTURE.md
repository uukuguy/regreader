# RegReader 统一工作区架构设计

## 概述

RegReader 统一工作区架构将原本分散在项目根目录的多个目录（`coordinator/`、`subagents/`、`shared/`）整合到单一可配置的工作区根目录中，实现会话级别的目录隔离和动态创建。

### 设计目标

1. **单一配置点**：通过一个环境变量控制所有工作区位置
2. **会话隔离**：每个会话拥有完整的独立工作区子目录
3. **易于清理**：可以归档/删除旧会话而不影响其他会话
4. **可移植性**：通过复制目录即可移动/共享会话
5. **清晰分离**：工作区与源代码分离，不纳入 git 版本控制

## 目录结构

### 新版统一结构

```
<workspace_root>/                          # 可配置（默认：.regreader_workspace/）
├── sessions/                              # 所有会话数据
│   ├── session_20260122_103045/          # 单个会话工作区
│   │   ├── coordinator/                   # 协调器工作区
│   │   │   ├── plan.md                    # 任务规划
│   │   │   ├── session_state.json         # 会话状态
│   │   │   ├── call_stack.json            # 调用栈
│   │   │   └── logs/                      # 日志目录
│   │   │       └── events.jsonl           # 事件日志
│   │   ├── subagents/                    # 子代理工作区
│   │   │   ├── regsearch/                # RegSearch 子代理
│   │   │   │   ├── scratch/              # 临时结果
│   │   │   │   └── logs/                 # 日志
│   │   │   ├── search/                   # Search 组件
│   │   │   ├── table/                    # Table 组件
│   │   │   └── reference/                # Reference 组件
│   │   └── shared/                       # 会话特定共享资源
│   └── active -> session_20260122_103045/ # 活动会话符号链接
├── shared/                                # 全局共享资源（只读）
│   ├── data -> ../../data/storage/        # 数据存储符号链接
│   ├── docs/                              # 工具使用指南
│   ├── templates/                         # 输出模板
│   └── skills/                            # 技能定义
├── archive/                               # 归档会话
│   └── 2026-01/
│       └── session_20260118_043822.tar.gz
└── workspace.json                         # 工作区元数据
```

### 旧版分散结构（已弃用）

```
project_root/
├── coordinator/                           # 协调器目录（93+ 会话）
│   ├── session_20260118_043822/
│   ├── session_20260119_172514/
│   └── ...
├── subagents/                             # 子代理目录
│   ├── regsearch/
│   ├── search/
│   ├── table/
│   └── reference/
└── shared/                                # 共享资源
    ├── data/
    ├── docs/
    └── templates/
```

## 核心组件

### 1. SessionWorkspace

会话工作区的数据类抽象，提供路径访问器。

**位置**：`src/regreader/workspace/session.py`

**职责**：
- 封装会话工作区的目录结构
- 提供类型安全的路径访问
- 创建会话目录结构

**关键属性**：
```python
@dataclass
class SessionWorkspace:
    session_id: str                    # 会话 ID
    workspace_root: Path               # 工作区根目录

    @property
    def session_dir(self) -> Path:     # 会话目录
    @property
    def coordinator_dir(self) -> Path: # 协调器目录
    @property
    def subagents_dir(self) -> Path:   # 子代理目录
    @property
    def shared_dir(self) -> Path:      # 共享目录
    @property
    def logs_dir(self) -> Path:        # 日志目录
```

**关键方法**：
- `get_subagent_dir(subagent_name: str) -> Path`：获取指定子代理的目录
- `ensure_structure() -> None`：创建会话目录结构

### 2. WorkspaceManager

工作区生命周期管理器，负责会话的创建、归档、清理。

**位置**：`src/regreader/workspace/manager.py`

**职责**：
- 创建和管理会话工作区
- 归档和清理旧会话
- 管理活动会话
- 维护工作区元数据

**关键方法**：
```python
class WorkspaceManager:
    def create_session(self, session_id: str | None = None) -> SessionWorkspace
    def get_session(self, session_id: str) -> SessionWorkspace
    def get_active_session(self) -> SessionWorkspace
    def set_active_session(self, session_id: str) -> None
    def list_sessions(self, include_archived: bool = False) -> list[str]
    def archive_session(self, session_id: str) -> Path
    def cleanup_old_sessions(self, retention_days: int) -> list[str]
    def get_shared_path(self, relative_path: str) -> Path
```

**会话生命周期**：
1. **创建**：`create_session()` 创建新会话目录结构
2. **使用**：通过 `get_session()` 获取会话工作区
3. **归档**：`archive_session()` 压缩并移动到 archive/
4. **清理**：`cleanup_old_sessions()` 根据保留策略清理

### 3. WorkspaceMigrator

从旧版分散结构迁移到统一工作区的工具。

**位置**：`src/regreader/workspace/migrator.py`

**职责**：
- 检测旧版会话
- 迁移会话到新结构
- 创建备份
- 支持回滚

**关键方法**：
```python
class WorkspaceMigrator:
    def detect_legacy_sessions(self) -> list[str]
    def migrate_session(self, session_id: str, dry_run: bool = True,
                       backup: bool = True) -> MigrationReport
    def migrate_all_sessions(self, dry_run: bool = True,
                            backup: bool = True) -> list[MigrationReport]
    def migrate_shared_resources(self, dry_run: bool = True) -> bool
    def rollback_migration(self, session_id: str) -> bool
    def get_migration_summary(self) -> dict[str, Any]
```

**迁移流程**：
1. **检测**：扫描 `coordinator/` 目录查找旧版会话
2. **备份**：创建 tar.gz 备份到 `backups/`
3. **迁移**：复制文件到新结构，保留权限
4. **验证**：检查迁移完整性
5. **清理**：可选删除旧版目录

### 4. LegacyWorkspaceAdapter

向后兼容层，支持旧版和新版结构共存。

**位置**：`src/regreader/workspace/compat.py`

**职责**：
- 检测旧版结构
- 路径解析（优先新结构）
- 迁移状态跟踪
- 发出弃用警告

**关键方法**：
```python
class LegacyWorkspaceAdapter:
    def get_session_dir(self, session_id: str) -> Path
    def get_subagent_dir(self, subagent_name: str) -> Path
    def get_shared_dir(self) -> Path
    def list_legacy_sessions(self) -> list[str]
    def is_session_migrated(self, session_id: str) -> bool
    def get_migration_status(self) -> dict[str, Any]
```

**路径解析优先级**：
1. 新结构：`.regreader_workspace/sessions/{session_id}/`
2. 旧结构：`coordinator/{session_id}/`
3. 默认：新结构（用于创建）

## 配置选项

通过环境变量或 `.env` 文件配置：

```bash
# 工作区根目录
REGREADER_WORKSPACE_ROOT=.regreader_workspace

# 会话保留天数
REGREADER_WORKSPACE_SESSION_RETENTION_DAYS=7

# 是否启用归档
REGREADER_WORKSPACE_ARCHIVE_ENABLED=true

# 最大活动会话数
REGREADER_WORKSPACE_MAX_SESSIONS=100
```

**配置字段**（`src/regreader/core/config.py`）：
```python
workspace_root: Path = Field(
    default=Path(".regreader_workspace"),
    description="工作区根目录",
)

workspace_session_retention_days: int = Field(
    default=7,
    description="会话保留天数",
)

workspace_archive_enabled: bool = Field(
    default=True,
    description="是否归档旧会话",
)

workspace_max_sessions: int = Field(
    default=100,
    description="最大活动会话数",
)
```

## 与现有组件的集成

### FileContext 集成

**文件**：`src/regreader/infrastructure/file_context.py`

**变更**：
- 将 `base_dir` 参数替换为 `session_workspace: SessionWorkspace`
- 使用 `session_workspace.get_subagent_dir()` 解析路径
- 支持会话特定和全局共享资源

**示例**：
```python
@dataclass
class FileContext:
    subagent_name: str
    session_workspace: SessionWorkspace  # 新增
    can_read: list[Path] = field(default_factory=list)
    can_write: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_dir = self.session_workspace.get_subagent_dir(self.subagent_name)

        if not self.can_read:
            self.can_read = [
                self.base_dir,
                self.session_workspace.shared_dir,  # 会话共享
                self.session_workspace.workspace_root / "shared",  # 全局共享
            ]
```

### HierarchyManager 集成

**文件**：`src/regreader/orchestration/hierarchy_manager.py`

**变更**：
- 添加 `workspace_manager: WorkspaceManager` 参数
- 使用 `workspace_manager.create_session()` 创建会话
- 使用 `session_workspace.coordinator_dir` 作为会话目录

**示例**：
```python
class HierarchyManager:
    def __init__(
        self,
        session_id: str | None = None,
        workspace_manager: WorkspaceManager | None = None
    ):
        settings = get_settings()
        self.workspace_manager = workspace_manager or WorkspaceManager(
            settings.workspace_root
        )
        self.session_workspace = self.workspace_manager.create_session(session_id)
        self.session_id = self.session_workspace.session_id
        self.session_dir = self.session_workspace.coordinator_dir
```

### EventBus 集成

**文件**：`src/regreader/infrastructure/event_bus.py`

**变更**：
- 添加 `session_workspace: SessionWorkspace` 参数
- 使用 `session_workspace.logs_dir` 作为事件目录

### SecurityGuard 集成

**文件**：`src/regreader/infrastructure/security_guard.py`

**变更**：
- 添加 `session_workspace: SessionWorkspace` 参数
- 使用 `session_workspace.logs_dir` 作为审计目录
- 使权限路径会话感知

## CLI 命令

### 工作区信息

```bash
regreader workspace-info
```

显示工作区统计信息：
- 工作区根目录
- 活动会话数
- 归档会话数
- 磁盘使用情况

### 迁移

```bash
# 预览迁移（不执行）
regreader workspace-migrate --dry-run

# 迁移所有会话
regreader workspace-migrate --all --no-dry-run

# 迁移指定会话
regreader workspace-migrate --session session_20260122_103045 --no-dry-run

# 不创建备份
regreader workspace-migrate --all --no-backup --no-dry-run
```

### 清理

```bash
# 清理旧会话（交互式确认）
regreader workspace-cleanup

# 自定义保留天数
regreader workspace-cleanup --retention-days 14

# 跳过确认
regreader workspace-cleanup --force
```

### 列表

```bash
# 列出活动会话
regreader workspace-list

# 包含归档会话
regreader workspace-list --include-archived
```

### 归档

```bash
# 归档指定会话
regreader workspace-archive session_20260122_103045
```

## 迁移策略

### 渐进式迁移

1. **阶段 1：共存**
   - 新会话使用新结构
   - 旧会话保持旧结构
   - LegacyWorkspaceAdapter 提供透明访问

2. **阶段 2：迁移**
   - 使用 `workspace-migrate` 命令迁移
   - 创建备份以防万一
   - 验证迁移完整性

3. **阶段 3：清理**
   - 删除旧版目录
   - 移除向后兼容代码
   - 更新文档

### 回滚计划

如果遇到问题：

1. **立即回滚**：
   - 使用 `rollback_migration()` 方法
   - 从备份恢复
   - 保持旧版结构不变

2. **部分回滚**：
   - 禁用新会话的新结构
   - 继续使用旧结构
   - 修复问题后重新启用

3. **手动回滚**：
   - 从 `.regreader_workspace/sessions/` 复制回 `coordinator/`
   - 删除 `.regreader_workspace/` 目录
   - 重启应用

## 性能考虑

### 符号链接

- 使用符号链接标记活动会话
- 避免重复复制大文件
- 快速访问当前会话

### 归档策略

- 使用 tar.gz 压缩归档
- 按月组织归档文件
- 可配置保留策略

### 并发访问

- 支持多个 WorkspaceManager 实例
- 文件系统级别的并发安全
- 无需额外锁机制

## 安全考虑

### 目录隔离

- 每个会话有独立目录
- 子代理只能访问自己的目录
- 共享资源为只读

### 权限控制

- 保留文件权限
- 审计日志记录
- SecurityGuard 集成

### 备份保护

- 自动创建备份
- 压缩存储
- 可验证完整性

## 测试覆盖

### 单元测试

- `test_session.py`：SessionWorkspace 测试（15 个测试）
- `test_manager.py`：WorkspaceManager 测试（25 个测试）
- `test_migrator.py`：WorkspaceMigrator 测试（20 个测试）
- `test_compat.py`：LegacyWorkspaceAdapter 测试（30+ 个测试）

### 集成测试

- `test_integration.py`：端到端工作流测试（15 个测试）
- 完整迁移工作流
- 混合结构操作
- 并发访问
- 权限保留

## 未来增强

### 会话快照

- 保存/恢复会话状态
- 时间点快照
- 增量备份

### 会话共享

- 导出/导入会话
- 协作支持
- 会话模板

### 工作区分析

- 使用统计
- 磁盘使用分析
- 性能指标

### 云同步

- S3/GCS 同步
- 自动备份
- 跨机器共享

## 参考资料

- **迁移指南**：`docs/dev/MIGRATION_GUIDE.md`
- **API 参考**：`docs/bash-fs-paradiam/API_REFERENCE.md`
- **用户指南**：`docs/bash-fs-paradiam/USER_GUIDE.md`
- **设计文档**：`docs/dev/DESIGN_DOCUMENT.md`
