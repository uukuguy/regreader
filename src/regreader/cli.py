"""RegReader CLI 入口

提供命令行操作接口。
支持本地直接访问和 MCP 远程调用两种模式。
"""

import asyncio
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table


# ==================== 全局状态 ====================


class CLIState:
    """CLI 全局状态

    存储 MCP 模式相关的全局配置。
    """

    use_mcp: bool = False
    mcp_transport: str = "stdio"
    mcp_url: str | None = None


state = CLIState()


# ==================== 工具辅助函数 ====================


def get_tools():
    """获取工具实例（根据全局状态）

    根据 --mcp 选项决定使用本地直接访问还是 MCP 远程调用。

    Returns:
        RegReaderTools 或 RegReaderMCPToolsAdapter 实例
    """
    from regreader.mcp.factory import create_tools

    return create_tools(
        use_mcp=state.use_mcp,
        transport=state.mcp_transport if state.use_mcp else None,
        server_url=state.mcp_url,
    )


# ==================== CLI 应用 ====================


app = typer.Typer(
    name="gridcode",
    help="RegReader - 电力系统安规智能检索 Agent",
    add_completion=False,
)
console = Console()


@app.callback()
def main(
    mcp: Annotated[
        bool,
        typer.Option(
            "--mcp",
            help="使用 MCP 模式访问数据（通过 MCP Server）",
            envvar="GRIDCODE_USE_MCP",
        ),
    ] = False,
    mcp_transport: Annotated[
        str,
        typer.Option(
            "--mcp-transport",
            help="MCP 传输方式: stdio（自动启动子进程）, sse（连接外部服务）",
            envvar="GRIDCODE_MCP_TRANSPORT",
        ),
    ] = "stdio",
    mcp_url: Annotated[
        str | None,
        typer.Option(
            "--mcp-url",
            help="MCP SSE 服务器 URL（SSE 模式使用，如 http://localhost:8080/sse）",
            envvar="GRIDCODE_MCP_SERVER_URL",
        ),
    ] = None,
):
    """RegReader CLI - 电力系统安规智能检索 Agent

    使用 --mcp 标志启用 MCP 模式，通过 MCP Server 访问数据。

    示例:
        # 默认模式（本地直接访问）
        gridcode search "母线失压" -r angui_2024

        # MCP stdio 模式（自动启动子进程）
        gridcode --mcp search "母线失压" -r angui_2024

        # MCP SSE 模式（连接外部服务）
        gridcode --mcp --mcp-transport sse --mcp-url http://localhost:8080/sse search "母线失压"
    """
    state.use_mcp = mcp
    state.mcp_transport = mcp_transport
    state.mcp_url = mcp_url

    if mcp:
        url_display = mcp_url or "(stdio 子进程)"
        console.print(f"[dim]MCP 模式: transport={mcp_transport}, url={url_display}[/dim]")


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
    no_ocr: bool = typer.Option(False, "--no-ocr", help="禁用 OCR（加快解析速度）"),
):
    """转换并入库文档到 RegReader"""
    from regreader.index import FTSIndex, VectorIndex
    from regreader.parser import DoclingParser, DoclingParserConfig, PageExtractor, TableRegistryBuilder
    from regreader.storage import PageStore

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

    # 配置解析器
    config = DoclingParserConfig(do_ocr=not no_ocr)
    parser = DoclingParser(config)
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
            # 从 DocumentStructure 构建 TocTree（确保与章节识别逻辑一致）
            toc = extractor.build_toc_from_structure(doc_structure, len(pages))

        console.print(f"提取完成: {len(pages)} 页")

        with console.status("保存页面..."):
            page_store.save_pages(pages, toc, doc_structure, doc_file.name)

        # 构建表格注册表
        with console.status("构建表格注册表..."):
            table_builder = TableRegistryBuilder(current_reg_id)
            table_registry = table_builder.build(pages)
            page_store.save_table_registry(table_registry)
        console.print(
            f"[green]✓ 表格注册表: {table_registry.total_tables} 个表格, "
            f"{table_registry.cross_page_tables} 个跨页表格[/green]"
        )

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
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="详细模式：显示 DEBUG 日志"
    ),
):
    """启动 MCP Server"""
    import sys

    from loguru import logger

    from regreader.mcp.server import create_mcp_server

    # 默认抑制 DEBUG 日志，verbose 模式下保留
    if not verbose:
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        )

    # stdio 模式下不能向 stdout 输出任何非 JSON-RPC 消息
    if transport == TransportType.sse:
        console.print(f"[bold]启动 MCP Server[/bold]")
        console.print(f"传输协议: {transport.value}")
        console.print(f"地址: http://{host}:{port}")
        mcp_server = create_mcp_server(host=host, port=port)
        mcp_server.run(transport="sse")
    else:
        # stdio 模式：只能向 stderr 输出日志
        print("[MCP] Starting stdio mode...", file=sys.stderr)
        mcp_server = create_mcp_server()
        mcp_server.run(transport="stdio")


@app.command("list")
def list_regulations():
    """列出所有已入库的规程"""
    tools = get_tools()
    regulations = tools.list_regulations()

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
            reg["reg_id"],
            reg["title"],
            str(reg["total_pages"]),
            reg["indexed_at"][:19],  # 截断毫秒
        )

    console.print(table)


@app.command("enrich-metadata")
def enrich_metadata(
    reg_id: str = typer.Argument(None, help="规程ID，不指定则需要 --all"),
    all_regs: bool = typer.Option(False, "--all", "-a", help="处理所有规程"),
    model: str = typer.Option(None, "--model", "-m", help="指定 LLM 模型"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览生成的元数据，不保存"),
):
    """自动生成规程元数据（description, keywords, scope）

    通过分析规程目录和首页内容，使用 LLM 生成描述信息。
    生成的元数据用于多规程智能检索时的规程自动选择。

    示例:
        gridcode enrich-metadata angui_2024           # 单个规程
        gridcode enrich-metadata --all                # 所有规程
        gridcode enrich-metadata angui_2024 --dry-run # 预览不保存
    """
    import json

    from rich.panel import Panel

    from regreader.services.metadata_service import (
        format_toc_for_metadata,
        generate_regulation_metadata,
    )
    from regreader.storage import PageStore

    if not reg_id and not all_regs:
        console.print("[red]错误: 必须指定规程ID 或使用 --all 选项[/red]")
        raise typer.Exit(1)

    page_store = PageStore()

    # 确定要处理的规程
    if all_regs:
        regulations = page_store.list_regulations()
        if not regulations:
            console.print("[yellow]暂无入库的规程[/yellow]")
            return
        reg_ids = [r.reg_id for r in regulations]
        console.print(f"[dim]将处理 {len(reg_ids)} 个规程[/dim]\n")
    else:
        if not page_store.exists(reg_id):
            console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
            raise typer.Exit(1)
        reg_ids = [reg_id]

    for rid in reg_ids:
        console.print(f"[bold]处理规程: {rid}[/bold]")

        try:
            # 1. 获取 TOC
            toc = page_store.load_toc(rid)
            toc_items = toc.model_dump().get("items", [])
            toc_text = format_toc_for_metadata(toc_items)

            # 2. 读取前几页内容
            first_pages_content = []
            for page_num in range(1, min(6, toc.total_pages + 1)):
                try:
                    page = page_store.load_page(rid, page_num)
                    first_pages_content.append(f"## 第 {page_num} 页\n{page.content_markdown}")
                except Exception:
                    continue
            first_pages_text = "\n\n".join(first_pages_content)

            # 3. 调用 LLM 生成元数据
            with console.status(f"调用 LLM 生成元数据..."):
                metadata = generate_regulation_metadata(
                    toc_text,
                    first_pages_text,
                    model=model,
                )

            # 4. 显示生成的元数据
            console.print(Panel(
                f"[bold]title:[/bold] {metadata['title']}\n\n"
                f"[bold]description:[/bold] {metadata['description']}\n\n"
                f"[bold]keywords:[/bold] {', '.join(metadata['keywords'])}\n\n"
                f"[bold]scope:[/bold] {metadata['scope']}",
                title=f"[green]生成的元数据[/green]",
                border_style="green",
            ))

            # 5. 保存元数据
            if dry_run:
                console.print(f"[yellow]--dry-run 模式，未保存[/yellow]")
            else:
                page_store.update_info(
                    rid,
                    title=metadata["title"],
                    description=metadata["description"],
                    keywords=metadata["keywords"],
                    scope=metadata["scope"],
                )
                console.print(f"[green]✓ {rid} 元数据已更新[/green]")

        except Exception as e:
            console.print(f"[red]✗ {rid} 处理失败: {e}[/red]")
            if not all_regs:
                raise typer.Exit(1)

        console.print()

    if not dry_run:
        console.print(f"[bold green]完成! 共处理 {len(reg_ids)} 个规程[/bold green]")


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索查询"),
    reg_id: list[str] = typer.Option(
        None, "--reg-id", "-r", help="限定规程（可多次指定，如 -r angui_2024 -r wengui_2024）"
    ),
    all_regs: bool = typer.Option(False, "--all", "-a", help="搜索所有规程"),
    chapter: str = typer.Option(None, "--chapter", "-c", help="限定章节"),
    limit: int = typer.Option(10, "--limit", "-l", help="结果数量"),
    block_types: str = typer.Option(None, "--types", "-T", help="限定块类型（逗号分隔，如 text,table）"),
    section_number: str = typer.Option(None, "--section", "-s", help="精确匹配章节号（如 2.1.4.1.6）"),
):
    """测试检索功能

    支持多种检索模式：
    - 智能选择：不指定 -r 且不指定 --all，根据查询关键词匹配规程元数据自动选择
    - 单规程：-r angui_2024
    - 多规程：-r angui_2024 -r wengui_2024
    - 全规程：--all 或 -a
    """
    # 解析块类型参数
    block_type_list = None
    if block_types:
        block_type_list = [t.strip() for t in block_types.split(",")]

    tools = get_tools()

    # 确定搜索的规程范围
    if all_regs:
        # 明确搜索所有规程
        search_reg_id: str | list[str] | None = "all"
    elif reg_id:
        # 指定规程（单个或多个）
        search_reg_id = reg_id[0] if len(reg_id) == 1 else reg_id
    else:
        # 智能选择（根据查询关键词匹配规程元数据）
        search_reg_id = None

    results = tools.smart_search(
        query,
        reg_id=search_reg_id,
        chapter_scope=chapter,
        limit=limit,
        block_types=block_type_list,
        section_number=section_number,
    )

    if not results:
        console.print("[yellow]未找到相关结果[/yellow]")
        return

    console.print(f"\n[bold]找到 {len(results)} 条结果:[/bold]\n")

    # 按规程分组显示
    results_by_reg: dict[str, list] = {}
    for result in results:
        result_reg_id = result.get("reg_id", "unknown")
        if result_reg_id not in results_by_reg:
            results_by_reg[result_reg_id] = []
        results_by_reg[result_reg_id].append(result)

    # 如果只有一个规程，不分组显示
    if len(results_by_reg) == 1:
        for i, result in enumerate(results, 1):
            console.print(f"[bold cyan]{i}. {result['source']}[/bold cyan]")
            if result.get("chapter_path"):
                console.print(f"   章节: {' > '.join(result['chapter_path'])}")
            console.print(f"   相关度: {result['score']:.4f}")
            console.print(f"   {result['snippet'][:200]}...")
            console.print()
    else:
        # 多规程分组显示
        idx = 1
        for reg, reg_results in results_by_reg.items():
            console.print(f"\n[bold magenta]━━━ 规程: {reg} ({len(reg_results)} 条) ━━━[/bold magenta]\n")
            for result in reg_results:
                console.print(f"[bold cyan]{idx}. {result['source']}[/bold cyan]")
                if result.get("chapter_path"):
                    console.print(f"   章节: {' > '.join(result['chapter_path'])}")
                console.print(f"   相关度: {result['score']:.4f}")
                console.print(f"   {result['snippet'][:200]}...")
                console.print()
                idx += 1


@app.command("read-chapter")
def read_chapter(
    reg_id: str = typer.Option(..., "--reg-id", "-r", help="规程标识"),
    section: str = typer.Option(..., "--section", "-s", help="章节编号，如 '2.1.4.1.6'"),
    no_children: bool = typer.Option(False, "--no-children", help="不包含子章节内容"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出到文件"),
):
    """读取指定章节的完整内容"""
    from rich.markdown import Markdown

    from regreader.core.exceptions import ChapterNotFoundError, RegulationNotFoundError

    tools = get_tools()

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
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="限定规程（可选，默认自动识别）"),
    agent_type: AgentType = typer.Option(
        AgentType.claude, "--agent", "-a", help="Agent 类型"
    ),
    orchestrator: bool = typer.Option(
        False, "--orchestrator", "-o", help="启用 Orchestrator 模式（Subagent 架构）"
    ),
    display: str = typer.Option(
        "simple",
        "--display",
        "-d",
        help="显示模式: simple（默认）, clean（简洁）, enhanced（增强）"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="详细模式：显示完整工具参数和 DEBUG 日志"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="静默模式：只显示最终结果"
    ),
    enhanced: bool = typer.Option(
        False, "--enhanced", "-e", help="增强显示模式：历史记录 + 树状结构 + 进度条"
    ),
    display_detail: str = typer.Option(
        "auto",
        "--display-detail",
        help="返回值显示详细程度: auto（自适应，默认）, summary（摘要）, full（完整）"
    ),
):
    """与 Agent 对话（交互模式）

    使用 --orchestrator 启用 Subagent 架构模式，通过专家代理协调实现更好的任务分解。

    示例：
        gridcode chat                           # 自动识别规程
        gridcode chat -r angui_2024             # 限定在安规中查询
        gridcode chat -o                        # 使用 Orchestrator 模式
    """
    from regreader.agents.shared.callbacks import NullCallback
    from regreader.agents.shared.display import AgentStatusDisplay
    from regreader.agents.shared.enhanced_display import EnhancedAgentStatusDisplay
    from regreader.agents.shared.clean_display import CleanAgentStatusDisplay, DisplayMode
    from regreader.agents.hooks import set_status_callback
    from regreader.agents.shared.mcp_connection import MCPConnectionConfig

    async def run_chat():
        from loguru import logger

        # 构建 MCP 配置（从全局状态）
        if state.mcp_transport == "sse" and state.mcp_url:
            mcp_config = MCPConnectionConfig.sse(state.mcp_url)
        else:
            mcp_config = MCPConnectionConfig.stdio()

        # 创建状态显示回调
        if quiet:
            status_callback = NullCallback()
        elif display == "clean":
            # 简洁显示模式
            mode = DisplayMode.VERBOSE if verbose else DisplayMode.COMPACT
            status_callback = CleanAgentStatusDisplay(console, mode=mode)
        elif display == "enhanced" or enhanced:
            # 增强显示模式（兼容旧的 --enhanced 标志）
            status_callback = EnhancedAgentStatusDisplay(console, verbose=verbose, detail_mode=display_detail)
        else:
            # 默认简单显示模式
            status_callback = AgentStatusDisplay(console, verbose=verbose)

        # 默认模式下抑制 DEBUG 日志（包括初始化阶段）
        # verbose 模式下保留 DEBUG 日志用于问题排查
        handler_id = None
        if not verbose:
            logger.remove()
            handler_id = logger.add(
                lambda msg: console.print(f"[dim]{msg}[/dim]", highlight=False),
                level="WARNING",
                format="{message}",
            )

        # 创建 Agent
        if orchestrator:
            # Orchestrator 模式（Subagent 架构）
            if agent_type == AgentType.claude:
                from regreader.agents import ClaudeOrchestrator
                agent = ClaudeOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            elif agent_type == AgentType.pydantic:
                from regreader.agents import PydanticOrchestrator
                agent = PydanticOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            else:
                from regreader.agents import LangGraphOrchestrator
                agent = LangGraphOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
        else:
            # 原始 Agent 模式
            if agent_type == AgentType.claude:
                from regreader.agents import ClaudeAgent
                agent = ClaudeAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            elif agent_type == AgentType.pydantic:
                from regreader.agents import PydanticAIAgent
                agent = PydanticAIAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            else:
                from regreader.agents import LangGraphAgent
                agent = LangGraphAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)

        console.print(f"[bold]RegReader Agent ({agent.name})[/bold]")
        console.print("输入问题进行对话，输入 'exit' 退出\n")

        try:
            while True:
                try:
                    user_input = console.input("[bold green]❯ [/bold green]")
                except (KeyboardInterrupt, EOFError):
                    break

                if user_input.lower() in ("exit", "quit", "q"):
                    break

                if not user_input.strip():
                    continue

                # 使用状态显示
                from rich.markdown import Markdown
                from rich.panel import Panel

                if quiet:
                    with console.status("思考中..."):
                        response = await agent.chat(user_input)
                else:
                    async with status_callback.live_context():
                        response = await agent.chat(user_input)

                # 使用 Markdown 渲染输出
                console.print()
                console.print(Panel(
                    Markdown(response.content),
                    title="[bold blue]RegReader[/bold blue]",
                    border_style="blue",
                    padding=(1, 2),
                ))

                if response.sources:
                    console.print(f"\n[dim]来源: {', '.join(response.sources)}[/dim]")
                console.print()
        finally:
            # 确保关闭 MCP 连接
            if hasattr(agent, "close"):
                await agent.close()
            # 清理全局回调
            if agent_type == AgentType.claude:
                set_status_callback(None)
            # 恢复 logger 配置（如果尚未被 live_context 恢复）
            if handler_id is not None:
                try:
                    logger.remove(handler_id)
                except ValueError:
                    # Handler 已被 live_context 移除，无需重复操作
                    pass
                else:
                    # 仅在成功移除时才添加 DEBUG handler（避免重复添加）
                    logger.add(
                        lambda msg: console.print(msg, highlight=False),
                        level="DEBUG",
                        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                    )

        console.print("[dim]再见![/dim]")

    asyncio.run(run_chat())


@app.command()
def ask(
    query: str = typer.Argument(..., help="查询问题"),
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="限定规程（可选，默认自动识别）"),
    agent_type: AgentType = typer.Option(
        AgentType.claude, "--agent", "-a", help="Agent 类型"
    ),
    orchestrator: bool = typer.Option(
        False, "--orchestrator", "-o", help="启用 Orchestrator 模式（Subagent 架构）"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON 格式输出"),
    display: str = typer.Option(
        "simple",
        "--display",
        "-d",
        help="显示模式: simple（默认）, clean（简洁）, enhanced（增强）"
    ),
    display_detail: str = typer.Option(
        "auto",
        "--display-detail",
        help="返回值显示详细程度: auto（自适应，默认）, summary（摘要）, full（完整）"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="详细模式：显示完整工具参数和 DEBUG 日志"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="静默模式：只显示最终结果"
    ),
    enhanced: bool = typer.Option(
        False, "--enhanced", "-e", help="增强显示模式：历史记录 + 树状结构 + 进度条"
    ),
):
    """单次查询 Agent（非交互模式）

    使用 --orchestrator 启用 Subagent 架构模式，通过专家代理协调实现更好的任务分解。

    示例:
        gridcode ask "母线失压如何处理?"              # 自动识别规程
        gridcode ask "什么是安规?" -r angui_2024     # 限定在安规中查询
        gridcode ask "安全距离是多少?" -v            # 详细模式
        gridcode ask "什么是接地?" -q                # 静默模式
        gridcode ask "表6-2注1的内容" -o             # Orchestrator 模式
    """
    from regreader.agents.shared.callbacks import NullCallback
    from regreader.agents.shared.display import AgentStatusDisplay
    from regreader.agents.shared.enhanced_display import EnhancedAgentStatusDisplay
    from regreader.agents.shared.clean_display import CleanAgentStatusDisplay, DisplayMode
    from regreader.agents.hooks import set_status_callback
    from regreader.agents.shared.mcp_connection import MCPConnectionConfig

    async def run_ask():
        from loguru import logger

        # 构建 MCP 配置
        if state.mcp_transport == "sse" and state.mcp_url:
            mcp_config = MCPConnectionConfig.sse(state.mcp_url)
        else:
            mcp_config = MCPConnectionConfig.stdio()

        # 创建状态显示回调（JSON 输出时自动静默）
        if quiet or json_output:
            status_callback = NullCallback()
        elif display == "enhanced" or enhanced:
            status_callback = EnhancedAgentStatusDisplay(console, verbose=verbose, detail_mode=display_detail)
        elif display == "clean":
            status_callback = CleanAgentStatusDisplay(console, mode=DisplayMode.COMPACT, verbose=verbose)
        else:  # display == "simple" or default
            status_callback = AgentStatusDisplay(console, verbose=verbose)

        # 默认模式下抑制 DEBUG 日志（包括初始化阶段）
        # verbose 模式下保留 DEBUG 日志用于问题排查
        handler_id = None
        if not verbose:
            logger.remove()
            handler_id = logger.add(
                lambda msg: console.print(f"[dim]{msg}[/dim]", highlight=False),
                level="WARNING",
                format="{message}",
            )

        # 创建 Agent
        if orchestrator:
            # Orchestrator 模式（Subagent 架构）
            if agent_type == AgentType.claude:
                from regreader.agents import ClaudeOrchestrator
                agent = ClaudeOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            elif agent_type == AgentType.pydantic:
                from regreader.agents import PydanticOrchestrator
                agent = PydanticOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            else:
                from regreader.agents import LangGraphOrchestrator
                agent = LangGraphOrchestrator(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
        else:
            # 原始 Agent 模式
            if agent_type == AgentType.claude:
                from regreader.agents import ClaudeAgent
                agent = ClaudeAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            elif agent_type == AgentType.pydantic:
                from regreader.agents import PydanticAIAgent
                agent = PydanticAIAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)
            else:
                from regreader.agents import LangGraphAgent
                agent = LangGraphAgent(reg_id=reg_id, mcp_config=mcp_config, status_callback=status_callback)

        try:
            if not json_output:
                # 非 JSON 模式：使用状态显示
                from rich.markdown import Markdown
                from rich.panel import Panel

                if quiet:
                    with console.status("思考中..."):
                        response = await agent.chat(query)
                else:
                    async with status_callback.live_context():
                        response = await agent.chat(query)

                # 使用 Markdown 渲染最终输出，并添加视觉分隔
                console.print()  # 空行分隔
                console.print(Panel(
                    Markdown(response.content),
                    title="[bold green]回答[/bold green]",
                    border_style="green",
                    padding=(1, 2),
                ))

                if response.sources:
                    console.print(f"\n[dim]来源: {', '.join(response.sources)}[/dim]")
            else:
                # JSON 模式：静默执行
                import json

                response = await agent.chat(query)
                result = {
                    "query": query,
                    "agent": agent.name,
                    "content": response.content,
                    "sources": response.sources,
                    "tool_calls": [
                        {"name": tc.get("name"), "input": tc.get("input")}
                        for tc in response.tool_calls
                    ] if response.tool_calls else [],
                }
                console.print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            if hasattr(agent, "close"):
                await agent.close()
            # 清理全局回调
            if agent_type == AgentType.claude:
                set_status_callback(None)
            # 恢复 logger 配置（如果尚未被 live_context 恢复）
            if handler_id is not None:
                try:
                    logger.remove(handler_id)
                except ValueError:
                    # Handler 已被 live_context 移除，无需重复操作
                    pass
                else:
                    # 仅在成功移除时才添加 DEBUG handler（避免重复添加）
                    logger.add(
                        lambda msg: console.print(msg, highlight=False),
                        level="DEBUG",
                        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
                    )

    asyncio.run(run_ask())


@app.command()
def delete(
    reg_id: str = typer.Argument(..., help="要删除的规程标识"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """删除已入库的规程"""
    from regreader.index import FTSIndex, VectorIndex
    from regreader.storage import PageStore

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
    from regreader.core.exceptions import PageNotFoundError, RegulationNotFoundError
    from regreader.services.inspect import InspectService
    from regreader.services.inspect_display import InspectDisplay

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

    from regreader.core.exceptions import RegulationNotFoundError
    from regreader.storage import PageStore

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

    from regreader.core.exceptions import InvalidPageRangeError, RegulationNotFoundError

    tools = get_tools()

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

    from regreader.core.exceptions import RegulationNotFoundError

    tools = get_tools()

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
    from regreader.core.exceptions import PageNotFoundError, RegulationNotFoundError

    tools = get_tools()

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

    from regreader.core.exceptions import AnnotationNotFoundError, RegulationNotFoundError

    tools = get_tools()

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
    mode: str = typer.Option("hybrid", "--mode", "-m", help="搜索模式: keyword, semantic, hybrid"),
    limit: int = typer.Option(10, "--limit", "-l", help="结果数量"),
):
    """搜索表格（支持精确关键词和模糊语义搜索）"""
    from regreader.core.exceptions import RegulationNotFoundError

    tools = get_tools()

    try:
        results = tools.search_tables(
            query=query,
            reg_id=reg_id,
            chapter_scope=chapter,
            search_mode=mode,
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

        # 显示页码信息
        pages = table.get('pages', [table.get('page_start', 0)])
        if len(pages) == 1:
            page_str = f"P{pages[0]}"
        else:
            page_str = f"P{pages[0]}-{pages[-1]}"
        console.print(f"   位置: {reg_id} {page_str} | {table['row_count']}行 x {table['col_count']}列")

        console.print(f"   匹配类型: {table['match_type']} | 跨页: {'是' if table.get('is_cross_page') else '否'}")
        console.print(f"   相关性: {table.get('score', 0):.4f}")

        if table.get("snippet"):
            snippet = table["snippet"][:100].replace("\n", " ")
            console.print(f"   预览: {snippet}...")

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

    from regreader.core.exceptions import ReferenceResolutionError, RegulationNotFoundError

    tools = get_tools()

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
    from regreader.core.exceptions import RegulationNotFoundError

    tools = get_tools()

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

    from regreader.core.exceptions import RegulationNotFoundError, TableNotFoundError

    tools = get_tools()

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

    from regreader.core.exceptions import RegulationNotFoundError

    tools = get_tools()

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
    from regreader.core.exceptions import RegulationNotFoundError

    if not query and not block_id:
        console.print("[red]错误: 必须提供 --query 或 --block 参数[/red]")
        raise typer.Exit(1)

    tools = get_tools()

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

    from regreader.core.exceptions import ChapterNotFoundError, RegulationNotFoundError

    tools = get_tools()

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


@app.command("build-table-index")
def build_table_index(
    reg_id: str = typer.Argument(..., help="规程标识"),
    rebuild: bool = typer.Option(False, "--rebuild", "-r", help="重建索引（删除旧索引）"),
):
    """为指定规程构建表格索引（FTS5 + 向量索引）"""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from regreader.core.exceptions import RegulationNotFoundError
    from regreader.index.table_indexer import TableIndexer

    indexer = TableIndexer()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"构建表格索引: {reg_id}...", total=None)
            stats = indexer.build_index(reg_id, rebuild=rebuild)
            progress.update(task, completed=True)

        console.print(f"\n[bold green]表格索引构建完成[/bold green]\n")
        console.print(f"  规程 ID: {reg_id}")
        console.print(f"  表格总数: {stats['total_tables']}")
        console.print(f"  FTS5 索引: {stats['indexed_fts']} 条")
        console.print(f"  向量索引: {stats['indexed_vector']} 条")
        if rebuild:
            console.print(f"  模式: 重建")

    except RegulationNotFoundError:
        console.print(f"[red]错误: 规程 {reg_id} 不存在[/red]")
        raise typer.Exit(1)
    except FileNotFoundError as e:
        console.print(f"[red]错误: 表格注册表不存在[/red]")
        console.print(f"[yellow]提示: 请先使用 read-pages 或 parse 命令处理文档[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


# ==================== 工具导航命令 ====================


@app.command("mcp-tools")
def mcp_tools(
    category: str | None = typer.Option(
        None, "--category", "-c",
        help="按分类过滤: base, multi-hop, context, discovery, navigation"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="显示详细信息（含工具链）"
    ),
    list_categories: bool = typer.Option(
        False, "--list-categories",
        help="仅列出分类"
    ),
    live: bool = typer.Option(
        False, "--live", "-l",
        help="实时连接 MCP Server 获取工具列表"
    ),
    sse_url: str | None = typer.Option(
        None, "--sse",
        help="SSE 服务器 URL（默认使用 stdio 模式）"
    ),
    verify: bool = typer.Option(
        False, "--verify",
        help="验证服务完整性（对比静态元数据）"
    ),
):
    """列出 MCP 服务提供的所有工具

    显示工具分类、用途说明和工具链关系，帮助理解如何使用各工具。

    示例:
        gridcode mcp-tools                # 列出所有工具（静态元数据）
        gridcode mcp-tools -c base        # 仅显示基础工具
        gridcode mcp-tools -v             # 显示详细信息
        gridcode mcp-tools --list-categories  # 仅列出分类
        gridcode mcp-tools --live         # 连接 stdio MCP Server
        gridcode mcp-tools --live --sse http://localhost:8080/sse  # 连接 SSE 服务
        gridcode mcp-tools --live --verify  # 验证服务完整性
    """
    from regreader.mcp.tool_metadata import (
        TOOL_METADATA,
        CATEGORY_INFO,
        CATEGORY_ORDER,
        ToolCategory,
    )

    # 实时模式：连接 MCP Server
    if live:
        _mcp_tools_live(sse_url, verify, verbose)
        return

    # 仅列出分类
    if list_categories:
        console.print("\n[bold]MCP 工具分类[/bold]\n")
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("名称", style="green")
        table.add_column("工具数", justify="right")
        table.add_column("说明")

        for cat in CATEGORY_ORDER:
            cat_id = cat.value
            info = CATEGORY_INFO.get(cat_id, {})
            count = sum(1 for m in TOOL_METADATA.values() if m.category.value == cat_id)
            table.add_row(cat_id, info.get("name", ""), str(count), info.get("description", ""))

        console.print(table)
        return

    # 统计总工具数
    total_tools = len(TOOL_METADATA)

    # 按分类组织工具
    tools_by_cat: dict[str, list] = {}
    for cat in CATEGORY_ORDER:
        cat_id = cat.value
        if category and cat_id != category:
            continue
        tools = [m for m in TOOL_METADATA.values() if m.category.value == cat_id]
        if tools:
            tools.sort(key=lambda t: (t.priority, t.name))
            tools_by_cat[cat_id] = tools

    if not tools_by_cat:
        if category:
            console.print(f"[yellow]未找到分类: {category}[/yellow]")
            console.print(f"[dim]可用分类: base, multi-hop, context, discovery, navigation[/dim]")
        return

    # 显示标题
    if category:
        cat_info = CATEGORY_INFO.get(category, {})
        console.print(f"\n[bold]MCP 工具列表 - {cat_info.get('name', category)}[/bold]\n")
    else:
        console.print(f"\n[bold]MCP 工具列表 ({total_tools} 个)[/bold]\n")

    # 遍历分类
    for cat_id, tools in tools_by_cat.items():
        cat_info = CATEGORY_INFO.get(cat_id, {})
        cat_name = cat_info.get("name", cat_id)

        console.print(f"[bold cyan]{cat_name}[/bold cyan] [dim]({len(tools)})[/dim]")

        if verbose:
            # 详细模式
            for tool in tools:
                console.print(f"\n  [green]{tool.name}[/green] - {tool.brief}")
                if tool.cli_command:
                    console.print(f"    CLI: [dim]{tool.cli_command}[/dim]")
                if tool.prerequisites:
                    console.print(f"    前置: [dim]{', '.join(tool.prerequisites)}[/dim]")
                if tool.next_tools:
                    console.print(f"    后续: [dim]{', '.join(tool.next_tools)}[/dim]")
                if tool.use_cases:
                    console.print(f"    场景: [dim]{', '.join(tool.use_cases)}[/dim]")
            console.print()
        else:
            # 简明模式
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("名称", style="green", width=25)
            table.add_column("说明")
            table.add_column("CLI", style="dim")

            for tool in tools:
                table.add_row(
                    tool.name,
                    tool.brief,
                    tool.cli_command or "-",
                )

            console.print(table)
            console.print()


def _mcp_tools_live(sse_url: str | None, verify: bool, verbose: bool):
    """实时连接 MCP Server 获取工具列表"""
    from regreader.mcp.tool_metadata import TOOL_METADATA

    transport = "sse" if sse_url else "stdio"
    console.print(f"\n正在连接 MCP Server ({transport})...", style="dim")

    async def _fetch_live_tools():
        from regreader.mcp.client import RegReaderMCPClient
        async with RegReaderMCPClient(transport=transport, server_url=sse_url) as client:
            return await client.list_tools()

    try:
        tools = asyncio.run(_fetch_live_tools())
        console.print("[green]连接成功！[/green]\n")
    except Exception as e:
        error_msg = str(e)
        if transport == "sse":
            console.print(f"[red]连接失败: 无法连接到 SSE 服务器[/red]")
            console.print(f"[dim]URL: {sse_url}[/dim]")
            console.print()
            console.print("[yellow]提示: 请先启动 MCP Server:[/yellow]")
            console.print("  [dim]make serve[/dim]  或  [dim]gridcode serve --transport sse[/dim]")
        else:
            console.print(f"[red]连接失败: {error_msg}[/red]")
        return

    if verify:
        # 验证模式
        _verify_mcp_tools(tools, verbose)
    else:
        # 列出实际工具
        console.print(f"[bold]MCP Server 工具列表 ({len(tools)} 个)[/bold]\n")
        table = Table()
        table.add_column("工具名称", style="green")
        table.add_column("描述")
        table.add_column("参数数", justify="right")

        for tool in sorted(tools, key=lambda t: t["name"]):
            params = tool.get("input_schema", {}).get("properties", {})
            desc = tool.get("description", "")[:60]
            if len(tool.get("description", "")) > 60:
                desc += "..."
            table.add_row(tool["name"], desc, str(len(params)))

        console.print(table)


def _verify_mcp_tools(tools: list[dict], verbose: bool):
    """验证 MCP 服务完整性"""
    from regreader.mcp.tool_metadata import TOOL_METADATA

    expected_tools = set(TOOL_METADATA.keys())
    actual_tools_map = {t["name"]: t for t in tools}
    actual_tools = set(actual_tools_map.keys())

    # 1. 检查工具名称
    missing_tools = expected_tools - actual_tools
    extra_tools = actual_tools - expected_tools

    # 2. 检查参数签名
    param_mismatches = []
    param_matches = []
    for tool_name, meta in TOOL_METADATA.items():
        if tool_name not in actual_tools_map:
            continue
        actual_schema = actual_tools_map[tool_name].get("input_schema", {})
        actual_params = set(actual_schema.get("properties", {}).keys())
        expected_params = set(meta.expected_params.keys())

        if actual_params != expected_params:
            param_mismatches.append({
                "tool": tool_name,
                "missing": expected_params - actual_params,
                "extra": actual_params - expected_params,
            })
        else:
            param_matches.append({
                "tool": tool_name,
                "count": len(expected_params),
            })

    # 3. 输出验证报告
    console.print("[bold]MCP 服务验证报告[/bold]")
    console.print("=" * 40)
    console.print()

    # 连接状态
    console.print("✓ 服务连接: [green]成功[/green]")

    # 工具数量
    tool_count_ok = len(missing_tools) == 0
    if tool_count_ok:
        console.print(f"✓ 工具数量: [green]{len(actual_tools)}/{len(expected_tools)} (100%)[/green]")
    else:
        pct = len(actual_tools & expected_tools) / len(expected_tools) * 100
        console.print(f"✗ 工具数量: [red]{len(actual_tools & expected_tools)}/{len(expected_tools)} ({pct:.1f}%)[/red]")

    # 参数签名
    if param_mismatches:
        console.print(f"✗ 参数签名: [red]{len(param_mismatches)} 个工具参数不匹配[/red]")
    else:
        console.print("✓ 参数签名: [green]全部匹配[/green]")

    console.print()

    # 详细信息
    if verbose or missing_tools or param_mismatches:
        console.print("[bold]工具验证详情:[/bold]")

        for tool_name in sorted(expected_tools):
            meta = TOOL_METADATA[tool_name]
            if tool_name in missing_tools:
                console.print(f"  ✗ [red]{tool_name:25}[/red] - 缺失")
            elif any(m["tool"] == tool_name for m in param_mismatches):
                mismatch = next(m for m in param_mismatches if m["tool"] == tool_name)
                console.print(f"  ✗ [yellow]{tool_name:25}[/yellow] - 参数不匹配")
                if mismatch["missing"]:
                    console.print(f"      缺少: [dim]{', '.join(mismatch['missing'])}[/dim]")
                if mismatch["extra"]:
                    console.print(f"      多余: [dim]{', '.join(mismatch['extra'])}[/dim]")
            else:
                param_count = len(meta.expected_params)
                console.print(f"  ✓ [green]{tool_name:25}[/green] - 存在，参数匹配 ({param_count}/{param_count})")

        if extra_tools:
            console.print()
            console.print("[bold]额外工具 (未在元数据中定义):[/bold]")
            for tool_name in sorted(extra_tools):
                console.print(f"  ? [blue]{tool_name}[/blue]")

    console.print()

    # 最终结果
    if not missing_tools and not param_mismatches:
        console.print("验证结果: [bold green]✓ 通过[/bold green]")
    else:
        issues = []
        if missing_tools:
            issues.append(f"缺失工具: {', '.join(sorted(missing_tools))}")
        if param_mismatches:
            issues.append(f"参数不匹配: {', '.join(m['tool'] for m in param_mismatches)}")
        console.print(f"验证结果: [bold red]✗ 失败[/bold red] ({'; '.join(issues)})")


@app.command()
def version():
    """显示版本信息"""
    from regreader import __version__
    console.print(f"RegReader v{__version__}")


if __name__ == "__main__":
    app()
