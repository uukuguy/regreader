"""GridCode CLI 入口

提供命令行操作接口。
"""

import asyncio
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="gridcode",
    help="GridCode - 电力系统安规智能检索 Agent",
    add_completion=False,
)
console = Console()


class TransportType(str, Enum):
    """MCP 传输类型"""
    sse = "sse"
    stdio = "stdio"


class AgentType(str, Enum):
    """Agent 类型"""
    claude = "claude"
    pydantic = "pydantic"
    langgraph = "langgraph"


@app.command()
def ingest(
    file: Path = typer.Option(None, "--file", "-f", help="单个文档文件路径"),
    directory: Path = typer.Option(None, "--dir", "-d", help="文档目录路径"),
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="规程标识"),
    file_format: str = typer.Option("docx", "--format", help="文件格式 (docx, pdf)"),
):
    """转换并入库文档到 GridCode"""
    from grid_code.index import FTSIndex, VectorIndex
    from grid_code.parser import DoclingParser, PageExtractor
    from grid_code.storage import PageStore

    if not file and not directory:
        console.print("[red]错误: 必须指定 --file 或 --dir[/red]")
        raise typer.Exit(1)

    files_to_process: list[Path] = []

    if file:
        if not file.exists():
            console.print(f"[red]错误: 文件不存在: {file}[/red]")
            raise typer.Exit(1)
        files_to_process.append(file)
    else:
        if not directory.exists():
            console.print(f"[red]错误: 目录不存在: {directory}[/red]")
            raise typer.Exit(1)
        pattern = f"*.{file_format}"
        files_to_process = list(directory.glob(pattern))
        if not files_to_process:
            console.print(f"[yellow]警告: 目录中没有 {file_format} 文件[/yellow]")
            raise typer.Exit(0)

    parser = DoclingParser()
    page_store = PageStore()
    fts_index = FTSIndex()
    vector_index = VectorIndex()

    for doc_file in files_to_process:
        current_reg_id = reg_id or doc_file.stem
        console.print(f"\n[bold]处理文件: {doc_file.name}[/bold]")
        console.print(f"规程标识: {current_reg_id}")

        with console.status("解析文档..."):
            result = parser.parse(doc_file)

        extractor = PageExtractor(current_reg_id)

        # 第一阶段：提取文档结构
        with console.status("提取章节结构..."):
            doc_structure = extractor.extract_document_structure(result)
        console.print(f"[green]✓ 提取章节结构: {len(doc_structure.all_nodes)} 个章节[/green]")

        # 第二阶段：提取页面内容
        with console.status("提取页面内容..."):
            pages = extractor.extract_pages(result, doc_structure)
            toc = extractor.extract_toc(result)

        console.print(f"提取完成: {len(pages)} 页")

        with console.status("保存页面..."):
            page_store.save_pages(pages, toc, doc_structure, doc_file.name)

        with console.status("构建 FTS 索引..."):
            fts_index.index_pages(pages, doc_structure)

        with console.status("构建向量索引..."):
            vector_index.index_pages(pages, doc_structure)

        console.print(f"[green]✓ 规程 {current_reg_id} 入库完成[/green]")

    console.print(f"\n[bold green]全部完成! 共处理 {len(files_to_process)} 个文件[/bold green]")


@app.command()
def serve(
    transport: TransportType = typer.Option(
        TransportType.sse, "--transport", "-t", help="传输协议"
    ),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8080, "--port", "-p", help="监听端口"),
):
    """启动 MCP Server"""
    from grid_code.mcp.server import mcp_server

    console.print(f"[bold]启动 MCP Server[/bold]")
    console.print(f"传输协议: {transport.value}")

    if transport == TransportType.sse:
        console.print(f"地址: http://{host}:{port}")
        mcp_server.run(transport="sse")
    else:
        console.print("使用 stdio 模式")
        mcp_server.run(transport="stdio")


@app.command("list")
def list_regulations():
    """列出所有已入库的规程"""
    from grid_code.storage import PageStore

    page_store = PageStore()
    regulations = page_store.list_regulations()

    if not regulations:
        console.print("[yellow]暂无入库的规程[/yellow]")
        return

    table = Table(title="已入库规程")
    table.add_column("规程标识", style="cyan")
    table.add_column("标题", style="green")
    table.add_column("页数", justify="right")
    table.add_column("入库时间")

    for reg in regulations:
        table.add_row(
            reg.reg_id,
            reg.title,
            str(reg.total_pages),
            reg.indexed_at[:19],  # 截断毫秒
        )

    console.print(table)


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索查询"),
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="限定规程"),
    chapter: str = typer.Option(None, "--chapter", "-c", help="限定章节"),
    limit: int = typer.Option(10, "--limit", "-l", help="结果数量"),
    block_types: str = typer.Option(None, "--types", "-T", help="限定块类型（逗号分隔，如 text,table）"),
    section_number: str = typer.Option(None, "--section", "-s", help="精确匹配章节号（如 2.1.4.1.6）"),
):
    """测试检索功能"""
    from grid_code.index import HybridSearch

    # 解析块类型参数
    block_type_list = None
    if block_types:
        block_type_list = [t.strip() for t in block_types.split(",")]

    hybrid_search = HybridSearch()
    results = hybrid_search.search(
        query,
        reg_id=reg_id,
        chapter_scope=chapter,
        limit=limit,
        block_types=block_type_list,
        section_number=section_number,
    )

    if not results:
        console.print("[yellow]未找到相关结果[/yellow]")
        return

    console.print(f"\n[bold]找到 {len(results)} 条结果:[/bold]\n")

    for i, result in enumerate(results, 1):
        console.print(f"[bold cyan]{i}. {result.source}[/bold cyan]")
        if result.chapter_path:
            console.print(f"   章节: {' > '.join(result.chapter_path)}")
        console.print(f"   相关度: {result.score:.4f}")
        console.print(f"   {result.snippet[:200]}...")
        console.print()


@app.command("read-chapter")
def read_chapter(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    section: str = typer.Option(..., "--section", "-s", help="章节编号，如 '2.1.4.1.6'"),
    no_children: bool = typer.Option(False, "--no-children", help="不包含子章节内容"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """读取指定章节的完整内容"""
    from rich.markdown import Markdown

    from grid_code.exceptions import ChapterNotFoundError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.read_chapter_content(
            reg_id,
            section,
            include_children=not no_children,
        )
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except ChapterNotFoundError:
        console.print(f"[red]错误: 章节 {section} 不存在[/red]")
        raise typer.Exit(1)

    if "error" in result:
        console.print(f"[red]错误: {result['error']}[/red]")
        raise typer.Exit(1)

    # 输出到文件
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {result['section_number']} {result['title']}\n\n"
        content += f"**路径**: {' > '.join(result['full_path'])}\n"
        content += f"**页码**: P{result['page_range'][0]}-{result['page_range'][1]}\n"
        content += f"**来源**: {result['source']}\n\n"
        content += "---\n\n"
        content += result['content_markdown']
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    # 输出到控制台
    console.print(f"\n[bold]{result['section_number']} {result['title']}[/bold]")
    console.print(f"[dim]路径: {' > '.join(result['full_path'])}[/dim]")
    console.print(f"[dim]页码: P{result['page_range'][0]}-{result['page_range'][1]}[/dim]")
    console.print(f"[dim]内容块: {result['block_count']} 个[/dim]")

    if result['children']:
        console.print(f"\n[bold]子章节 ({len(result['children'])} 个):[/bold]")
        for child in result['children']:
            console.print(f"  • {child['section_number']} {child['title']} (P{child['page_num']})")

    console.print(f"\n[dim]{'包含' if result['children_included'] else '不包含'}子章节内容[/dim]")
    console.print("\n" + "─" * 60 + "\n")

    # 显示 Markdown 内容
    if result['content_markdown']:
        console.print(Markdown(result['content_markdown']))
    else:
        console.print("[yellow]该章节暂无内容[/yellow]")


@app.command()
def chat(
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="限定规程"),
    agent_type: AgentType = typer.Option(
        AgentType.claude, "--agent", "-a", help="Agent 类型"
    ),
):
    """与 Agent 对话（交互模式）"""

    async def run_chat():
        # 创建 Agent
        if agent_type == AgentType.claude:
            from grid_code.agents import ClaudeAgent
            agent = ClaudeAgent(reg_id=reg_id)
        elif agent_type == AgentType.pydantic:
            from grid_code.agents import PydanticAIAgent
            agent = PydanticAIAgent(reg_id=reg_id)
        else:
            from grid_code.agents import LangGraphAgent
            agent = LangGraphAgent(reg_id=reg_id)

        console.print(f"[bold]GridCode Agent ({agent.name})[/bold]")
        console.print("输入问题进行对话，输入 'exit' 退出\n")

        try:
            while True:
                try:
                    user_input = console.input("[bold green]你: [/bold green]")
                except (KeyboardInterrupt, EOFError):
                    break

                if user_input.lower() in ("exit", "quit", "q"):
                    break

                if not user_input.strip():
                    continue

                with console.status("思考中..."):
                    response = await agent.chat(user_input)

                console.print(f"\n[bold blue]GridCode:[/bold blue]")
                console.print(response.content)

                if response.sources:
                    console.print(f"\n[dim]来源: {', '.join(response.sources)}[/dim]")
                console.print()
        finally:
            # 确保关闭 MCP 连接
            if hasattr(agent, "close"):
                await agent.close()

        console.print("[dim]再见![/dim]")

    asyncio.run(run_chat())


@app.command()
def delete(
    reg_id: str = typer.Argument(..., help="要删除的规程标识"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除已入库的规程"""
    from grid_code.index import FTSIndex, VectorIndex
    from grid_code.storage import PageStore

    page_store = PageStore()

    if not page_store.exists(reg_id):
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"确定要删除规程 {reg_id}?")
        if not confirm:
            console.print("已取消")
            raise typer.Exit(0)

    with console.status("删除中..."):
        page_store.delete_regulation(reg_id)
        FTSIndex().delete_regulation(reg_id)
        VectorIndex().delete_regulation(reg_id)

    console.print(f"[green]✓ 规程 {reg_id} 已删除[/green]")


@app.command()
def inspect(
    reg_id: str = typer.Argument(..., help="规程标识"),
    page_num: int = typer.Argument(..., help="页码"),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
    show_vectors: bool = typer.Option(False, "--show-vectors", help="显示向量数据（默认隐藏）"),
):
    """检查指定页面在不同数据源中的原始数据"""
    from grid_code.exceptions import PageNotFoundError, RegulationNotFoundError
    from grid_code.services.inspect import InspectService
    from grid_code.services.inspect_display import InspectDisplay

    service = InspectService()
    display = InspectDisplay()

    try:
        with console.status(f"检查 {reg_id} P{page_num} 的数据..."):
            result, analysis = service.inspect_page(reg_id, page_num, show_vectors)

        # 显示结果
        display.display_result(result, analysis)

        # 保存 JSON
        saved_path = service.save_json(result, analysis, output)
        display.display_save_message(str(saved_path))

    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        console.print("[yellow]提示: 使用 'grid-code list' 查看已入库的规程[/yellow]")
        raise typer.Exit(1)
    except PageNotFoundError:
        console.print(f"[red]错误: 页面 {page_num} 不存在[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# ==================== 基础工具 CLI 命令 ====================


@app.command()
def toc(
    reg_id: str = typer.Argument(..., help="规程标识"),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
    expand_all: bool = typer.Option(False, "--expand", "-e", help="展开所有层级"),
    max_level: int = typer.Option(3, "--level", "-l", help="显示的最大层级深度"),
):
    """获取规程目录树（带章节结构）"""
    import json

    from rich.panel import Panel
    from rich.text import Text
    from rich.tree import Tree

    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.storage import PageStore

    page_store = PageStore()

    # 检查规程是否存在
    if not page_store.exists(reg_id):
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    # 加载章节结构
    try:
        doc_structure = page_store.load_document_structure(reg_id)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    # 读取第一页获取文档标题
    first_page = page_store.load_page(reg_id, 1)
    doc_title = reg_id
    doc_subtitle = ""
    for block in first_page.content_blocks[:3]:
        if block.block_type == "text":
            content = block.content_markdown.strip()
            if not doc_title or doc_title == reg_id:
                doc_title = content
            elif not doc_subtitle:
                doc_subtitle = content
                break

    if output:
        # 导出JSON时使用章节结构
        result = {
            "reg_id": reg_id,
            "title": doc_title,
            "subtitle": doc_subtitle,
            "total_chapters": len(doc_structure.all_nodes),
            "chapters": [
                {
                    "section_number": node.section_number,
                    "title": node.title,
                    "level": node.level,
                    "page_num": node.page_num,
                    "children_count": len(node.children_ids),
                }
                for node in doc_structure.all_nodes.values()
            ],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    # 定义层级对应的颜色
    level_colors = {
        1: "bold green",      # 节 (如 1.1, 2.1)
        2: "yellow",          # 条 (如 2.1.1)
        3: "white",           # 款 (如 2.1.1.1)
        4: "dim white",       # 项 (如 2.1.1.1.1)
        5: "dim",             # 更深层级
    }

    def get_color(display_level: int) -> str:
        """获取层级颜色"""
        return level_colors.get(display_level, "dim")

    def add_chapter_node(parent_tree: Tree, node_id: str, display_level: int = 1):
        """递归添加章节节点到树"""
        node = doc_structure.all_nodes.get(node_id)
        if not node:
            return

        color = get_color(display_level)

        # 构建节点标签：章节号 + 标题（截断）
        section = node.section_number
        title = node.title[:50] + "..." if len(node.title) > 50 else node.title

        label = Text()
        label.append(f"{section} ", style="bold " + color)
        label.append(title, style=color)
        label.append(f"  {node.page_num}", style="dim")

        if node.children_ids and display_level < max_level:
            # 有子节点且未达到最大层级
            branch = parent_tree.add(label)
            for child_id in node.children_ids:
                add_chapter_node(branch, child_id, display_level + 1)
        elif node.children_ids and display_level >= max_level and not expand_all:
            # 有子节点但已达到最大层级，显示折叠提示
            collapsed_label = Text()
            collapsed_label.append(f"{section} ", style="bold " + color)
            collapsed_label.append(title, style=color)
            collapsed_label.append(f"  {node.page_num}", style="dim")
            collapsed_label.append(f"  +{len(node.children_ids)}", style="dim yellow")
            parent_tree.add(collapsed_label)
        elif node.children_ids and expand_all:
            # 展开所有层级
            branch = parent_tree.add(label)
            for child_id in node.children_ids:
                add_chapter_node(branch, child_id, relative_depth + 1)
        else:
            # 叶子节点
            parent_tree.add(label)

    # 创建根节点（文档标题）
    root_label = Text()
    root_label.append(doc_title, style="bold blue")
    if doc_subtitle:
        root_label.append("\n   ", style="")
        root_label.append(doc_subtitle, style="dim")

    tree = Tree(root_label)

    # 按章节编号前缀分组显示根节点
    if doc_structure.root_node_ids:
        # 将根节点按章节编号前缀分组（1.x, 2.x, 3.x...）
        chapter_groups: dict[str, list[str]] = {}
        for node_id in doc_structure.root_node_ids:
            node = doc_structure.all_nodes.get(node_id)
            if node:
                # 提取章节编号前缀（如 "1.1" -> "1", "2.3.4" -> "2"）
                prefix = node.section_number.split(".")[0] if node.section_number else "0"
                if prefix not in chapter_groups:
                    chapter_groups[prefix] = []
                chapter_groups[prefix].append(node_id)

        # 查找一级章节标题（从页面内容中读取，如 "1. 总则"）
        chapter_titles: dict[str, str] = {}
        # 收集所有章节分组的起始页
        chapter_start_pages = set()
        for prefix, node_ids in chapter_groups.items():
            first_node = doc_structure.all_nodes.get(node_ids[0])
            if first_node:
                # 搜索起始页及前一页
                chapter_start_pages.add(first_node.page_num)
                if first_node.page_num > 1:
                    chapter_start_pages.add(first_node.page_num - 1)

        # 在相关页面中查找一级章节标题
        for page_num in sorted(chapter_start_pages):
            try:
                page = page_store.load_page(reg_id, page_num)
                for block in page.content_blocks:
                    text = block.content_markdown.strip()
                    # 匹配 "1. 标题" 或 "2. 标题" 格式
                    import re
                    match = re.match(r'^(\d{1,2})\.\s+(.+)$', text)
                    if match:
                        prefix = match.group(1)
                        title = match.group(2).strip()
                        if prefix not in chapter_titles:
                            chapter_titles[prefix] = title
            except Exception:
                continue

        # 按前缀排序显示，为每个前缀创建一级章节分组
        for prefix in sorted(chapter_groups.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            node_ids = chapter_groups[prefix]

            # 创建一级章节分组节点
            chapter_title = chapter_titles.get(prefix, "")
            group_label = Text()
            group_label.append(f"{prefix}. ", style="bold cyan")
            group_label.append(chapter_title if chapter_title else f"第{prefix}章", style="bold cyan")

            # 获取该组第一个节点的页码
            first_node = doc_structure.all_nodes.get(node_ids[0])
            if first_node:
                group_label.append("  ", style="")
                group_label.append(f"{first_node.page_num}", style="dim cyan")

            # 创建分组分支
            group_branch = tree.add(group_label)

            # 添加该组的所有章节节点
            for node_id in node_ids:
                add_chapter_node(group_branch, node_id, 1)

        # 统计信息
        total_count = len(doc_structure.all_nodes)
        group_count = len(chapter_groups)
        console.print()
        console.print(Panel(
            tree,
            title=f"[bold blue]目录结构[/bold blue]",
            subtitle=f"[dim]共 {group_count} 章 {total_count} 个章节节点 | 显示深度: {max_level}[/dim]",
            border_style="blue",
            padding=(1, 2),
        ))
        console.print()

        # 图例
        console.print("[dim]页码显示在章节标题后，+N 表示有 N 个子节点被折叠[/dim]")
        console.print(f"[dim]提示: --level N 设置显示深度, --expand 展开全部[/dim]")
    else:
        console.print("[yellow]章节结构为空[/yellow]")


@app.command("read-pages")
def read_pages(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    start: int = typer.Option(..., "--start", "-s", help="起始页码"),
    end: int = typer.Option(..., "--end", "-e", help="结束页码"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """读取指定页面范围的内容"""
    from rich.markdown import Markdown

    from grid_code.exceptions import InvalidPageRangeError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.read_page_range(reg_id, start, end)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except InvalidPageRangeError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {reg_id} P{result['start_page']}-{result['end_page']}\n\n"
        content += result["content_markdown"]
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    console.print(f"\n[bold]{result['source']}[/bold]")
    console.print(f"[dim]页数: {result['page_count']} | 跨页表格: {'是' if result['has_merged_tables'] else '否'}[/dim]")
    console.print("\n" + "─" * 60 + "\n")
    console.print(Markdown(result["content_markdown"]))


@app.command("chapter-structure")
def chapter_structure(
    reg_id: str = typer.Argument(..., help="规程标识"),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
):
    """获取完整章节结构"""
    import json

    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.get_chapter_structure(reg_id)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if "message" in result:
        console.print(f"[yellow]警告: {result['message']}[/yellow]")
        return

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    table = Table(title=f"{reg_id} 章节结构 (共 {result['total_chapters']} 个节点)")
    table.add_column("节点ID", style="dim")
    table.add_column("章节号", style="cyan")
    table.add_column("标题", style="green")
    table.add_column("级别", justify="right")
    table.add_column("页码", justify="right")
    table.add_column("子节点数", justify="right")

    for node in result["root_nodes"]:
        table.add_row(
            node["node_id"][:8],
            node["section_number"],
            node["title"][:30],
            str(node["level"]),
            str(node["page_num"]),
            str(node["children_count"]),
        )

    console.print(table)


@app.command("page-info")
def page_info(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    page_num: int = typer.Option(..., "--page", "-p", help="页码"),
):
    """获取页面章节信息"""
    from grid_code.exceptions import PageNotFoundError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.get_page_chapter_info(reg_id, page_num)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except PageNotFoundError:
        console.print(f"[red]错误: 页面 {page_num} 不存在[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{reg_id} P{page_num} 章节信息[/bold]")
    console.print(f"[dim]活跃章节: {result['total_chapters']} | 新章节: {result['new_chapters_count']} | 延续章节: {result['inherited_chapters_count']}[/dim]\n")

    table = Table()
    table.add_column("章节号", style="cyan")
    table.add_column("标题", style="green")
    table.add_column("级别", justify="right")
    table.add_column("状态")

    for ch in result["active_chapters"]:
        status = "[dim]延续[/dim]" if ch["inherited"] else "[green]新开始[/green]"
        table.add_row(
            ch["section_number"],
            ch["title"][:40],
            str(ch["level"]),
            status,
        )

    console.print(table)


# ==================== Phase 1: 核心多跳工具 CLI 命令 ====================


@app.command("lookup-annotation")
def lookup_annotation(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    annotation_id: str = typer.Argument(..., help="注释标识，如 '注1', '方案A'"),
    page_hint: int | None = typer.Option(None, "--page", "-p", help="页码提示，优先从该页附近搜索"),
):
    """查找注释内容（支持变体匹配：注1/注①/注一）"""
    from rich.markdown import Markdown

    from grid_code.exceptions import AnnotationNotFoundError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.lookup_annotation(reg_id, annotation_id, page_hint)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except AnnotationNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]{result['annotation_id']}[/bold cyan] [dim]({result['source']})[/dim]\n")
    console.print(Markdown(result["content"]))

    if result.get("related_blocks"):
        console.print(f"\n[dim]关联块: {', '.join(result['related_blocks'])}[/dim]")


@app.command("search-tables")
def search_tables(
    query: str = typer.Argument(..., help="搜索查询，如 '母线失压' 或 '表6-2'"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    chapter: str | None = typer.Option(None, "--chapter", "-c", help="限定章节范围"),
    no_cells: bool = typer.Option(False, "--no-cells", help="不搜索单元格内容"),
    limit: int = typer.Option(10, "--limit", "-l", help="结果数量"),
):
    """搜索表格（按标题或单元格内容）"""
    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        results = tools.search_tables(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter,
            search_cells=not no_cells,
            limit=limit,
        )
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]未找到匹配的表格[/yellow]")
        return

    console.print(f"\n[bold]找到 {len(results)} 个表格:[/bold]\n")

    for i, table in enumerate(results, 1):
        console.print(f"[bold cyan]{i}. {table['caption'] or '(无标题)'}[/bold cyan]")
        console.print(f"   表格ID: {table['table_id']}")
        console.print(f"   位置: {table['source']} | {table['row_count']}行 x {table['col_count']}列")
        console.print(f"   匹配类型: {table['match_type']} | 跨页: {'是' if table['is_truncated'] else '否'}")
        if table.get("matched_cells"):
            console.print(f"   匹配单元格: {len(table['matched_cells'])} 个")
        if table.get("chapter_path"):
            console.print(f"   章节: {' > '.join(table['chapter_path'])}")
        console.print()


@app.command("resolve-reference")
def resolve_reference(
    reference: str = typer.Argument(..., help="引用文本，如 '见第六章', '参见表6-2'"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
):
    """解析交叉引用"""
    from rich.markdown import Markdown

    from grid_code.exceptions import ReferenceResolutionError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.resolve_reference(reg_id, reference)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except ReferenceResolutionError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)

    if result.get("error"):
        console.print(f"[yellow]解析失败: {result['error']}[/yellow]")
        console.print(f"引用类型: {result['reference_type']}")
        console.print(f"解析目标: {result['parsed_target']}")
        return

    console.print(f"\n[bold]引用解析结果[/bold]\n")
    console.print(f"引用类型: [cyan]{result['reference_type']}[/cyan]")
    console.print(f"解析目标: [cyan]{result['parsed_target']}[/cyan]")
    console.print(f"来源: {result['source']}")

    if result.get("target_location"):
        console.print(f"\n[bold]目标位置:[/bold]")
        for key, value in result["target_location"].items():
            console.print(f"  {key}: {value}")

    if result.get("preview"):
        console.print(f"\n[bold]内容预览:[/bold]")
        console.print(Markdown(result["preview"]))


# ==================== Phase 2: 上下文工具 CLI 命令 ====================


@app.command("search-annotations")
def search_annotations(
    reg_id: str = typer.Argument(..., help="规程标识"),
    pattern: str | None = typer.Option(None, "--pattern", "-p", help="内容匹配模式"),
    annotation_type: str | None = typer.Option(None, "--type", "-t", help="注释类型: note(注x) / plan(方案x)"),
):
    """搜索所有注释"""
    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        results = tools.search_annotations(reg_id, pattern, annotation_type)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]未找到匹配的注释[/yellow]")
        return

    console.print(f"\n[bold]找到 {len(results)} 个注释:[/bold]\n")

    table = Table()
    table.add_column("页码", justify="right", style="cyan")
    table.add_column("标识", style="green")
    table.add_column("内容预览")

    for ann in results:
        table.add_row(
            str(ann["page_num"]),
            ann["annotation_id"],
            ann["content"][:50] + "..." if len(ann["content"]) > 50 else ann["content"],
        )

    console.print(table)


@app.command("get-table")
def get_table(
    table_id: str = typer.Argument(..., help="表格标识"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    no_merge: bool = typer.Option(False, "--no-merge", help="不合并跨页表格"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """获取完整表格内容（按表格ID）"""
    from rich.markdown import Markdown

    from grid_code.exceptions import RegulationNotFoundError, TableNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.get_table_by_id(reg_id, table_id, include_merged=not no_merge)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except TableNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {result['caption'] or table_id}\n\n"
        content += f"来源: {result['source']}\n\n"
        content += result["markdown"]
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    console.print(f"\n[bold]{result['caption'] or table_id}[/bold]")
    console.print(f"[dim]来源: {result['source']}[/dim]")
    console.print(f"[dim]大小: {result['row_count']}行 x {result['col_count']}列 | 页码范围: P{result['page_range'][0]}-{result['page_range'][1]}[/dim]")

    if result.get("chapter_path"):
        console.print(f"[dim]章节: {' > '.join(result['chapter_path'])}[/dim]")

    console.print("\n" + "─" * 60 + "\n")
    console.print(Markdown(result["markdown"]))

    if result.get("annotations"):
        console.print("\n[bold]相关注释:[/bold]")
        for ann in result["annotations"]:
            console.print(f"  • {ann['annotation_id']}: {ann['content'][:100]}...")


@app.command("get-block-context")
def get_block_context(
    block_id: str = typer.Argument(..., help="内容块标识"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    context: int = typer.Option(2, "--context", "-c", help="上下文块数量"),
):
    """获取内容块及其上下文"""
    from rich.markdown import Markdown
    from rich.panel import Panel

    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.get_block_with_context(reg_id, block_id, context)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if "error" in result:
        console.print(f"[red]错误: {result['error']}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]{result['source']}[/bold]")

    # 显示活跃章节
    if result.get("active_chapters"):
        chapters = " > ".join([f"{ch['section_number']} {ch['title']}" for ch in result["active_chapters"][:3]])
        console.print(f"[dim]章节: {chapters}[/dim]\n")

    # 显示前序块
    if result.get("before_blocks"):
        console.print("[dim]─── 前序内容 ───[/dim]")
        for block in result["before_blocks"]:
            from_page = f" (P{block['from_page']})" if block.get("from_page") else ""
            console.print(f"[dim]{block['block_type']}{from_page}[/dim]")
            console.print(Markdown(block["content_markdown"][:200] + "..."))

    # 显示目标块
    target = result["target_block"]
    console.print("\n[bold green]─── 目标内容 ───[/bold green]")
    console.print(Panel(Markdown(target["content_markdown"]), title=f"[{target['block_type']}]"))

    # 显示后续块
    if result.get("after_blocks"):
        console.print("[dim]─── 后续内容 ───[/dim]")
        for block in result["after_blocks"]:
            from_page = f" (P{block['from_page']})" if block.get("from_page") else ""
            console.print(f"[dim]{block['block_type']}{from_page}[/dim]")
            console.print(Markdown(block["content_markdown"][:200] + "..."))

    # 显示页面注释
    if result.get("page_annotations"):
        console.print("\n[bold]页面注释:[/bold]")
        for ann in result["page_annotations"]:
            console.print(f"  • {ann['annotation_id']}: {ann['content'][:80]}...")


# ==================== Phase 3: 发现工具 CLI 命令 ====================


@app.command("find-similar")
def find_similar(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    query: str | None = typer.Option(None, "--query", "-q", help="查询文本"),
    block_id: str | None = typer.Option(None, "--block", "-b", help="源内容块ID"),
    limit: int = typer.Option(5, "--limit", "-l", help="结果数量"),
    same_page: bool = typer.Option(False, "--same-page", help="包含同页内容"),
):
    """查找语义相似的内容"""
    from grid_code.exceptions import RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    if not query and not block_id:
        console.print("[red]错误: 必须提供 --query 或 --block 参数[/red]")
        raise typer.Exit(1)

    tools = GridCodeTools()

    try:
        results = tools.find_similar_content(
            reg_id=reg_id,
            query_text=query,
            source_block_id=block_id,
            limit=limit,
            exclude_same_page=not same_page,
        )
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]未找到相似内容[/yellow]")
        return

    if isinstance(results[0], dict) and "error" in results[0]:
        console.print(f"[red]错误: {results[0]['error']}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]找到 {len(results)} 条相似内容:[/bold]\n")

    for i, item in enumerate(results, 1):
        console.print(f"[bold cyan]{i}. {item['source']}[/bold cyan]")
        console.print(f"   相似度: {item['similarity_score']:.4f}")
        if item.get("chapter_path"):
            console.print(f"   章节: {' > '.join(item['chapter_path'])}")
        console.print(f"   {item['snippet'][:150]}...")
        console.print()


@app.command("compare-sections")
def compare_sections(
    section_a: str = typer.Argument(..., help="第一个章节编号"),
    section_b: str = typer.Argument(..., help="第二个章节编号"),
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    output: Path | None = typer.Option(None, "--output", "-o", help="JSON 输出文件路径"),
):
    """比较两个章节的内容"""
    import json

    from grid_code.exceptions import ChapterNotFoundError, RegulationNotFoundError
    from grid_code.mcp.tools import GridCodeTools

    tools = GridCodeTools()

    try:
        result = tools.compare_sections(reg_id, section_a, section_b)
    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except ChapterNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        console.print(f"[green]✓ 已保存到 {output}[/green]")
        return

    console.print(f"\n[bold]章节比较: {section_a} vs {section_b}[/bold]\n")

    # 显示两列对比
    table = Table(title="结构对比")
    table.add_column("属性", style="dim")
    table.add_column(f"{section_a}", style="cyan")
    table.add_column(f"{section_b}", style="green")
    table.add_column("差异", style="yellow")

    a_info = result["section_a_info"]
    b_info = result["section_b_info"]
    diff = result["structural_comparison"]

    table.add_row("标题", a_info["title"][:30], b_info["title"][:30], "")
    table.add_row("页码范围", f"P{a_info['page_range'][0]}-{a_info['page_range'][1]}", f"P{b_info['page_range'][0]}-{b_info['page_range'][1]}", "")
    table.add_row("内容块数", str(a_info["block_count"]), str(b_info["block_count"]), f"{diff['block_diff']:+d}")
    table.add_row("子章节数", str(a_info["children_count"]), str(b_info["children_count"]), f"{diff['children_diff']:+d}")
    table.add_row("表格数", str(a_info["table_count"]), str(b_info["table_count"]), f"{diff['table_diff']:+d}")
    table.add_row("列表项数", str(a_info["list_count"]), str(b_info["list_count"]), f"{diff['list_diff']:+d}")

    console.print(table)

    if result.get("common_keywords"):
        console.print(f"\n[bold]共同关键词:[/bold] {', '.join(result['common_keywords'][:10])}")


@app.command()
def version():
    """显示版本信息"""
    from grid_code import __version__
    console.print(f"GridCode v{__version__}")


if __name__ == "__main__":
    app()
