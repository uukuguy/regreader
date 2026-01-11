# 多规程检索系统改造计划

## 背景

当前 GridCode 系统针对单一规程（安规2024）设计，现已入库两个规程：
- `angui_2024`：安全自动装置调度运行管理规定
- `wengui_2024`：特高压互联电网稳定及无功电压调度运行规定

需要改造检索系统以支持多规程智能检索。

## 核心需求

**默认行为**：根据用户问题自动判断应查询哪个或哪些规程，支持联合检索回答。

## 当前问题

| 层级 | 问题 |
|------|------|
| 工具层 | `smart_search(reg_id: str)` 必需参数，阻止跨规程 |
| 返回值 | 结果不包含 `reg_id` 字段，无法追溯来源 |
| Prompt | 硬编码"安规专家"，假设单一规程 |
| 工作流 | 无多规程发现和选择流程 |

## 实现计划

### Phase 1: MCP 工具层改造

#### 1.1 修改 `smart_search` 参数签名
**文件**: `src/grid_code/mcp/tools.py` (第 168-220 行)

```python
# 当前
def smart_search(self, query: str, reg_id: str, ...) -> list[dict]:

# 改为（合并参数）
def smart_search(
    self,
    query: str,
    reg_id: str | list[str] | None = None,  # 支持单值、列表或None
    ...
) -> list[dict]:
```

#### 1.2 实现多规程检索逻辑

三种模式（通过单一参数区分）：
1. **单规程**: `reg_id="angui_2024"` → 仅搜索指定规程
2. **多规程**: `reg_id=["angui_2024", "wengui_2024"]` → 搜索指定规程列表
3. **智能选择**: `reg_id=None` → **根据 query 关键词匹配规程元数据自动选择**
4. **全规程**: `reg_id="all"` → 明确搜索所有已入库规程

**智能选择实现逻辑**：
```python
def _smart_select_regulations(self, query: str) -> list[str]:
    """根据查询关键词智能选择规程"""
    regulations = self.page_store.list_regulations()
    matched = []

    for reg in regulations:
        # 匹配 keywords 字段
        for kw in reg.keywords:
            if kw in query:
                matched.append(reg.reg_id)
                break

    # 如果没有匹配到任何规程，返回所有（降级为全规程）
    return matched if matched else [r.reg_id for r in regulations]
```

#### 1.3 结果添加 `reg_id` 字段

```python
return [
    {
        "reg_id": r.reg_id,  # 新增：来源规程
        "page_num": r.page_num,
        ...
    }
    for r in results
]
```

#### 1.4 扩展 `RegulationInfo` 模型
**文件**: `src/grid_code/storage/models.py` (第 323-330 行)

新增字段用于辅助 Agent 选择规程：
```python
class RegulationInfo(BaseModel):
    """规程基本信息"""
    reg_id: str = Field(description="规程标识")
    title: str = Field(description="规程标题")
    source_file: str = Field(description="源文件名")
    total_pages: int = Field(description="总页数")
    indexed_at: str = Field(description="索引时间")

    # 新增字段
    description: str | None = Field(default=None, description="规程简介")
    keywords: list[str] = Field(default_factory=list, description="主题关键词，用于智能选择")
    scope: str | None = Field(default=None, description="适用范围描述")
```

#### 1.5 更新规程 info.json 格式

示例 `data/storage/pages/angui_2024/info.json`：
```json
{
  "reg_id": "angui_2024",
  "title": "2024年国调直调安全自动装置调度运行管理规定（第二版）",
  "source_file": "angui_2024.pdf",
  "total_pages": 150,
  "indexed_at": "2025-12-29T15:01:38.226993",
  "description": "规定安全自动装置的配置、功能、投停操作及参数管理",
  "keywords": ["安控装置", "稳控系统", "压板投退", "故障处理", "装置参数"],
  "scope": "适用于涉及装置配置、操作规程、故障响应等问题"
}
```

#### 1.6 新增 CLI 命令：自动生成规程元数据
**文件**: `src/grid_code/cli.py`

```bash
# 为单个规程生成元数据
gridcode enrich-metadata angui_2024

# 为所有规程生成元数据
gridcode enrich-metadata --all
```

实现逻辑：
```python
@app.command()
def enrich_metadata(
    reg_id: str = typer.Argument(None, help="规程ID，不指定则处理所有"),
    all_regs: bool = typer.Option(False, "--all", "-a", help="处理所有规程"),
):
    """
    自动生成规程元数据（description, keywords, scope）

    通过分析规程目录和首页内容，使用 LLM 生成描述信息。
    """
    tools = get_tools()

    # 确定要处理的规程
    if all_regs:
        regulations = tools.list_regulations()
        reg_ids = [r["reg_id"] for r in regulations]
    else:
        reg_ids = [reg_id]

    for rid in reg_ids:
        # 1. 获取 TOC
        toc = tools.get_toc(rid)

        # 2. 读取前几页内容（封面、目录、总则）
        first_pages = tools.read_page_range(rid, 1, 5)

        # 3. 调用 LLM 生成元数据
        metadata = generate_regulation_metadata(toc, first_pages)

        # 4. 更新 info.json
        update_info_json(rid, metadata)

        console.print(f"[green]✓ {rid} 元数据已更新[/green]")
```

LLM 提示词模板：
```python
METADATA_GENERATION_PROMPT = """
根据以下规程的目录结构和首页内容，生成规程元数据。

## 目录结构
{toc}

## 首页内容
{first_pages}

请生成以下 JSON 格式的元数据：
{{
  "description": "一句话描述规程的主要内容和用途（50字以内）",
  "keywords": ["关键词1", "关键词2", ...],  // 5-8个主题关键词，用于检索时匹配用户问题
  "scope": "适用范围描述（说明什么类型的问题应该查询此规程）"
}}
"""
```

---

### Phase 2: Prompt 系统改造

#### 2.1 泛化角色定义
**文件**: `src/grid_code/agents/prompts.py` (第 20-25 行)

```python
# 当前
ROLE_DEFINITION = """你是电力系统安规专家助理 GridCode..."""

# 改为（规程列表从元数据动态生成）
ROLE_DEFINITION = """# 角色定义
你是电力系统规程专家助理 GridCode，具备在多部规程文档中动态"翻书"的能力。

## 可用规程库
{regulation_list}

根据用户问题中的关键词，选择最相关的规程进行检索。
当问题可能涉及多个规程时，应主动进行跨规程检索。"""
```

#### 2.2 从元数据动态生成规程列表
**文件**: `src/grid_code/agents/prompts.py`

新增函数，从 `list_regulations()` 返回的元数据生成提示词片段：
```python
def format_regulation_list(regulations: list[dict]) -> str:
    """从规程元数据生成提示词中的规程列表"""
    lines = []
    for r in regulations:
        keywords = ", ".join(r.get("keywords", []))
        scope = r.get("scope", "")
        lines.append(
            f"- **{r['reg_id']}**: {r['title']}\n"
            f"  - 关键词: {keywords}\n"
            f"  - 适用范围: {scope}"
        )
    return "\n".join(lines)
```

#### 2.3 新增多规程工作流
**文件**: `src/grid_code/agents/prompts.py`

在 `OPERATION_PROTOCOLS` 开头新增：

```python
## 0. 规程选择原则
根据用户问题和规程元数据中的关键词/适用范围，智能选择检索范围：
- 问题关键词匹配单个规程 → 单规程检索
- 问题关键词匹配多个规程 → 跨规程检索
- 不确定时 → 使用全规程模式，从结果中筛选
```

---

### Phase 3: Agent 层改造

#### 3.1 初始化时预加载规程列表
**文件**: `src/grid_code/agents/claude_agent.py` (及其他 Agent)

```python
async def _get_system_prompt(self) -> str:
    # 获取规程列表注入提示词
    if self._regulations is None:
        self._regulations = await self._call_tool("list_regulations", {})
    return get_prompt_with_regulations(self._regulations)
```

---

### Phase 4: CLI 改造

#### 4.1 搜索命令支持多规程参数
**文件**: `src/grid_code/cli.py` (第 271-288 行)

```python
@app.command()
def search(
    query: str,
    reg_id: list[str] = Option(None, "-r", help="规程ID，可多次指定"),
    all_regs: bool = Option(False, "--all", "-a", help="搜索所有规程"),
):
    # 示例用法：
    # gridcode search "母线失压"                          # 智能选择规程
    # gridcode search "天中直流安控" -r angui_2024         # 单规程
    # gridcode search "稳定控制" -r angui_2024 -r wengui_2024  # 多规程
    # gridcode search "故障处理" --all                    # 全规程
```

**默认行为**：
- 不指定 `-r` 且不指定 `--all` → 智能选择（根据 query 匹配规程关键词）
- 指定 `-r` → 搜索指定规程
- 指定 `--all` → 搜索所有规程

#### 4.2 结果按规程分组显示

---

### Phase 5: 工具元数据更新

**文件**: `src/grid_code/mcp/tool_metadata.py`

更新 `smart_search` 描述和参数定义，新增工作流：
```python
"跨规程查询": ["list_regulations", "smart_search", "read_page_range"]
```

---

## 关键文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/grid_code/storage/models.py` | RegulationInfo 新增 description/keywords/scope 字段 |
| `src/grid_code/storage/page_store.py` | 新增 update_info() 方法更新元数据 |
| `src/grid_code/mcp/tools.py` | smart_search 参数+逻辑 |
| `src/grid_code/mcp/tool_metadata.py` | 工具描述、参数定义、工作流 |
| `src/grid_code/agents/prompts.py` | 角色定义、format_regulation_list 函数、操作协议 |
| `src/grid_code/agents/claude_agent.py` | 预加载规程列表、动态生成提示词 |
| `src/grid_code/agents/pydantic_agent.py` | 同上 |
| `src/grid_code/agents/langgraph_agent.py` | 同上 |
| `src/grid_code/cli.py` | 多规程参数、结果分组显示、enrich-metadata 命令 |
| `src/grid_code/services/metadata_service.py` | 新增：LLM 生成元数据服务 |

## 实现顺序

1. **Phase 1.1**: 模型层（RegulationInfo 新增字段）
2. **Phase 1.2**: 存储层（update_info 方法）
3. **Phase 1.3**: 服务层（metadata_service.py）
4. **Phase 1.4**: CLI（enrich-metadata 命令）
5. **Phase 1.5**: 工具层（smart_search 参数+逻辑）
6. **Phase 2**: Prompt（角色定义、format_regulation_list）
7. **Phase 3**: Agent 层（动态提示词）
8. **Phase 4**: CLI（多规程检索参数）
9. **Phase 5**: 元数据（工具描述）

## 向后兼容

- 单规程查询 `smart_search(query, reg_id="xxx")` 仍正常工作
- CLI `-r` 参数保持不变
- 现有测试用例无需修改

## 验收标准

1. `gridcode search "母线失压"` → 智能选择匹配的规程（angui_2024 包含"故障处理"关键词）
2. `gridcode search "特高压稳定限额"` → 智能选择 wengui_2024
3. `gridcode search "天中直流安控" -r angui_2024` → 仅搜索安规
4. `gridcode search "稳定控制" -r angui_2024 -r wengui_2024` → 搜索指定多规程
5. `gridcode search "xxx" --all` → 搜索所有规程
6. `gridcode chat` → Agent 能根据问题智能选择规程
7. 跨规程问题（如"天中直流的稳定限额和安控措施"）能匹配两个规程并整合回答
8. `gridcode enrich-metadata --all` → 自动生成所有规程的元数据
