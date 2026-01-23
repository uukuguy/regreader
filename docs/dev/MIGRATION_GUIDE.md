# RegReader 工作区迁移指南

## 概述

本指南帮助您从旧版分散的工作区结构迁移到新的统一工作区架构。迁移过程安全、可逆，支持渐进式迁移。

## 为什么要迁移？

### 旧版结构的问题

```
project_root/
├── coordinator/           # 93+ 个会话目录混在一起
│   ├── session_20260118_043822/
│   ├── session_20260119_172514/
│   └── ...（93+ 个目录）
├── subagents/            # 所有子代理共享
├── shared/               # 全局共享资源
└── ...（源代码文件）
```

**痛点**：
- 会话目录与源代码混在一起
- 难以清理旧会话
- 无法隔离不同会话的数据
- 备份和迁移困难

### 新版结构的优势

```
.regreader_workspace/     # 单一工作区根目录
├── sessions/             # 所有会话隔离
│   ├── session_20260122_103045/
│   │   ├── coordinator/
│   │   ├── subagents/
│   │   └── shared/
│   └── ...
├── shared/               # 全局共享资源
└── archive/              # 归档的旧会话
```

**优势**：
- ✅ 单一配置点，易于管理
- ✅ 会话完全隔离，互不影响
- ✅ 易于清理、归档、备份
- ✅ 工作区与源代码分离
- ✅ 支持会话级别的移植和共享

## 迁移前准备

### 1. 检查当前结构

```bash
# 查看当前会话数量
ls -d coordinator/session_* | wc -l

# 查看磁盘使用
du -sh coordinator/ subagents/ shared/
```

### 2. 备份重要数据

虽然迁移工具会自动创建备份，但建议手动备份重要数据：

```bash
# 创建完整备份
tar -czf regreader_backup_$(date +%Y%m%d).tar.gz \
    coordinator/ subagents/ shared/

# 验证备份
tar -tzf regreader_backup_*.tar.gz | head
```

### 3. 更新 RegReader

确保使用支持统一工作区的版本：

```bash
# 检查版本
regreader version

# 更新到最新版本
pip install --upgrade regreader
```

### 4. 配置工作区根目录（可选）

默认使用 `.regreader_workspace/`，可以自定义：

```bash
# 在 .env 文件中配置
echo "REGREADER_WORKSPACE_ROOT=.regreader_workspace" >> .env

# 或使用环境变量
export REGREADER_WORKSPACE_ROOT=/path/to/workspace
```

## 迁移步骤

### 方式 1：使用 CLI 命令（推荐）

#### 步骤 1：预览迁移

首先使用 dry-run 模式预览迁移：

```bash
regreader workspace-migrate --dry-run
```

**输出示例**：
```
🔍 检测到 93 个旧版会话需要迁移

预览迁移计划：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
会话 ID                      文件数  大小
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
session_20260118_043822      45      2.3 MB
session_20260119_172514      38      1.8 MB
...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
总计：93 个会话，4,185 个文件，156.7 MB

⚠️  这是预览模式，未执行实际迁移
💡 使用 --no-dry-run 执行实际迁移
```

#### 步骤 2：执行迁移

确认无误后，执行实际迁移：

```bash
# 迁移所有会话（推荐）
regreader workspace-migrate --all --no-dry-run

# 或迁移指定会话
regreader workspace-migrate --session session_20260122_103045 --no-dry-run
```

**迁移过程**：
```
🚀 开始迁移工作区...

[1/93] 迁移 session_20260118_043822
  ├─ 创建备份: backups/session_20260118_043822_20260122_103045.tar.gz
  ├─ 复制文件: 45 个文件
  ├─ 验证完整性: ✓
  └─ 完成 (2.3 MB, 1.2s)

[2/93] 迁移 session_20260119_172514
  ├─ 创建备份: backups/session_20260119_172514_20260122_103045.tar.gz
  ├─ 复制文件: 38 个文件
  ├─ 验证完整性: ✓
  └─ 完成 (1.8 MB, 0.9s)

...

✅ 迁移完成！
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
成功: 93 个会话
失败: 0 个会话
总耗时: 2m 15s
总大小: 156.7 MB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 步骤 3：验证迁移

```bash
# 查看工作区信息
regreader workspace-info

# 列出所有会话
regreader workspace-list

# 检查特定会话
ls -la .regreader_workspace/sessions/session_20260122_103045/
```

#### 步骤 4：测试功能

```bash
# 测试搜索功能
regreader search "母线失压" -r angui_2024

# 测试 Agent 功能
regreader ask "测试查询" -r angui_2024 --agent claude
```

#### 步骤 5：清理旧版目录（可选）

确认一切正常后，可以删除旧版目录：

```bash
# ⚠️  警告：此操作不可逆！确保已验证迁移成功

# 删除旧版会话目录
rm -rf coordinator/

# 删除旧版子代理目录
rm -rf subagents/

# 保留 shared/ 目录（通过符号链接使用）
```

### 方式 2：使用 Python API

如果需要更细粒度的控制，可以使用 Python API：

```python
from pathlib import Path
from regreader.core.config import get_settings
from regreader.workspace import WorkspaceManager, WorkspaceMigrator

# 初始化
settings = get_settings()
workspace_manager = WorkspaceManager(settings.workspace_root)
migrator = WorkspaceMigrator(workspace_manager)
migrator.project_root = Path.cwd()

# 检测旧版会话
legacy_sessions = migrator.detect_legacy_sessions()
print(f"检测到 {len(legacy_sessions)} 个旧版会话")

# 获取迁移摘要
summary = migrator.get_migration_summary()
print(f"待迁移: {summary['legacy_sessions_count']}")
print(f"已迁移: {summary['migrated_sessions_count']}")

# 迁移单个会话
report = migrator.migrate_session(
    "session_20260122_103045",
    dry_run=False,
    backup=True
)

if report.success:
    print(f"✓ 迁移成功: {report.files_migrated} 个文件")
else:
    print(f"✗ 迁移失败: {report.errors}")

# 迁移所有会话
reports = migrator.migrate_all_sessions(dry_run=False, backup=True)
success_count = sum(1 for r in reports if r.success)
print(f"成功迁移 {success_count}/{len(reports)} 个会话")

# 迁移共享资源
migrator.migrate_shared_resources(dry_run=False)
```

## 渐进式迁移策略

如果不想一次性迁移所有会话，可以采用渐进式策略：

### 阶段 1：新会话使用新结构

```bash
# 配置工作区根目录
export REGREADER_WORKSPACE_ROOT=.regreader_workspace

# 新会话自动使用新结构
regreader ask "新查询" -r angui_2024 --agent claude
```

旧会话仍然可以正常访问（通过 LegacyWorkspaceAdapter）。

### 阶段 2：按需迁移旧会话

```bash
# 迁移最近使用的会话
regreader workspace-migrate --session session_20260122_103045 --no-dry-run

# 迁移特定日期范围的会话
for session in coordinator/session_202601*; do
    session_id=$(basename $session)
    regreader workspace-migrate --session $session_id --no-dry-run
done
```

### 阶段 3：批量迁移剩余会话

```bash
# 迁移所有剩余会话
regreader workspace-migrate --all --no-dry-run
```

## 回滚迁移

如果迁移后遇到问题，可以回滚：

### 使用 CLI 回滚

```bash
# 回滚单个会话（从备份恢复）
regreader workspace-rollback session_20260122_103045
```

### 使用 Python API 回滚

```python
from regreader.workspace import WorkspaceManager, WorkspaceMigrator

workspace_manager = WorkspaceManager(".regreader_workspace")
migrator = WorkspaceMigrator(workspace_manager)

# 回滚迁移
success = migrator.rollback_migration("session_20260122_103045")
if success:
    print("✓ 回滚成功")
else:
    print("✗ 回滚失败")
```

### 手动回滚

如果自动回滚失败，可以手动恢复：

```bash
# 1. 从备份恢复
cd backups/
tar -xzf session_20260122_103045_*.tar.gz -C ../

# 2. 删除新结构中的会话
rm -rf .regreader_workspace/sessions/session_20260122_103045/

# 3. 验证旧版会话可用
ls -la coordinator/session_20260122_103045/
```

## 常见问题

### Q1: 迁移会删除旧版目录吗？

**A**: 不会。迁移只是复制文件到新结构，旧版目录保持不变。您需要手动删除旧版目录。

### Q2: 迁移失败怎么办？

**A**: 迁移工具会自动创建备份。如果失败：
1. 检查错误信息
2. 使用 `rollback_migration()` 回滚
3. 或从 `backups/` 目录手动恢复

### Q3: 可以自定义工作区位置吗？

**A**: 可以。通过环境变量配置：
```bash
export REGREADER_WORKSPACE_ROOT=/custom/path
```

### Q4: 迁移会影响正在运行的会话吗？

**A**: 建议在没有活动会话时进行迁移。如果有活动会话，先完成或终止它们。

### Q5: 备份文件占用太多空间怎么办？

**A**: 迁移验证成功后，可以删除备份：
```bash
rm -rf backups/
```

或使用 `--no-backup` 选项跳过备份（不推荐）：
```bash
regreader workspace-migrate --all --no-backup --no-dry-run
```

### Q6: 如何验证迁移完整性？

**A**: 迁移工具会自动验证文件数量和大小。您也可以手动验证：
```bash
# 比较文件数量
find coordinator/session_20260122_103045 -type f | wc -l
find .regreader_workspace/sessions/session_20260122_103045 -type f | wc -l

# 比较目录大小
du -sh coordinator/session_20260122_103045
du -sh .regreader_workspace/sessions/session_20260122_103045
```

### Q7: 迁移后旧代码还能工作吗？

**A**: 可以。LegacyWorkspaceAdapter 提供向后兼容：
- 优先使用新结构
- 自动回退到旧结构
- 透明路径解析

### Q8: 如何迁移共享资源？

**A**: 使用专门的命令：
```bash
regreader workspace-migrate-shared --no-dry-run
```

或在 Python 中：
```python
migrator.migrate_shared_resources(dry_run=False)
```

### Q9: 迁移需要多长时间？

**A**: 取决于会话数量和文件大小：
- 小型项目（<10 会话）：< 1 分钟
- 中型项目（10-50 会话）：1-5 分钟
- 大型项目（50-100 会话）：5-15 分钟

### Q10: 可以在 CI/CD 中自动迁移吗？

**A**: 可以。使用 `--force` 跳过确认：
```bash
regreader workspace-migrate --all --no-dry-run --force
```

## 迁移检查清单

使用此检查清单确保迁移顺利：

- [ ] 备份重要数据
- [ ] 更新 RegReader 到最新版本
- [ ] 配置工作区根目录（如需自定义）
- [ ] 使用 `--dry-run` 预览迁移
- [ ] 执行实际迁移
- [ ] 验证迁移完整性
- [ ] 测试核心功能
- [ ] 清理旧版目录（可选）
- [ ] 删除备份文件（可选）
- [ ] 更新文档和脚本

## 最佳实践

### 1. 分批迁移

对于大型项目，建议分批迁移：

```bash
# 第一批：最近 10 个会话
ls -t coordinator/session_* | head -10 | while read session; do
    session_id=$(basename $session)
    regreader workspace-migrate --session $session_id --no-dry-run
done

# 验证第一批
regreader workspace-list

# 第二批：剩余会话
regreader workspace-migrate --all --no-dry-run
```

### 2. 保留备份

至少保留备份 7 天，确认无问题后再删除：

```bash
# 7 天后删除备份
find backups/ -name "*.tar.gz" -mtime +7 -delete
```

### 3. 监控磁盘空间

迁移会临时占用双倍空间：

```bash
# 检查可用空间
df -h .

# 如果空间不足，先清理旧会话
regreader workspace-cleanup --retention-days 30
```

### 4. 更新脚本

如果有自定义脚本使用旧路径，需要更新：

```bash
# 旧路径
coordinator/session_*/plan.md

# 新路径
.regreader_workspace/sessions/session_*/coordinator/plan.md
```

### 5. 配置 .gitignore

确保工作区不被 git 跟踪：

```bash
# 添加到 .gitignore
echo ".regreader_workspace/" >> .gitignore
echo "backups/" >> .gitignore
```

## 获取帮助

如果遇到问题：

1. **查看日志**：
   ```bash
   tail -f .regreader_workspace/sessions/*/coordinator/logs/events.jsonl
   ```

2. **查看迁移报告**：
   ```python
   from regreader.workspace import WorkspaceManager, WorkspaceMigrator

   workspace_manager = WorkspaceManager(".regreader_workspace")
   migrator = WorkspaceMigrator(workspace_manager)
   summary = migrator.get_migration_summary()
   print(summary)
   ```

3. **提交 Issue**：
   - GitHub: https://github.com/your-org/regreader/issues
   - 包含错误信息和迁移报告

4. **查看文档**：
   - 架构文档：`docs/dev/WORKSPACE_ARCHITECTURE.md`
   - API 参考：`docs/bash-fs-paradiam/API_REFERENCE.md`

## 总结

统一工作区架构提供了更好的会话隔离、管理和可移植性。迁移过程安全、可逆，支持渐进式迁移。按照本指南操作，您可以顺利完成迁移并享受新架构的优势。
