# Agent 记忆系统设计与实现

## 概述

本文档描述 GridCode Agent 记忆系统的设计与实现，用于优化多轮工具调用效率。

### 解决的问题

1. `get_toc()` 查询后，后续还会重复查询目录
2. 搜索页面内容后，没有记忆相关内容，无法在迭代推理中复用
3. 每次工具调用都是独立的，缺乏上下文积累

### 设计决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 目录缓存方案 | 提示词引导 | 简单实现，不改事件流 |
| 记忆持久化 | 仅当前会话 | 简单实现，会话结束清空 |
| 相关性评分 | 使用搜索返回的 score | 无额外计算开销 |

---

## 架构设计

### 核心组件

```
src/grid_code/agents/
├── memory.py          # 记忆系统核心模块
├── pydantic_agent.py  # PydanticAI Agent（已集成）
└── claude_agent.py    # Claude Agent SDK（已集成）
```

### 数据流

```
用户查询 → Agent 运行 → 工具调用
                          ↓
                    _update_memory()
                          ↓
         ┌────────────────┼────────────────┐
         ↓                ↓                ↓
    get_toc         smart_search     read_page_range
         ↓                ↓                ↓
   缓存到 toc_cache   添加高分结果      添加页面摘要
         ↓                ↓                ↓
         └────────────────┴────────────────┘
                          ↓
                  _build_system_prompt()
                          ↓
              注入 "已缓存目录" 提示
              注入 "已获取的相关信息"
```

---

## 核心数据结构

### ContentChunk

内容片段，用于存储搜索结果和页面内容摘要。

```python
@dataclass
class ContentChunk:
    """内容片段"""
    content: str           # 内容文本
    source: str            # 来源（如 angui_2024 P85）
    relevance_score: float # 相关性评分 (0-1)
    chunk_type: str        # 类型: search_result, page_content, table
    metadata: dict         # 额外元数据
```

### AgentMemory

Agent 记忆状态，会话级记忆。

```python
@dataclass
class AgentMemory:
    """Agent 记忆状态"""
    toc_cache: dict[str, dict]        # 目录缓存 (reg_id -> TocTree)
    known_chapters: list[str]          # 已知章节范围
    relevant_chunks: list[ContentChunk] # 相关内容（按相关性排序）
    current_query: str                  # 当前查询上下文
    max_chunks: int = 10               # 最大记忆容量
    min_relevance: float = 0.5         # 最小相关性阈值
```

---

## 主要方法

### 目录缓存

```python
def cache_toc(self, reg_id: str, toc: dict) -> None:
    """缓存目录"""

def get_cached_toc(self, reg_id: str) -> dict | None:
    """获取缓存的目录"""

def has_cached_toc(self, reg_id: str) -> bool:
    """检查目录是否已缓存"""
```

### 内容记忆

```python
def add_chunk(self, chunk: ContentChunk) -> None:
    """添加内容片段，保持按相关性排序，超过容量时移除低分内容"""

def add_search_results(self, results: list[dict]) -> None:
    """从搜索结果中提取并添加高相关性内容"""

def add_page_content(self, content: str, source: str, relevance: float = 0.8) -> None:
    """添加页面内容摘要"""
```

### 上下文生成

```python
def get_memory_context(self) -> str:
    """生成记忆上下文，用于注入系统提示词"""
    # 返回格式：
    # # 已获取的相关信息
    # ## [1] angui_2024 P85
    # 内容摘要...

def get_toc_cache_hint(self) -> str:
    """生成目录缓存提示"""
    # 返回格式：
    # # 已缓存目录
    # 以下规程目录已获取: angui_2024
    # 无需再次调用 get_toc()
```

### 重置方法

```python
def clear_query_context(self) -> None:
    """清除当前查询上下文（保留目录缓存）"""

def reset(self) -> None:
    """完全重置记忆"""
```

---

## Agent 集成

### PydanticAI Agent

关键修改点：

1. **动态系统提示词**：使用 lambda 函数确保每次运行时重建提示词
   ```python
   system_prompt=lambda ctx: self._build_system_prompt()
   ```

2. **工具结果处理**：在事件处理流程中调用 `_update_memory()`
   ```python
   async for event in agent_run.stream_text(delta=True):
       # ... 处理事件 ...
       if tool_name and result_content:
           self._update_memory(tool_name, result_content)
   ```

3. **重置方法**：
   - `reset()`: 清除查询上下文，保留目录缓存
   - 完全重置时调用 `self._memory.reset()`

### Claude Agent SDK

关键修改点：

1. **系统提示词构建**：在 `_build_system_prompt()` 中注入记忆上下文
   ```python
   # 注入目录缓存提示
   toc_hint = self._memory.get_toc_cache_hint()
   if toc_hint:
       base_prompt += toc_hint

   # 注入已获取的相关内容
   memory_context = self._memory.get_memory_context()
   if memory_context:
       base_prompt += f"\n\n{memory_context}"
   ```

2. **事件处理**：在 `_process_event()` 中更新记忆
   ```python
   if hasattr(event, "type") and getattr(event, "type", None) == "tool_result":
       if tool_name:
           self._update_memory(tool_name, content)
   ```

3. **重置方法**：
   - `reset()`: 调用 `self._memory.clear_query_context()`
   - `reset_all()`: 调用 `self._memory.reset()`

---

## 预期效果

| 场景 | 优化前 | 优化后 |
|------|--------|--------|
| 目录查询 | 每次查询都调用 get_toc | 首次调用后缓存，后续跳过 |
| 搜索结果 | 结果丢失，无法复用 | 高分结果记忆，后续可引用 |
| 页面阅读 | 内容仅在当次可见 | 摘要记忆，迭代推理可用 |
| 工具调用次数 | 重复调用 | 减少冗余调用 |

---

## 验证方法

### 目录缓存验证

1. 首次查询观察 get_toc 调用
2. 第二次查询观察是否跳过 get_toc
3. 检查日志：`[Memory] 缓存目录: xxx`

### 内容记忆验证

1. 查看系统提示词是否包含 "已获取的相关信息"
2. 观察 LLM 是否在后续回答中引用已记忆内容
3. 检查日志：`[Memory] 添加搜索结果: X 条`

### 日志检查

```python
logger.debug(f"[Memory] 缓存目录: {reg_id}")
logger.debug(f"[Memory] 添加搜索结果: {len(results)} 条")
logger.debug(f"[Memory] 添加页面内容: {source}")
```

---

## 配置项（可选扩展）

如需添加配置项，可在 `config.py` 中添加：

```python
# 记忆系统配置
memory_enabled: bool = Field(
    default=True,
    description="是否启用 Agent 记忆系统",
)
memory_max_chunks: int = Field(
    default=10,
    description="最大记忆内容片段数",
)
memory_min_relevance: float = Field(
    default=0.5,
    description="最小相关性阈值（低于此值的内容不记忆）",
)
```

---

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `src/grid_code/agents/memory.py` | 新增 | AgentMemory 核心模块 |
| `src/grid_code/agents/pydantic_agent.py` | 修改 | 集成记忆系统 |
| `src/grid_code/agents/claude_agent.py` | 修改 | 集成记忆系统 |
