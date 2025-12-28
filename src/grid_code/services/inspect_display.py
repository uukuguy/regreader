"""页面数据检查显示模块

使用 Rich 库美化终端输出。
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grid_code.services.inspect import DifferenceAnalysis, InspectResult


class InspectDisplay:
    """页面数据检查显示器"""

    def __init__(self):
        """初始化显示器"""
        self.console = Console()

    def display_result(self, result: InspectResult, analysis: DifferenceAnalysis) -> None:
        """显示检查结果

        Args:
            result: 检查结果
            analysis: 差异分析
        """
        # 1. 显示标题
        self._display_title(result)

        # 2. 显示原始页面数据
        self._display_page_document(result)

        # 3. 显示内容块详情
        self._display_content_blocks(result)

        # 4. 显示 FTS5 索引数据
        self._display_fts5_data(result, analysis)

        # 5. 显示 LanceDB 索引数据
        self._display_lancedb_data(result, analysis)

        # 6. 显示差异分析
        self._display_difference_analysis(analysis)

    def _display_title(self, result: InspectResult) -> None:
        """显示标题面板"""
        title_text = f"页面数据检查: {result.reg_id} P{result.page_num}"
        self.console.print(
            Panel(
                title_text,
                style="bold blue",
                padding=(1, 2),
            )
        )
        self.console.print()

    def _display_page_document(self, result: InspectResult) -> None:
        """显示原始页面数据"""
        self.console.print("📄 [bold]原始页面数据 (PageDocument)[/bold]")

        # 基本信息
        page = result.page_document
        chapter_path_str = " > ".join(page.chapter_path) if page.chapter_path else "无章节信息"

        self.console.print(f"  规程: [cyan]{page.reg_id}[/cyan]")
        self.console.print(f"  页码: [cyan]{page.page_num}[/cyan]")
        self.console.print(f"  章节: [cyan]{chapter_path_str}[/cyan]")
        self.console.print(f"  内容块数量: [cyan]{len(page.content_blocks)}[/cyan]")

        if page.continues_from_prev:
            self.console.print("  [yellow]⚠ 包含从上页延续的内容[/yellow]")
        if page.continues_to_next:
            self.console.print("  [yellow]⚠ 包含延续到下页的内容[/yellow]")

        self.console.print()

    def _display_content_blocks(self, result: InspectResult) -> None:
        """显示内容块详情表格"""
        self.console.print("📊 [bold]内容块详情[/bold]")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Block ID", min_width=15)
        table.add_column("Type", width=10)
        table.add_column("Content Preview", min_width=40)

        for i, block in enumerate(result.page_document.content_blocks, 1):
            # 内容预览（前60字符）
            content_preview = block.content_markdown.strip()[:60]
            if len(block.content_markdown.strip()) > 60:
                content_preview += "..."

            # 类型颜色
            type_color = {
                "text": "green",
                "table": "blue",
                "heading": "yellow",
                "list": "cyan",
            }.get(block.block_type, "white")

            table.add_row(
                str(i),
                block.block_id,
                f"[{type_color}]{block.block_type}[/{type_color}]",
                content_preview,
            )

        self.console.print(table)
        self.console.print()

    def _display_fts5_data(self, result: InspectResult, analysis: DifferenceAnalysis) -> None:
        """显示 FTS5 索引数据"""
        fts5_count = len(result.fts5_records)
        total_count = analysis.total_blocks

        # 标题
        if fts5_count == total_count:
            status = "[green]✓ 所有内容块均已索引[/green]"
        else:
            status = f"[yellow]⚠ {fts5_count}/{total_count} 已索引[/yellow]"

        self.console.print(f"🔍 [bold]FTS5 关键词索引[/bold] ({fts5_count} 条记录)")
        self.console.print(f"  {status}")

        if result.fts5_records:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Block ID", min_width=15)
            table.add_column("Chapter Path", min_width=20)
            table.add_column("Content Preview", min_width=40)

            for rec in result.fts5_records:
                chapter_str = " > ".join(rec.chapter_path) if rec.chapter_path else "无"
                content_preview = rec.content_preview or rec.content[:60]

                # 检查是否缺失
                is_missing = rec.block_id in analysis.missing_in_fts5
                if is_missing:
                    block_id_display = f"[red]{rec.block_id}[/red]"
                else:
                    block_id_display = rec.block_id

                table.add_row(block_id_display, chapter_str, content_preview)

            self.console.print(table)

        self.console.print()

    def _display_lancedb_data(
        self, result: InspectResult, analysis: DifferenceAnalysis
    ) -> None:
        """显示 LanceDB 向量索引数据"""
        vector_count = len(result.vector_records)
        total_count = analysis.total_blocks

        # 标题
        if vector_count == total_count:
            status = "[green]✓ 所有内容块均已索引[/green]"
        else:
            status = f"[yellow]⚠ {vector_count}/{total_count} 已索引[/yellow]"

        self.console.print(f"🧮 [bold]LanceDB 向量索引[/bold] ({vector_count} 条记录)")
        self.console.print(f"  {status}")

        if result.vector_records:
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Block ID", min_width=15)
            table.add_column("Chapter Path", min_width=20)
            table.add_column("Content Preview", min_width=40)

            for rec in result.vector_records:
                content_preview = rec.content[:60]
                if len(rec.content) > 60:
                    content_preview += "..."

                # 检查是否缺失
                is_missing = rec.block_id in analysis.missing_in_vector
                if is_missing:
                    block_id_display = f"[red]{rec.block_id}[/red]"
                else:
                    block_id_display = rec.block_id

                table.add_row(block_id_display, rec.chapter_path, content_preview)

            self.console.print(table)

        self.console.print()

    def _display_difference_analysis(self, analysis: DifferenceAnalysis) -> None:
        """显示差异分析"""
        self.console.print("⚠️  [bold]差异分析[/bold]")

        # 检查是否有差异
        has_differences = (
            analysis.missing_in_fts5
            or analysis.missing_in_vector
            or analysis.content_mismatches
        )

        if not has_differences:
            # 全部通过
            self.console.print("[green]✅ 数据一致性检查通过[/green]")
            self.console.print("  [green]- 内容块完整性: ✓[/green]")
            self.console.print("  [green]- FTS5 内容一致: ✓[/green]")
            self.console.print("  [green]- LanceDB 内容一致: ✓[/green]")
        else:
            # 显示缺失的内容块
            if analysis.missing_in_fts5:
                self.console.print(
                    f"[red]✗ FTS5 缺失内容块 ({len(analysis.missing_in_fts5)}):[/red]"
                )
                for block_id in analysis.missing_in_fts5:
                    self.console.print(f"  [red]- {block_id}[/red]")

            if analysis.missing_in_vector:
                self.console.print(
                    f"[red]✗ 向量索引缺失内容块 ({len(analysis.missing_in_vector)}):[/red]"
                )
                for block_id in analysis.missing_in_vector:
                    self.console.print(f"  [red]- {block_id}[/red]")

            # 显示内容不匹配
            if analysis.content_mismatches:
                self.console.print(
                    f"[yellow]⚠ 内容不匹配 ({len(analysis.content_mismatches)}):[/yellow]"
                )
                for mismatch in analysis.content_mismatches:
                    self.console.print(f"  [yellow]- Block ID: {mismatch['block_id']}[/yellow]")
                    self.console.print(f"    [yellow]来源: {mismatch['source']}[/yellow]")
                    self.console.print(
                        f"    [dim]PageDocument: {mismatch['page_content'][:50]}...[/dim]"
                    )
                    self.console.print(
                        f"    [dim]索引内容: {mismatch['indexed_content'][:50]}...[/dim]"
                    )

        # 显示统计信息
        self.console.print()
        self.console.print("📊 [bold]索引覆盖率[/bold]")
        self.console.print(f"  原始内容块: [cyan]{analysis.total_blocks}[/cyan]")

        fts5_percent = (
            (analysis.indexed_in_fts5 / analysis.total_blocks * 100)
            if analysis.total_blocks > 0
            else 0
        )
        vector_percent = (
            (analysis.indexed_in_vector / analysis.total_blocks * 100)
            if analysis.total_blocks > 0
            else 0
        )

        fts5_color = "green" if fts5_percent == 100 else "yellow"
        vector_color = "green" if vector_percent == 100 else "yellow"

        self.console.print(
            f"  FTS5 索引: [{fts5_color}]{analysis.indexed_in_fts5} ({fts5_percent:.1f}%)[/{fts5_color}]"
        )
        self.console.print(
            f"  LanceDB 索引: [{vector_color}]{analysis.indexed_in_vector} ({vector_percent:.1f}%)[/{vector_color}]"
        )

        self.console.print()

    def display_save_message(self, file_path: str) -> None:
        """显示保存成功消息

        Args:
            file_path: 保存的文件路径
        """
        self.console.print(f"💾 [green]数据已保存至:[/green] [cyan]{file_path}[/cyan]")
        self.console.print()
