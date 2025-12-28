# GridCode 章节信息和块类型优化方案

## 问题总结

当前系统存在以下设计问题：

1. **章节号+内容混合块**：如 "2.1.1.1.1 复奉-宾金安全稳定控制系统为..." 既是章节标识又包含段落内容
2. **章节信息粒度不足**：`chapter_path` 只在 Page 级，无法精确知道某个块属于哪个章节
3. **索引缺失元数据**：`block_type` 未被索引，无法按类型过滤搜索
4. **缺少章节结构树**：无法快速获取完整的文档章节导航结构

## 设计方案：混合架构

基于用户需求，采用**分层章节结构 + 块级章节信息**的混合方案：

### 核心设计思想

```
┌─────────────────────────────────────────────────┐
│ DocumentStructure (文档结构层)                    │
│  - 全局章节树 (ChapterNode)                       │
│  - 支持快速导航和章节查询                          │
└─────────────────────────────────────────────────┘
              ↓ 引用关系
┌─────────────────────────────────────────────────┐
│ PageDocument (页面层)                            │
│  - content_blocks (内容块)                       │
│  - chapter_nodes (本页定义的章节节点)              │
└─────────────────────────────────────────────────┘
              ↓ 包含关系
┌─────────────────────────────────────────────────┐
│ ContentBlock (内容块层)                          │
│  - block_type (text/table/list/section_content) │
│  - chapter_path (块级章节路径)                    │
│  - chapter_node_id (所属章节节点ID)               │
└─────────────────────────────────────────────────┘
```

---

## 实施步骤

### 第一阶段：数据模型扩展

#### 1.1 新增 ChapterNode 模型

**文件**: `src/grid_code/storage/models.py`

```python
class ChapterNode(BaseModel):
    """章节节点（文档结构树）"""
    node_id: str = Field(description="节点唯一标识")
    section_number: str = Field(description="章节编号，如 '2.1.4.1.6'")
    title: str = Field(description="章节标题（纯文本，不含编号）")
    level: int = Field(description="章节层级 1-6")
    page_num: int = Field(description="章节首次出现的页码")

    # 层级关系
    parent_id: str | None = Field(default=None, description="父节点ID")
    children_ids: list[str] = Field(default_factory=list, description="子节点ID列表")

    # 内容关联
    content_block_ids: list[str] = Field(
        default_factory=list,
        description="属于此章节的内容块ID列表（跨页）"
    )

    # 元数据
    has_direct_content: bool = Field(
        default=False,
        description="章节号后是否有直接内容（如长段落）"
    )
    direct_content: str | None = Field(
        default=None,
        description="章节号后的直接内容（如有）"
    )
```

#### 1.2 扩展 ContentBlock 模型

**文件**: `src/grid_code/storage/models.py`

```python
class ContentBlock(BaseModel):
    block_id: str
    block_type: Literal["text", "table", "list", "section_content"]  # 新增 section_content
    order_in_page: int
    content_markdown: str

    # 新增：块级章节信息
    chapter_path: list[str] = Field(
        default_factory=list,
        description="块级章节路径（完整路径）"
    )
    chapter_node_id: str | None = Field(
        default=None,
        description="所属章节节点ID"
    )

    # 原有字段
    table_meta: TableMeta | None = None
    heading_level: int | None = None  # 保留用于 Markdown 渲染


# 块类型说明：
# - "text": 普通段落文本
# - "table": 表格
# - "list": 列表
# - "section_content": 章节号后直接跟随的内容
#   （如 "2.1.1.1.1 复奉-宾金...这些内容"，编号存在 ChapterNode，内容存在此块）
```

#### 1.3 新增 DocumentStructure 模型

**文件**: `src/grid_code/storage/models.py`

```python
class DocumentStructure(BaseModel):
    """文档章节结构（全局）"""
    reg_id: str
    all_nodes: dict[str, ChapterNode] = Field(
        default_factory=dict,
        description="所有章节节点映射 {node_id: ChapterNode}"
    )
    root_node_ids: list[str] = Field(
        default_factory=list,
        description="顶级章节节点ID列表"
    )

    def get_chapter_path(self, node_id: str) -> list[str]:
        """获取章节完整路径"""
        path = []
        node = self.all_nodes.get(node_id)
        while node:
            path.insert(0, f"{node.section_number} {node.title}")
            node = self.all_nodes.get(node.parent_id) if node.parent_id else None
        return path

    def get_chapter_tree(self) -> list[TocItem]:
        """转换为目录树格式"""
        # 用于 MCP get_toc() 工具
        ...
```

#### 1.4 修改 PageDocument 模型

**文件**: `src/grid_code/storage/models.py`

```python
class PageDocument(BaseModel):
    reg_id: str
    page_num: int

    # 保留页面级章节路径（用于快速访问）
    chapter_path: list[str] = Field(
        default_factory=list,
        description="页面主要章节路径"
    )

    content_blocks: list[ContentBlock] = Field(default_factory=list)

    # 新增：本页定义的章节节点
    chapter_nodes: list[ChapterNode] = Field(
        default_factory=list,
        description="本页首次出现的章节节点"
    )

    # 原有字段保持不变
    content_markdown: str
    continues_from_prev: bool = False
    continues_to_next: bool = False
    annotations: list[Annotation] = Field(default_factory=list)
```

---

### 第二阶段：解析逻辑重构

#### 2.1 两阶段解析策略

**第一阶段：提取文档结构**

**文件**: `src/grid_code/parser/page_extractor.py`

新增方法：
```python
def extract_document_structure(self, result: ConversionResult) -> DocumentStructure:
    """
    第一遍扫描：提取全局章节结构

    流程：
    1. 遍历所有文本项
    2. 识别章节标题（Docling标签 + 智能检测）
    3. 解析章节编号和标题
    4. 构建层级关系（父子节点）
    5. 返回 DocumentStructure
    """
    all_nodes = {}
    node_stack = []  # (level, node_id)

    for item in doc.texts:
        # 识别章节标题
        is_section, section_info = self._parse_section_info(item.text)
        if not is_section:
            continue

        # 创建 ChapterNode
        node_id = self._generate_id("chapter")
        node = ChapterNode(
            node_id=node_id,
            section_number=section_info["number"],
            title=section_info["title"],
            level=section_info["level"],
            page_num=self._get_page_num(item),
            has_direct_content=len(section_info["direct_content"]) > 50,
            direct_content=section_info["direct_content"] if section_info["direct_content"] else None,
        )

        # 维护层级关系
        while node_stack and node_stack[-1][0] >= node.level:
            node_stack.pop()

        if node_stack:
            parent_id = node_stack[-1][1]
            node.parent_id = parent_id
            all_nodes[parent_id].children_ids.append(node_id)

        all_nodes[node_id] = node
        node_stack.append((node.level, node_id))

    return DocumentStructure(reg_id=self.reg_id, all_nodes=all_nodes, ...)
```

**第二阶段：提取页面内容并关联章节**

修改 `extract_pages()` 方法：

```python
def extract_pages(
    self,
    result: ConversionResult,
    doc_structure: DocumentStructure
) -> list[PageDocument]:
    """
    第二遍扫描：提取页面内容并关联章节结构

    流程：
    1. 按页分组内容
    2. 匹配章节节点
    3. 为每个块分配章节归属
    4. 处理章节号+内容混合块
    """
    for page_num in sorted_page_nums:
        blocks = page_contents[page_num]

        current_chapter_node = None
        page_chapter_nodes = []
        content_blocks = []

        for block_data in blocks:
            # 检查是否为章节标题
            if block_data.get("type") == "heading":
                # 查找对应的 ChapterNode
                node = self._find_chapter_node_by_text(
                    doc_structure,
                    block_data["text"],
                    page_num
                )

                if node:
                    current_chapter_node = node
                    page_chapter_nodes.append(node)

                    # 如果章节号后有直接内容，创建 section_content 块
                    if node.has_direct_content and node.direct_content:
                        block = ContentBlock(
                            block_id=self._generate_id("section"),
                            block_type="section_content",
                            order_in_page=len(content_blocks),
                            content_markdown=node.direct_content,
                            chapter_path=doc_structure.get_chapter_path(node.parent_id or node.node_id),
                            chapter_node_id=node.node_id,
                        )
                        content_blocks.append(block)
                        node.content_block_ids.append(block.block_id)
                    # 否则不创建内容块（纯章节标题已在 ChapterNode 中）
                    continue

            # 创建普通内容块
            block = self._create_content_block(block_data, len(content_blocks))

            # 关联章节
            if current_chapter_node:
                block.chapter_path = doc_structure.get_chapter_path(current_chapter_node.node_id)
                block.chapter_node_id = current_chapter_node.node_id
                current_chapter_node.content_block_ids.append(block.block_id)

            content_blocks.append(block)

        # 创建 PageDocument
        page = PageDocument(
            reg_id=self.reg_id,
            page_num=page_num,
            chapter_path=page_chapter_nodes[0].get_full_path() if page_chapter_nodes else [],
            content_blocks=content_blocks,
            chapter_nodes=page_chapter_nodes,
            ...
        )
        pages.append(page)
```

#### 2.2 新增章节解析辅助方法

```python
def _parse_section_info(self, text: str) -> tuple[bool, dict | None]:
    """
    解析章节信息

    Returns:
        (is_section, section_info)
        section_info = {
            "number": "2.1.4.1.6",
            "title": "龙泉站中州安控装置",
            "level": 4,
            "direct_content": "与其他站安控装置间通过..."  # 章节号后的直接内容
        }
    """
    # 章节编号模式
    patterns = [
        (r'^(\d+(?:\.\d+)*)\.?\s+(.+)$', 'numeric'),          # "2.1.4 标题..."
        (r'^(第[一二三四五六七八九十\d]+章)\s*(.*)$', 'chapter'),  # "第一章 ..."
        (r'^(第[一二三四五六七八九十\d]+节)\s*(.*)$', 'section'),  # "第一节 ..."
    ]

    for pattern, pattern_type in patterns:
        match = re.match(pattern, text.strip())
        if match:
            section_num = match.group(1)
            remaining = match.group(2).strip()

            # 计算层级
            if pattern_type == 'numeric':
                level = section_num.count('.') + 1
            elif pattern_type == 'chapter':
                level = 1
            elif pattern_type == 'section':
                level = 2

            # 分离标题和直接内容
            # 如果 remaining 很长（>50字符），认为包含直接内容
            if len(remaining) > 50:
                # 尝试找到第一个句号或换行作为标题结束
                title_end = min(
                    remaining.find('。') if '。' in remaining else len(remaining),
                    remaining.find('\n') if '\n' in remaining else len(remaining),
                    50  # 标题最多50字符
                )
                title = remaining[:title_end]
                direct_content = remaining[title_end:].strip()
            else:
                title = remaining
                direct_content = ""

            return True, {
                "number": section_num,
                "title": title,
                "level": level,
                "direct_content": direct_content,
            }

    return False, None


def _find_chapter_node_by_text(
    self,
    doc_structure: DocumentStructure,
    text: str,
    page_num: int
) -> ChapterNode | None:
    """根据文本和页码查找对应的章节节点"""
    is_section, section_info = self._parse_section_info(text)
    if not is_section:
        return None

    # 在 DocumentStructure 中查找匹配的节点
    for node in doc_structure.all_nodes.values():
        if (node.section_number == section_info["number"] and
            node.page_num == page_num):
            return node

    return None
```

---

### 第三阶段：存储层扩展

#### 3.1 保存文档结构

**文件**: `src/grid_code/storage/page_store.py`

```python
class PageStore:
    def save_document_structure(self, structure: DocumentStructure):
        """保存文档结构到独立文件"""
        structure_dir = self.pages_dir.parent / "structures"
        structure_dir.mkdir(parents=True, exist_ok=True)

        structure_path = structure_dir / f"{structure.reg_id}_structure.json"
        structure_path.write_text(
            structure.model_dump_json(indent=2),
            encoding="utf-8"
        )
        logger.info(f"文档结构已保存: {structure_path}")

    def load_document_structure(self, reg_id: str) -> DocumentStructure:
        """加载文档结构"""
        structure_path = self.pages_dir.parent / "structures" / f"{reg_id}_structure.json"
        if not structure_path.exists():
            raise StorageError(f"文档结构不存在: {reg_id}")

        return DocumentStructure.model_validate_json(
            structure_path.read_text(encoding="utf-8")
        )
```

#### 3.2 修改保存流程

**文件**: `src/grid_code/storage/page_store.py`

```python
def save_pages(
    self,
    pages: list[PageDocument],
    toc: TocTree | None = None,
    doc_structure: DocumentStructure | None = None,  # 新增
    source_file: str = "",
) -> RegulationInfo:
    """保存页面列表和文档结构"""
    # ... 现有逻辑

    # 保存文档结构
    if doc_structure:
        self.save_document_structure(doc_structure)

    # ... 现有逻辑
```

---

### 第四阶段：索引层增强

#### 4.1 FTS5 索引扩展

**文件**: `src/grid_code/index/keyword/fts5.py`

```python
def _init_db(self):
    """初始化数据库，添加新字段"""
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS page_index USING fts5(
            content,                    -- 内容文本
            reg_id UNINDEXED,
            page_num UNINDEXED,
            block_id UNINDEXED,

            -- 新增字段
            block_type UNINDEXED,       -- 块类型（支持过滤）
            chapter_node_id UNINDEXED,  -- 章节节点ID
            chapter_path UNINDEXED,     -- 块级章节路径（JSON）
            section_number UNINDEXED,   -- 章节编号（用于精确匹配）

            tokenize='porter unicode61'
        )
    """)


def index_page(
    self,
    page: PageDocument,
    doc_structure: DocumentStructure | None = None  # 新增参数
) -> None:
    """索引页面，包含块级章节信息"""
    for block in page.content_blocks:
        # 获取章节编号
        section_number = None
        if block.chapter_node_id and doc_structure:
            node = doc_structure.all_nodes.get(block.chapter_node_id)
            if node:
                section_number = node.section_number

        cursor.execute("""
            INSERT INTO page_index
            (content, reg_id, page_num, block_id, block_type,
             chapter_node_id, chapter_path, section_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            block.content_markdown.strip(),
            page.reg_id,
            page.page_num,
            block.block_id,
            block.block_type,
            block.chapter_node_id,
            json.dumps(block.chapter_path, ensure_ascii=False),
            section_number,
        ))


def search(
    self,
    query: str,
    reg_id: str | None = None,
    chapter_scope: str | None = None,
    limit: int = 10,
    block_types: list[str] | None = None,      # 新增：块类型过滤
    section_number: str | None = None,         # 新增：章节号精确匹配
) -> list[SearchResult]:
    """增强搜索功能"""
    sql = """
        SELECT content, reg_id, page_num, block_id, block_type,
               chapter_node_id, chapter_path, section_number,
               rank
        FROM page_index
        WHERE page_index MATCH ?
    """
    params = [query]

    if reg_id:
        sql += " AND reg_id = ?"
        params.append(reg_id)

    if chapter_scope:
        sql += " AND chapter_path LIKE ?"
        params.append(f"%{chapter_scope}%")

    # 新增：块类型过滤
    if block_types:
        placeholders = ','.join('?' for _ in block_types)
        sql += f" AND block_type IN ({placeholders})"
        params.extend(block_types)

    # 新增：章节号精确匹配
    if section_number:
        sql += " AND section_number = ?"
        params.append(section_number)

    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)

    # ... 执行查询并返回结果
```

#### 4.2 LanceDB 索引扩展

**文件**: `src/grid_code/index/vector/lancedb.py`

```python
def index_page(
    self,
    page: PageDocument,
    doc_structure: DocumentStructure | None = None
) -> None:
    """索引页面向量，包含元数据"""
    records = []

    for block in page.content_blocks:
        content = block.content_markdown.strip()
        if not content or len(content) < 10:
            continue

        # 获取章节编号
        section_number = None
        if block.chapter_node_id and doc_structure:
            node = doc_structure.all_nodes.get(block.chapter_node_id)
            if node:
                section_number = node.section_number

        vector = self._embed_text(content)

        records.append({
            "vector": vector,
            "reg_id": page.reg_id,
            "page_num": page.page_num,
            "block_id": block.block_id,
            "block_type": block.block_type,          # 新增
            "chapter_node_id": block.chapter_node_id, # 新增
            "chapter_path": " > ".join(block.chapter_path),
            "section_number": section_number,         # 新增
            "content": content[:500],
        })

    # ... 批量插入
```

---

### 第五阶段：CLI 和 MCP 工具适配

#### 5.1 修改 ingest 命令

**文件**: `src/grid_code/cli.py`

```python
@app.command()
def ingest(
    file: Path = typer.Option(..., "--file", "-f", help="文档文件路径"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    format: str = typer.Option("docx", "--format", help="文件格式"),
):
    """转换并入库文档"""
    # 1. 解析文档
    parser = DoclingParser()
    result = parser.parse(file)

    # 2. 提取文档结构（第一阶段）
    extractor = PageExtractor(reg_id)
    doc_structure = extractor.extract_document_structure(result)
    console.print(f"[green]✓ 提取章节结构: {len(doc_structure.all_nodes)} 个章节[/green]")

    # 3. 提取页面内容（第二阶段）
    pages = extractor.extract_pages(result, doc_structure)
    toc = doc_structure.get_chapter_tree()  # 从结构生成目录

    # 4. 保存
    page_store = PageStore()
    page_store.save_pages(pages, toc, doc_structure, source_file=file.name)

    # 5. 索引
    fts_index = FTSIndex()
    vector_index = VectorIndex()

    for page in pages:
        fts_index.index_page(page, doc_structure)      # 传入结构
        vector_index.index_page(page, doc_structure)   # 传入结构

    console.print(f"[bold green]✓ 入库完成！[/bold green]")
```

#### 5.2 增强 MCP 工具

**文件**: `src/grid_code/mcp/tools.py`

```python
@mcp.tool()
async def get_toc(reg_id: str) -> TocTree:
    """获取规程目录（从文档结构生成）"""
    page_store = PageStore()

    # 优先使用 DocumentStructure
    try:
        doc_structure = page_store.load_document_structure(reg_id)
        toc_items = doc_structure.get_chapter_tree()

        info = page_store.load_info(reg_id)
        return TocTree(
            reg_id=reg_id,
            title=info.title,
            total_pages=info.total_pages,
            items=toc_items,
        )
    except:
        # 降级：使用旧方法
        return page_store.load_toc(reg_id)


@mcp.tool()
async def smart_search(
    query: str,
    reg_id: str,
    chapter_scope: str | None = None,
    limit: int = 10,
    block_types: list[str] | None = None,     # 新增
    section_number: str | None = None,        # 新增
) -> list[SearchResult]:
    """智能搜索（支持块类型和章节号过滤）"""
    hybrid_search = HybridSearch()

    results = hybrid_search.search(
        query=query,
        reg_id=reg_id,
        chapter_scope=chapter_scope,
        limit=limit,
        block_types=block_types,         # 传递过滤参数
        section_number=section_number,   # 传递章节号
    )

    return results


@mcp.tool()
async def get_chapter_structure(reg_id: str) -> dict:
    """获取完整章节结构（新增工具）"""
    page_store = PageStore()
    doc_structure = page_store.load_document_structure(reg_id)

    return {
        "reg_id": reg_id,
        "total_chapters": len(doc_structure.all_nodes),
        "root_nodes": [
            {
                "node_id": node_id,
                "section_number": doc_structure.all_nodes[node_id].section_number,
                "title": doc_structure.all_nodes[node_id].title,
                "level": doc_structure.all_nodes[node_id].level,
                "children_count": len(doc_structure.all_nodes[node_id].children_ids),
            }
            for node_id in doc_structure.root_node_ids
        ],
    }
```

---

### 第六阶段：数据迁移

#### 6.1 迁移策略

**推荐方式**：重新运行 ingest 命令

```bash
# 备份旧数据
make clean-backups
cp -r data/ data_backup/

# 重新入库
gridcode ingest -f /path/to/2024年国调直调安全自动装置调度运行管理规定（第二版）.pdf \
                 -r angui_2024 \
                 --format pdf

# 验证结果
gridcode inspect angui_2024 7
```

#### 6.2 迁移脚本（可选）

**文件**: `scripts/migrate_to_chapter_structure.py`

```python
#!/usr/bin/env python
"""
数据迁移脚本：从旧格式迁移到新格式
（可选，如果无法重新解析源文档时使用）
"""

def migrate_regulation(reg_id: str):
    """迁移单个规程"""
    page_store = PageStore()

    # 1. 加载所有页面
    pages = []
    page_num = 1
    while True:
        try:
            page = page_store.load_page(reg_id, page_num)
            pages.append(page)
            page_num += 1
        except PageNotFoundError:
            break

    # 2. 重建文档结构
    doc_structure = rebuild_document_structure(pages)

    # 3. 为每个块添加章节信息
    for page in pages:
        chapter_stack = page.chapter_path.copy()

        for block in page.content_blocks:
            if block.block_type == "heading" and block.heading_level:
                # 更新章节栈
                chapter_stack = chapter_stack[:block.heading_level - 1]
                chapter_stack.append(block.content_markdown)

                # 查找对应的章节节点
                node = find_matching_node(doc_structure, block.content_markdown, page.page_num)
                if node:
                    block.chapter_node_id = node.node_id

            block.chapter_path = chapter_stack.copy()

    # 4. 保存
    page_store.save_pages(pages, None, doc_structure, source_file="migrated")

    # 5. 重建索引
    rebuild_indexes(reg_id, pages, doc_structure)


if __name__ == "__main__":
    migrate_regulation("angui_2024")
```

---

## 关键文件清单

### 核心修改文件

1. **`src/grid_code/storage/models.py`**
   - 新增 `ChapterNode`
   - 新增 `DocumentStructure`
   - 扩展 `ContentBlock`（添加 `chapter_path`, `chapter_node_id`）
   - 扩展 `PageDocument`（添加 `chapter_nodes`）

2. **`src/grid_code/parser/page_extractor.py`**
   - 新增 `extract_document_structure()` 方法
   - 修改 `extract_pages()` 接受 `doc_structure` 参数
   - 新增 `_parse_section_info()` 辅助方法
   - 新增 `_find_chapter_node_by_text()` 辅助方法

3. **`src/grid_code/storage/page_store.py`**
   - 新增 `save_document_structure()` 方法
   - 新增 `load_document_structure()` 方法
   - 修改 `save_pages()` 接受 `doc_structure` 参数

4. **`src/grid_code/index/keyword/fts5.py`**
   - 修改 `_init_db()` 添加新字段
   - 修改 `index_page()` 接受 `doc_structure` 参数
   - 扩展 `search()` 支持 `block_types` 和 `section_number` 参数

5. **`src/grid_code/index/vector/lancedb.py`**
   - 修改 `index_page()` 添加元数据字段
   - 扩展 `search()` 支持块类型过滤

6. **`src/grid_code/index/base.py`**
   - 扩展 `BaseKeywordIndex.search()` 接口
   - 扩展 `BaseVectorIndex.search()` 接口

7. **`src/grid_code/index/hybrid_search.py`**
   - 修改 `search()` 传递新参数到后端索引

8. **`src/grid_code/cli.py`**
   - 修改 `ingest` 命令使用两阶段解析

9. **`src/grid_code/mcp/tools.py`**
   - 修改 `get_toc()` 使用 DocumentStructure
   - 扩展 `smart_search()` 支持新参数
   - 新增 `get_chapter_structure()` 工具

### 新增文件

10. **`scripts/migrate_to_chapter_structure.py`**
    - 数据迁移脚本（可选）

---

## 实施优先级

### P0 - 核心功能

1. 数据模型扩展（ChapterNode, DocumentStructure）
2. 两阶段解析逻辑
3. 存储层扩展

### P1 - 索引增强

4. FTS5 和 LanceDB 索引扩展
5. 支持块类型过滤和章节号查询

### P2 - 工具适配

6. CLI 命令更新
7. MCP 工具增强
8. 数据迁移脚本

---

## 测试验证

### 单元测试

```python
# tests/test_chapter_structure.py
def test_extract_document_structure():
    """测试文档结构提取"""
    # 验证章节节点数量
    # 验证层级关系正确性
    # 验证章节号和标题分离

def test_chapter_path_propagation():
    """测试章节路径传播"""
    # 验证每个块的 chapter_path 正确
    # 验证跨页章节关联正确

def test_section_content_block():
    """测试章节号+内容混合块处理"""
    # 验证直接内容正确提取到 section_content 块
    # 验证 ChapterNode 的 has_direct_content 标记
```

### 集成测试

```bash
# 完整流程测试
gridcode ingest -f data/test.pdf -r test_2024 --format pdf

# 验证文档结构
gridcode inspect test_2024 7

# 验证搜索过滤
gridcode search "母线失压" --reg-id test_2024 --block-types text,section_content

# 验证章节查询
gridcode search "安控装置" --reg-id test_2024 --section-number "2.1.4.1.6"
```

---

## 预期效果

### 解决的问题

1. ✅ **章节号+内容混合**：章节号存在 ChapterNode，内容存在 section_content 块
2. ✅ **块级章节信息**：每个块都有 `chapter_path` 和 `chapter_node_id`
3. ✅ **索引元数据丰富**：支持按 `block_type`、`section_number` 过滤
4. ✅ **完整章节结构树**：DocumentStructure 提供全局导航

### 查询示例

```python
# 示例1：只搜索表格内容
results = smart_search(
    query="电压等级",
    reg_id="angui_2024",
    block_types=["table"]
)

# 示例2：精确定位到某章节
results = smart_search(
    query="安控装置",
    reg_id="angui_2024",
    section_number="2.1.4.1.6"
)

# 示例3：获取完整章节树
structure = get_chapter_structure("angui_2024")
# 输出：{
#   "total_chapters": 150,
#   "root_nodes": [
#     {"section_number": "1", "title": "总则", "level": 1, ...},
#     {"section_number": "2", "title": "安全稳定控制装置", "level": 1, ...},
#   ]
# }
```

---

## 风险和应对

### 风险1：解析准确性下降

- **风险**：两阶段解析可能导致章节识别不准确
- **应对**：充分的单元测试 + 人工抽查验证

### 风险2：存储空间增加

- **风险**：DocumentStructure 和块级 chapter_path 增加存储
- **应对**：可接受（约 10-20% 增长）

### 风险3：索引重建时间长

- **风险**：大文档重建索引耗时
- **应对**：提供进度条 + 支持增量索引（后续优化）

---

## 后续优化方向

1. **增量索引**：只索引变更的页面
2. **章节摘要**：为每个章节自动生成摘要
3. **跨章节引用**：识别章节间的引用关系
4. **可视化导航**：Web UI 展示章节树
