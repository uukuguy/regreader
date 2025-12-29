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


@app.command()
def version():
    """显示版本信息"""
    from grid_code import __version__
    console.print(f"GridCode v{__version__}")


if __name__ == "__main__":
    app()
