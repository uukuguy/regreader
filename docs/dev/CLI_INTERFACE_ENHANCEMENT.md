# RegReader CLI 界面增强设计文档

## 1. 项目背景

### 1.1 目标

设计并实现一个与 Claude Code 同等或更高水平的精致 CLI 运行界面，用于 RegReader 的 `ask` 和 `chat` 命令。

### 1.2 用户需求

基于 Claude Code 的界面设计，用户期望：

1. **动态底部状态栏** - 当前操作显示在最底部，带动态图标和执行时间
2. **历史记录向上滚动** - 已完成步骤向上滚动，显示状态图标和结果摘要
3. **树状分支结构** - 使用 `├─` 和 `└─` 字符显示操作层级关系
4. **代码差异显示** - 绿色高亮新增内容，清晰的代码块边界
5. **交互式控制** - 键盘快捷键支持

### 1.3 现有基础

RegReader 已具备：
- ✅ 完善的事件系统（14 种事件类型）
- ✅ 精确的时间测量（thinking/API/execution）
- ✅ Rich 库集成
- ✅ 异步架构
- ✅ 回调协议设计

## 2. 设计方案

### 2.1 核心设计理念

**"分层渲染 + 状态机驱动"架构**

```
┌─────────────────────────────────────────────────────────┐
│                    历史记录区域                          │
│  ✓ 步骤 1: 分析查询意图                    (0.5s)       │
│    └─ 识别到：TABLE 类型查询                            │
│  ✓ 步骤 2: 调用 search_tables                           │
│    ├─ 参数: query="母线失压", mode="hybrid"             │
│    └─ 结果: 找到 3 个表格 [P12, P45, P67]              │
│  ⚙ 步骤 3: 提取表格内容              (进行中 2.1s)      │
│    └─ 正在处理表格 2/3...                               │
├─────────────────────────────────────────────────────────┤
│                    当前操作区域                          │
│  🔄 正在调用 get_table_by_id(table_id="tbl_045")...    │
│     [████████████░░░░░░░░] 60% (1.8s)                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 架构层次

#### 2.2.1 显示层（Display Layer）

**新增组件**：

- `EnhancedStatusDisplay` - 增强版状态显示器
  - 继承自现有的 `AgentStatusDisplay`
  - 新增历史记录管理
  - 新增树状结构渲染
  - 新增进度条支持

- `HistoryManager` - 历史记录管理器
  - 存储已完成的步骤
  - 支持滚动显示
  - 支持折叠/展开

- `TreeRenderer` - 树状结构渲染器
  - 使用 Rich Tree 组件
  - 支持嵌套层级
  - 动态更新节点状态

#### 2.2.2 状态机层（State Machine Layer）

**新增组件**：

- `DisplayState` - 显示状态枚举
  - `IDLE` - 空闲
  - `ANALYZING` - 分析中
  - `TOOL_CALLING` - 工具调用中
  - `THINKING` - 思考中
  - `AGGREGATING` - 聚合结果中
  - `COMPLETED` - 完成
  - `ERROR` - 错误

- `StepTracker` - 步骤追踪器
  - 记录每个步骤的开始/结束时间
  - 计算步骤耗时
  - 维护步骤层级关系

#### 2.2.3 渲染层（Rendering Layer）

**增强现有组件**：

- `_render()` 方法增强
  - 分离历史区域和当前操作区域
  - 使用 Rich Layout 进行布局
  - 支持动态高度调整

- `_format_tool_call_end()` 方法增强
  - 添加树状结构前缀
  - 添加结果摘要
  - 添加时间戳

## 3. 技术实现细节

### 3.1 历史记录持久化

使用 `deque` 存储历史步骤，限制最大显示数量（如 50 条）：

```python
from collections import deque

class HistoryManager:
    def __init__(self, max_size: int = 50):
        self._history: deque[StepRecord] = deque(maxlen=max_size)
        self._current_depth: int = 0

    def add_step(self, step: StepRecord) -> None:
        """添加步骤到历史记录"""
        self._history.append(step)

    def render(self) -> Table:
        """渲染历史记录为 Rich Table"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        for step in self._history:
            table.add_row(self._format_step(step))
        return table
```

### 3.2 树状结构渲染

使用 Rich Tree 组件实现层级显示：

```python
from rich.tree import Tree

class TreeRenderer:
    def __init__(self):
        self._root = Tree("🔍 查询执行流程")
        self._current_node = self._root
        self._node_stack: list[Tree] = [self._root]

    def add_child(self, label: str, icon: str = "├─") -> Tree:
        """添加子节点"""
        node = self._current_node.add(f"{icon} {label}")
        return node

    def enter_context(self, node: Tree) -> None:
        """进入子上下文"""
        self._node_stack.append(node)
        self._current_node = node

    def exit_context(self) -> None:
        """退出子上下文"""
        if len(self._node_stack) > 1:
            self._node_stack.pop()
            self._current_node = self._node_stack[-1]
```

### 3.3 进度条实现

使用 Rich Progress 组件显示工具调用进度：

```python
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

class ProgressTracker:
    def __init__(self):
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._tasks: dict[str, int] = {}

    def start_task(self, task_id: str, description: str, total: int = 100) -> None:
        """开始一个新任务"""
        task = self._progress.add_task(description, total=total)
        self._tasks[task_id] = task

    def update_task(self, task_id: str, advance: int = 1) -> None:
        """更新任务进度"""
        if task_id in self._tasks:
            self._progress.update(self._tasks[task_id], advance=advance)
```

### 3.4 动态布局管理

使用 Rich Layout 实现分区显示：

```python
from rich.layout import Layout
from rich.panel import Panel

class EnhancedLayout:
    def __init__(self):
        self._layout = Layout()
        self._layout.split_column(
            Layout(name="history", ratio=3),
            Layout(name="current", ratio=1),
        )

    def update_history(self, content: Table) -> None:
        """更新历史记录区域"""
        self._layout["history"].update(
            Panel(content, title="执行历史", border_style="dim")
        )

    def update_current(self, content: str) -> None:
        """更新当前操作区域"""
        self._layout["current"].update(
            Panel(content, title="当前操作", border_style="bold blue")
        )
```

## 4. 视觉设计规范

### 4.1 图标系统

| 状态 | 图标 | 颜色 | 说明 |
|------|------|------|------|
| 成功 | ✓ | green | 步骤成功完成 |
| 失败 | ✗ | red | 步骤执行失败 |
| 警告 | ⚠ | yellow | 部分成功或有警告 |
| 进行中 | 🔄 | blue | 正在执行 |
| 等待 | ⏳ | dim | 等待执行 |
| 思考 | 💭 | cyan | LLM 思考中 |
| 工具调用 | 🔧 | magenta | 调用 MCP 工具 |
| 结果 | 📊 | green | 返回结果 |

### 4.2 树状结构字符

```
├─ 中间节点
└─ 最后节点
│  垂直连接线
   缩进空格
```

### 4.3 颜色方案

- **主色调**: 蓝色（blue）- 当前操作
- **成功色**: 绿色（green）- 完成步骤
- **警告色**: 黄色（yellow）- 警告信息
- **错误色**: 红色（red）- 错误信息
- **次要色**: 灰色（dim）- 历史记录
- **强调色**: 青色（cyan）- 思考过程

## 5. 实施计划

### 5.1 阶段 1: 核心显示组件（第 1 周）

**优先级**: 🔴 最高

**新建文件**: `src/regreader/agents/shared/enhanced_display.py`

**核心类**:
1. `StepRecord` - 步骤记录（~50 行）
2. `HistoryManager` - 历史记录管理（~150 行）
3. `TreeRenderer` - 树状结构渲染（~100 行）
4. `ProgressTracker` - 进度追踪（~100 行）

**预计代码量**: ~400 行

### 5.2 阶段 2: 集成到现有显示系统（第 2 周）

**优先级**: 🔴 最高

**修改文件**: `src/regreader/agents/shared/display.py`

**修改内容**:
1. 重构 `AgentStatusDisplay._render()` 方法，使用 Layout 分区
2. 集成 `HistoryManager` 和 `TreeRenderer`
3. 添加流式响应支持（`TEXT_DELTA`, `THINKING_DELTA`）
4. 优化事件处理流程

**预计代码量**: ~300 行修改

### 5.3 阶段 3: CLI 命令集成（第 3 周）

**优先级**: 🟡 高

**修改文件**: `src/regreader/cli.py`

**修改内容**:
1. 默认启用增强显示模式
2. 添加 `--simple` 标志切换回简单模式
3. 添加 `--history-size` 参数（默认 50）
4. 更新 `ask` 和 `chat` 命令

**预计代码量**: ~100 行修改

### 5.4 阶段 4: 基础交互控制（第 4 周）

**优先级**: 🟢 中

**新建文件**: `src/regreader/agents/shared/interactive.py`

**功能**:
1. Ctrl+C 优雅退出（保存执行日志）
2. 折叠/展开历史记录（键盘快捷键）
3. 导出执行日志到文件

**预计代码量**: ~200 行

### 5.5 阶段 5: 测试和文档（第 5 周）

**优先级**: 🟢 中

**新建文件**:
- `tests/agents/test_enhanced_display.py` - 单元测试
- 本文档

**测试内容**:
1. 历史记录管理测试
2. 树状结构渲染测试
3. 进度追踪测试
4. 流式响应测试
5. 交互控制测试

**预计代码量**: ~300 行测试

## 6. 关键文件清单

| 文件路径 | 操作 | 说明 | 代码量 |
|---------|------|------|--------|
| `src/regreader/agents/shared/enhanced_display.py` | 新建 | 核心显示组件 | ~400 行 |
| `src/regreader/agents/shared/display.py` | 修改 | 集成增强功能 | ~300 行 |
| `src/regreader/cli.py` | 修改 | CLI 集成 | ~100 行 |
| `src/regreader/agents/shared/interactive.py` | 新建 | 交互控制 | ~200 行 |
| `tests/agents/test_enhanced_display.py` | 新建 | 单元测试 | ~300 行 |

**总计**: ~1300 行新增/修改代码

## 7. 验证方案

### 7.1 基础功能验证

**测试命令**:
```bash
# 测试历史记录和树状结构
regreader ask "母线失压如何处理?" -r angui_2024

# 测试进度条显示
regreader ask "列出所有母线失压相关的表格" -r angui_2024

# 测试流式响应
regreader chat -r angui_2024
> 详细说明母线失压的处理流程
```

**验证要点**:
- ✅ 历史记录向上滚动显示
- ✅ 树状结构层级正确（使用 ├─ └─ 字符）
- ✅ 进度条实时更新
- ✅ 流式响应逐字显示
- ✅ 时间统计准确（thinking/API/execution）

### 7.2 交互控制验证

**测试场景**:
```bash
# 测试 Ctrl+C 优雅退出
regreader chat -r angui_2024
> 长查询...
# 按 Ctrl+C，验证是否保存执行日志

# 测试简单模式切换
regreader ask "查询..." -r angui_2024 --simple
```

**验证要点**:
- ✅ Ctrl+C 能优雅退出并保存日志
- ✅ `--simple` 标志能切换回简单模式
- ✅ 执行日志正确保存到文件

### 7.3 性能和兼容性验证

**测试场景**:
- 长时间运行（10+ 分钟）
- 大量工具调用（50+ 次）
- 不同终端模拟器（iTerm2, Terminal.app, VS Code Terminal）

**验证要点**:
- ✅ 内存占用稳定（历史记录限制生效）
- ✅ 渲染性能流畅（无卡顿）
- ✅ 终端兼容性良好

### 7.4 单元测试验证

**运行命令**:
```bash
pytest tests/agents/test_enhanced_display.py -xvs
```

**测试覆盖率目标**: ≥ 80%

## 8. 技术风险与缓解措施

### 8.1 风险 1: 终端兼容性问题

**描述**: 不同终端模拟器对 Rich 组件的支持程度不同

**缓解措施**:
- 提供 `--simple` 模式作为降级方案
- 检测终端能力（`console.is_terminal`）
- 在不支持的终端自动切换到简单模式

### 8.2 风险 2: 性能问题

**描述**: 频繁渲染可能导致 CPU 占用过高

**缓解措施**:
- 使用 `Live.refresh()` 控制刷新频率（最多 10 FPS）
- 历史记录限制大小（默认 50 条）
- 使用 `deque` 优化内存占用

### 8.3 风险 3: 复杂度增加

**描述**: 新增组件可能增加维护成本

**缓解措施**:
- 保持现有 `AgentStatusDisplay` 作为默认
- 新功能通过 `--enhanced` 标志启用
- 充分的单元测试覆盖

## 9. 示例效果展示

### 9.1 执行前（当前效果）

```
⚙ 正在调用 smart_search...
✓ 找到 3 个结果
⚙ 正在调用 read_page_range...
✓ 读取完成
```

### 9.2 执行后（增强效果）

```
┌─────────────────────────────────────────────────────────┐
│                    执行历史                              │
│  ✓ 步骤 1: 分析查询意图                    (0.5s)       │
│    └─ 识别到：TABLE 类型查询                            │
│  ✓ 步骤 2: 调用 smart_search              (1.2s)       │
│    ├─ 参数: query="母线失压", limit=10                  │
│    └─ 结果: 找到 3 个结果 [P12, P45, P67]              │
├─────────────────────────────────────────────────────────┤
│                    当前操作                              │
│  🔄 正在调用 read_page_range(start=12, end=12)...      │
│     [████████████░░░░░░░░] 60% (0.8s)                   │
└─────────────────────────────────────────────────────────┘
```

## 10. 总结

本方案通过以下方式实现与 Claude Code 同等或更高水平的 CLI 界面：

**核心特性**:
1. ✅ 历史记录持久化显示（向上滚动）
2. ✅ 树状结构可视化（清晰层级）
3. ✅ 进度条和百分比显示（实时更新）
4. ✅ 流式响应显示（逐字输出）
5. ✅ 基础交互控制（Ctrl+C、折叠/展开）

**技术优势**:
- 基于现有事件系统，无需大规模重构
- 使用 Python + Rich 库（与项目技术栈一致）
- 渐进式实施，分 5 个阶段交付
- 默认启用，向后兼容（`--simple` 降级）
- 充分的测试和验证方案

**实施周期**: 5 周（~1300 行代码）
