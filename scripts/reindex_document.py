#!/usr/bin/env python
"""重新索引文档脚本

用于在修复解析问题后重新索引已有文档。
"""

import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm

from regreader.config import get_settings
from regreader.index import FTSIndex, VectorIndex
from regreader.parser import DoclingParser, PageExtractor
from regreader.storage import PageStore

console = Console()
app = typer.Typer()


@app.command()
def reindex(
    source_file: Path = typer.Argument(..., help="源文档路径"),
    reg_id: str = typer.Option(None, "--reg-id", "-r", help="规程标识（默认使用文件名）"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="是否备份旧数据"),
):
    """重新索引文档

    此脚本会：
    1. 备份现有的页面数据和索引（可选）
    2. 清除旧数据
    3. 使用新的解析逻辑重新解析文档
    4. 重新构建索引

    示例:
        python scripts/reindex_document.py path/to/document.pdf --reg-id angui_2024
    """
    settings = get_settings()

    # 确定规程ID
    if reg_id is None:
        reg_id = source_file.stem
        console.print(f"[yellow]未指定 reg_id，使用文件名: {reg_id}[/yellow]")

    # 检查源文件
    if not source_file.exists():
        console.print(f"[red]✗ 错误: 源文件不存在: {source_file}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]重新索引文档[/bold]")
    console.print(f"源文件: {source_file}")
    console.print(f"规程ID: {reg_id}")

    # 检查是否已有数据
    pages_dir = settings.pages_dir / reg_id
    has_existing_data = pages_dir.exists()

    if has_existing_data:
        console.print(f"\n[yellow]⚠ 发现现有数据: {pages_dir}[/yellow]")

        # 确认是否继续
        if not Confirm.ask("是否继续？这将删除现有数据并重新索引", default=False):
            console.print("[yellow]已取消[/yellow]")
            raise typer.Exit(0)

        # 备份
        if backup:
            backup_dir = settings.data_dir / "backups" / f"{reg_id}_backup"
            backup_dir.parent.mkdir(parents=True, exist_ok=True)

            console.print(f"\n[cyan]备份现有数据到: {backup_dir}[/cyan]")
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(pages_dir, backup_dir)
            console.print("[green]✓ 备份完成[/green]")

        # 删除旧数据
        console.print(f"\n[cyan]删除旧数据...[/cyan]")
        shutil.rmtree(pages_dir)

    # 清除索引中的旧数据
    console.print(f"[cyan]清除索引中的旧数据...[/cyan]")
    fts_index = FTSIndex()
    vector_index = VectorIndex()

    # FTS5 清除
    try:
        import sqlite3
        conn = sqlite3.connect(str(settings.fts_db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM page_meta WHERE reg_id = ?", (reg_id,))
        # 同步到 FTS 虚拟表
        cursor.execute(
            "DELETE FROM page_index WHERE rowid IN (SELECT id FROM page_meta WHERE reg_id = ?)",
            (reg_id,)
        )
        conn.commit()
        conn.close()
        console.print("[green]✓ FTS5 索引已清除[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ 清除 FTS5 索引失败: {e}[/yellow]")

    # LanceDB 清除
    try:
        import lancedb
        db = lancedb.connect(str(settings.lancedb_path))
        table = db.open_table("page_vectors")

        # 删除指定 reg_id 的记录
        import pandas as pd
        df = table.to_pandas()
        df_filtered = df[df["reg_id"] != reg_id]

        # 重新创建表
        if len(df_filtered) > 0:
            db.create_table("page_vectors", df_filtered, mode="overwrite")
        else:
            # 如果没有剩余数据，删除表
            table_path = settings.lancedb_path / "page_vectors.lance"
            if table_path.exists():
                shutil.rmtree(table_path)

        console.print("[green]✓ LanceDB 索引已清除[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ 清除 LanceDB 索引失败: {e}[/yellow]")

    # 开始重新解析
    console.print(f"\n[bold cyan]开始重新解析...[/bold cyan]")

    parser = DoclingParser()
    page_store = PageStore()

    with console.status("解析文档..."):
        result = parser.parse(source_file)

    with console.status("提取页面..."):
        extractor = PageExtractor(reg_id)
        # 两阶段解析：先提取文档结构，再提取页面
        doc_structure = extractor.extract_document_structure(result)
        pages = extractor.extract_pages(result, doc_structure)
        toc = extractor.extract_toc(result)

    console.print(f"[green]✓ 提取完成: {len(pages)} 页[/green]")

    # 检查标题识别效果
    heading_count = sum(
        1 for page in pages
        for block in page.content_blocks
        if block.block_type == "heading"
    )
    pages_with_chapters = sum(1 for page in pages if page.chapter_path)

    console.print(f"\n[cyan]标题识别统计:[/cyan]")
    console.print(f"  识别到的标题数量: {heading_count}")
    console.print(f"  有章节信息的页面: {pages_with_chapters}/{len(pages)}")

    console.print(f"\n[cyan]文档结构:[/cyan]")
    console.print(f"  章节总数: {len(doc_structure.all_nodes)}")
    console.print(f"  顶级章节: {len(doc_structure.root_node_ids)}")

    with console.status("保存页面..."):
        page_store.save_pages(pages, toc, doc_structure, source_file.name)

    console.print("[green]✓ 页面已保存[/green]")

    with console.status("构建 FTS 索引..."):
        fts_index.index_pages(pages, doc_structure)

    console.print("[green]✓ FTS 索引已构建[/green]")

    with console.status("构建向量索引..."):
        vector_index.index_pages(pages, doc_structure)

    console.print("[green]✓ 向量索引已构建[/green]")

    console.print(f"\n[bold green]✓ 重新索引完成！[/bold green]")
    console.print(f"\n运行以下命令验证修复效果：")
    console.print(f"  python src/grid_code/cli.py inspect {reg_id} 13")


if __name__ == "__main__":
    app()
