# RegReader MCP 工具集精简分析与智能体工作流设计

> 创建日期: 2026-01-03
> 分支: dev
> 状态: 已确认实施

## 一、当前工具集现状分析

### 1.1 现有工具清单（16个）

| 分类 | 工具名 | 优先级 | 当前用途 |
|------|--------|--------|----------|
| BASE | `get_toc` | ⭐⭐⭐ | 获取规程目录树 |
| BASE | `smart_search` | ⭐⭐⭐ | 混合检索（关键词+语义） |
| BASE | `read_page_range` | ⭐⭐ | 读取连续页面 |
| BASE | `list_regulations` | ⭐⭐⭐ | 列出已入库规程 |
| BASE | `get_chapter_structure` | ⭐⭐ | 获取章节结构树 |
| BASE | `get_page_chapter_info` | ⭐ | 获取页面章节信息 |
| BASE | `read_chapter_content` | ⭐⭐ | 读取完整章节内容 |
| MULTI-HOP | `lookup_annotation` | ⭐⭐ | 追踪注释（注1、方案A） |
| MULTI-HOP | `search_tables` | ⭐⭐ | 搜索表格 |
| MULTI-HOP | `resolve_reference` | ⭐⭐ | 解析交叉引用 |
| CONTEXT | `search_annotations` | ⭐ | 搜索所有注释 |
| CONTEXT | `get_table_by_id` | ⭐⭐ | 获取完整表格 |
| CONTEXT | `get_block_with_context` | ⭐⭐ | 获取上下文 |
| DISCOVERY | `find_similar_content` | ⭐ | 查找相似内容 |
| DISCOVERY | `compare_sections` | ⭐ | 比较章节 |
| NAVIGATION | `get_tool_guide` | ⭐⭐⭐ | 获取工具使用指南 |

### 1.2 问题诊断

**问题1：工具数量过多，增加智能体决策负担**
- 16个工具，每次LLM推理都需考虑所有工具选择
- 部分工具功能重叠（如 `get_chapter_structure` vs `get_toc`）
- 低频工具占用提示词空间

**问题2：工具边界模糊**
- `search_annotations` vs `lookup_annotation` 区分不清
- `get_page_chapter_info` 使用场景有限
- `find_similar_content` 和 `compare_sections` 属于高级分析，非检索核心

**问题3：工具粒度不一致**
- 有些太细（`get_page_chapter_info`）
- 有些太粗（`smart_search` 参数过多）

---

## 二、最终工具集方案

### 2.1 核心工具集（8个，始终启用）

```python
CORE_TOOLS = [
    # 基础工具（4个）
    "list_regulations",    # 入口：列出可用规程
    "get_toc",             # 导航：获取目录结构
    "smart_search",        # 检索：混合搜索
    "read_page_range",     # 阅读：获取页面内容

    # 多跳工具（3个）
    "search_tables",       # 表格：搜索表格
    "lookup_annotation",   # 多跳：追踪注释
    "resolve_reference",   # 多跳：解析引用

    # 扩展工具（1个）
    "get_table_by_id",     # 表格：获取完整跨页表格
]
```

### 2.2 可选扩展工具（默认禁用，配置开关启用）

```python
OPTIONAL_TOOLS = [
    "find_similar_content",   # 高级：查找相似内容
    "compare_sections",       # 高级：比较章节
]
```

### 2.3 移除的工具（6个）

| 工具 | 移除理由 | 替代方案 |
|------|----------|----------|
| `get_tool_guide` | 内容嵌入系统提示词 | 系统提示词 |
| `get_chapter_structure` | 与 `get_toc` 重叠 | `get_toc` |
| `get_page_chapter_info` | 使用频率极低 | `read_page_range` |
| `read_chapter_content` | 可组合实现 | `smart_search` + `read_page_range` |
| `search_annotations` | 与 `lookup_annotation` 重叠 | `lookup_annotation` |
| `get_block_with_context` | 可组合实现 | `read_page_range` |

---

## 三、智能体工作流设计

### 3.1 标准检索工作流（Standard Retrieval Flow）

```
┌─────────────────────────────────────────────────────────┐
│                    用户提问                              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 1: 识别规程范围                                      │
│ - 如果不确定规程：list_regulations()                      │
│ - 如果已知规程：直接使用 reg_id                           │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 2: 获取目录结构                                      │
│ - get_toc(reg_id)                                        │
│ - 分析目录，确定可能的章节范围                            │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 3: 精准搜索                                          │
│ - smart_search(query, reg_id, scope=章节范围)            │
│ - 获取初步搜索结果                                        │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 4: 阅读完整内容                                      │
│ - read_page_range(reg_id, start, end)                   │
│ - 获取搜索结果所在页面的完整内容                          │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│ Step 5: 生成答案                                          │
│ - 整合信息，生成结构化答案                                │
│ - 包含来源引用（规程名 + 页码）                           │
└─────────────────────────────────────────────────────────┘
```

### 3.2 多跳推理工作流（Multi-hop Reasoning Flow）

```
用户提问（涉及表格/注释/引用）
         │
         ▼
    [标准流程 Step 1-4]
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 5: 检测多跳需求                                     │
│                                                         │
│ 触发条件检测：                                           │
│ ├── "见注X"、"注①"、"方案A" → lookup_annotation()       │
│ ├── "见第X章"、"参见表Y" → resolve_reference()          │
│ └── 表格相关查询 → search_tables()                       │
└────────────────────────────────────────────────────────┘
         │
         ├─── 注释追踪 ─────────────────┐
         │                              ▼
         │    lookup_annotation(reg_id, "注1", page_hint)
         │                              │
         │                              ▼
         │                     获取注释完整内容
         │
         ├─── 引用解析 ─────────────────┐
         │                              ▼
         │    resolve_reference(reg_id, "见第六章")
         │                              │
         │                              ▼
         │                     获取目标章节位置
         │                              │
         │                              ▼
         │                     read_page_range(解析后位置)
         │
         └─── 表格查询 ─────────────────┐
                                       ▼
              search_tables(query, reg_id, scope)
                                       │
                                       ▼
                              是否需要完整表格？
                              ├── 否 → 使用摘要
                              └── 是 → get_table_by_id()
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 6: 整合多源信息                                     │
│ - 合并主内容 + 注释 + 引用目标 + 表格                    │
│ - 生成完整答案                                           │
└────────────────────────────────────────────────────────┘
```

### 3.3 表格密集型查询工作流

```
用户提问（表格相关）
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 1: 表格定位                                         │
│ - search_tables(query, reg_id)                          │
│ - 获取匹配的表格列表                                     │
└────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 2: 检查表格完整性                                   │
│ - 如果 is_cross_page=true 或 is_truncated=true          │
│ - 调用 get_table_by_id() 获取完整内容                   │
└────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 3: 追踪表格注释                                     │
│ - 检查表格内容中的 "见注X"                              │
│ - 调用 lookup_annotation() 获取注释                     │
└────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Step 4: 整合答案                                         │
│ - 表格数据 + 注释补充 + 上下文                           │
│ - 生成结构化答案                                         │
└────────────────────────────────────────────────────────┘
```

---

## 四、智能体指导策略

### 4.1 系统提示词设计（精简版）

```markdown
# 角色定义
你是电力系统安规专家助理 RegReader，具备在安规文档中动态"翻书"的能力。

# 可用工具（8个）
1. list_regulations() - 列出已入库规程
2. get_toc(reg_id) - 获取规程目录结构
3. smart_search(query, reg_id, scope, limit) - 混合检索
4. read_page_range(reg_id, start, end) - 读取页面内容
5. search_tables(query, reg_id, scope) - 搜索表格
6. lookup_annotation(reg_id, annotation_id, page_hint) - 追踪注释
7. resolve_reference(reg_id, reference_text) - 解析交叉引用
8. get_table_by_id(reg_id, table_id) - 获取完整跨页表格

# 核心工作流
1. 目录优先：先 get_toc() 确定范围，禁止盲目全文搜索
2. 精准定位：smart_search 时务必指定 scope 参数
3. 完整阅读：搜索结果不完整时用 read_page_range 补充
4. 多跳追踪：见"注X"用 lookup_annotation，见"第X章"用 resolve_reference

# 输出格式
所有回答必须包含：
- 【处置措施】具体步骤
- 【注意事项】重要提醒
- 【来源】规程名 + 页码（如：安规2024 P85）
```

### 4.2 工具选择决策树

```
用户提问
    │
    ├─ "有哪些规程？" / 不确定规程
    │  └─→ list_regulations()
    │
    ├─ 已知规程 + 需要了解结构
    │  └─→ get_toc(reg_id)
    │
    ├─ 具体问题查询
    │  ├─→ 先 get_toc() 确定章节范围
    │  ├─→ smart_search(query, scope=章节)
    │  └─→ read_page_range() 获取完整内容
    │
    ├─ 表格相关查询
    │  ├─→ search_tables(query)
    │  └─→ 如需完整表格: get_table_by_id()
    │
    ├─ 发现"见注X"
    │  └─→ lookup_annotation(annotation_id, page_hint)
    │
    └─ 发现"见第X章"/"参见表Y"
       └─→ resolve_reference(reference_text)
```

### 4.3 工具组合模式

**模式1：简单查询**
```
get_toc → smart_search → read_page_range → 生成答案
```

**模式2：表格查询**
```
get_toc → search_tables → [get_table_by_id] → [lookup_annotation] → 生成答案
```

**模式3：引用追踪**
```
get_toc → smart_search → resolve_reference → read_page_range(目标) → 生成答案
```

**模式4：深度探索**
```
get_toc → smart_search → read_page_range → lookup_annotation → resolve_reference → read_page_range(目标) → 生成答案
```

---

## 五、预期效果

### 5.1 工具数量对比

| 状态 | 工具数 | 提示词开销 |
|------|--------|-----------|
| 当前 | 16个 | ~3000 tokens |
| 精简后 | 8个核心 + 2个可选 | ~1500 tokens |
| 节省 | 6个 | ~1500 tokens (50%) |

### 5.2 智能体决策复杂度

| 状态 | 工具选择复杂度 | 决策时间 |
|------|---------------|----------|
| 当前 | O(16) | 较慢 |
| 精简后 | O(8) | 更快 |

### 5.3 检索质量

- **核心检索能力保持**：smart_search + read_page_range 覆盖80%场景
- **多跳推理能力保持**：annotation + reference + tables 覆盖复杂场景
- **移除的工具功能可通过组合实现**：不影响最终检索效果

---

## 六、配置开关设计

```python
# config.py 新增配置
class MCPToolConfig:
    """MCP工具集配置"""

    # 核心工具（始终启用）
    CORE_TOOLS: list[str] = [
        "list_regulations",
        "get_toc",
        "smart_search",
        "read_page_range",
        "search_tables",
        "lookup_annotation",
        "resolve_reference",
        "get_table_by_id",
    ]

    # 高级分析工具（默认禁用）
    ADVANCED_TOOLS: list[str] = [
        "find_similar_content",
        "compare_sections",
    ]

    # 是否启用高级工具
    ENABLE_ADVANCED_TOOLS: bool = False
```

---

## 七、实施清单

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/regreader/config.py` | 添加工具集配置开关 |
| `src/regreader/mcp/tool_metadata.py` | 更新工具元数据，移除被删除的工具 |
| `src/regreader/mcp/server.py` | 根据配置动态注册工具 |
| `src/regreader/agents/prompts.py` | 更新系统提示词，嵌入工具使用指南 |
