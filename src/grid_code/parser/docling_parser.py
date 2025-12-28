"""Docling 文档解析器

封装 Docling 库，实现 PDF/DOCX → 结构化数据的转换。
基于 Docling 官方文档最佳实践实现，支持完整的 Pipeline 配置。

参考：https://docling-project.github.io/docling/examples/custom_convert/
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
    RapidOcrOptions,
)

from docling.document_converter import DocumentConverter, PdfFormatOption
from loguru import logger

from grid_code.exceptions import ParserError


class DoclingParserConfig:
    """Docling 解析器配置"""

    def __init__(
        self,
        # OCR 配置
        do_ocr: bool = True,
        ocr_options = RapidOcrOptions(),
        ocr_lang: list[str] | None = None,
        force_full_page_ocr: bool = False,
        # 表格配置
        do_table_structure: bool = True,
        table_mode: str = "accurate",  # "accurate" or "fast"
        do_cell_matching: bool = False,
        # 图片配置
        do_picture_classification: bool = False,
        do_picture_description: bool = False,
        generate_page_images: bool = False,
        images_scale: float = 1.0,
        # 公式和代码
        do_formula_enrichment: bool = False,
        do_code_enrichment: bool = False,
        # 设备配置
        accelerator_device: str = "auto",  # "auto", "cpu", "cuda", "mps"
        num_threads: int = 4,
        # 其他配置
        document_timeout: int | None = None,
        max_num_pages: int | None = None,
        max_file_size: int | None = None,
    ):
        self.do_ocr = do_ocr
        self.ocr_options = ocr_options
        self.ocr_lang = ocr_lang or ["ch_sim", "en"]
        self.force_full_page_ocr = force_full_page_ocr

        self.do_table_structure = do_table_structure
        self.table_mode = table_mode
        self.do_cell_matching = do_cell_matching

        self.do_picture_classification = do_picture_classification
        self.do_picture_description = do_picture_description
        self.generate_page_images = generate_page_images
        self.images_scale = images_scale

        self.do_formula_enrichment = do_formula_enrichment
        self.do_code_enrichment = do_code_enrichment

        self.accelerator_device = accelerator_device
        self.num_threads = num_threads

        self.document_timeout = document_timeout
        self.max_num_pages = max_num_pages
        self.max_file_size = max_file_size


class DoclingParser:
    """Docling 文档解析器

    基于 Docling 官方最佳实践实现，支持：
    - 完整的 PipelineOptions 配置
    - 表格结构识别配置
    - OCR 配置
    - 设备加速器配置
    - 批量文档转换
    """

    def __init__(self, config: DoclingParserConfig | None = None):
        """初始化解析器

        Args:
            config: 解析器配置，如果为 None 则使用默认配置
        """
        self.config = config or DoclingParserConfig()
        self._converter: DocumentConverter | None = None
        self._pipeline_options: PdfPipelineOptions | None = None

    def _build_pipeline_options(self) -> PdfPipelineOptions:
        """构建 PDF Pipeline 选项"""
        if self._pipeline_options is not None:
            return self._pipeline_options

        # 设备加速器配置
        device_map = {
            "auto": AcceleratorDevice.AUTO,
            "cpu": AcceleratorDevice.CPU,
            "cuda": AcceleratorDevice.CUDA,
            "mps": AcceleratorDevice.MPS,
        }
        accelerator_options = AcceleratorOptions(
            device=device_map.get(self.config.accelerator_device, AcceleratorDevice.AUTO),
            num_threads=self.config.num_threads,
        )

        # 表格结构配置
        table_mode_map = {
            "accurate": TableFormerMode.ACCURATE,
            "fast": TableFormerMode.FAST,
        }
        table_structure_options = TableStructureOptions(
            mode=table_mode_map.get(self.config.table_mode, TableFormerMode.ACCURATE),
            do_cell_matching=self.config.do_cell_matching,
            do_table_structure=self.config.do_table_structure,
        )

        # 构建 Pipeline 选项
        pipeline_options = PdfPipelineOptions(
            # OCR
            do_ocr=self.config.do_ocr,
            # 表格
            do_table_structure=self.config.do_table_structure,
            table_structure_options=table_structure_options,
            # 图片
            do_picture_classification=self.config.do_picture_classification,
            do_picture_description=self.config.do_picture_description,
            generate_page_images=self.config.generate_page_images,
            images_scale=self.config.images_scale,
            # 公式和代码
            do_formula_enrichment=self.config.do_formula_enrichment,
            do_code_enrichment=self.config.do_code_enrichment,
            # 加速器
            accelerator_options=accelerator_options,
        )

        # 设置文档超时（如果指定）
        if self.config.document_timeout is not None:
            pipeline_options.document_timeout = self.config.document_timeout

        if self.config.ocr_options is not None:
            pipeline_options.ocr_options = self.config.ocr_options

        self._pipeline_options = pipeline_options
        return pipeline_options

    def _build_format_options(self) -> dict[InputFormat, PdfFormatOption]:
        """构建格式选项映射"""
        pipeline_options = self._build_pipeline_options()

        return {
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }

    @property
    def converter(self) -> DocumentConverter:
        """延迟初始化 DocumentConverter"""
        if self._converter is None:
            logger.info("初始化 Docling DocumentConverter...")
            logger.debug(f"OCR 启用: {self.config.do_ocr}")
            logger.debug(f"表格识别启用: {self.config.do_table_structure}")
            logger.debug(f"表格模式: {self.config.table_mode}")
            logger.debug(f"加速设备: {self.config.accelerator_device}")

            # FIXME:
            format_options = self._build_format_options()
            # format_options = None

            self._converter = DocumentConverter(
                allowed_formats=[
                    InputFormat.PDF,
                    InputFormat.DOCX,
                    InputFormat.PPTX,
                    InputFormat.XLSX,
                    InputFormat.HTML,
                    InputFormat.MD,
                ],
                format_options=format_options,
            )
            logger.info("DocumentConverter 初始化完成")
        return self._converter

    def initialize_pipeline(self, input_format: InputFormat = InputFormat.PDF) -> None:
        """预初始化 Pipeline

        在处理文档之前调用此方法可以预加载模型，避免首次转换时的延迟。

        Args:
            input_format: 要初始化的输入格式
        """
        logger.info(f"预初始化 {input_format} Pipeline...")
        self.converter.initialize_pipeline(input_format)
        logger.info("Pipeline 预初始化完成")

    def parse(
        self,
        file_path: str | Path,
        max_num_pages: int | None = None,
        max_file_size: int | None = None,
    ) -> ConversionResult:
        """解析文档文件

        Args:
            file_path: 文档文件路径（支持 PDF, DOCX, PPTX, XLSX, HTML）
            max_num_pages: 最大页数限制（覆盖配置）
            max_file_size: 最大文件大小限制（覆盖配置）

        Returns:
            Docling ConversionResult 对象

        Raises:
            ParserError: 文件不存在或解析失败
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise ParserError(f"文件不存在: {file_path}")

        logger.info(f"开始解析文档: {file_path.name}")

        # 确定页数和大小限制
        max_pages = max_num_pages or self.config.max_num_pages
        max_size = max_file_size or self.config.max_file_size

        try:
            # 构建转换参数
            convert_kwargs: dict[str, Any] = {
                "source": str(file_path),
                "raises_on_error": True,
            }
            if max_pages is not None:
                convert_kwargs["max_num_pages"] = max_pages
            if max_size is not None:
                convert_kwargs["max_file_size"] = max_size

            result = self.converter.convert(**convert_kwargs)
            logger.info(f"文档解析完成: {file_path.name}")
            return result
        except Exception as e:
            raise ParserError(f"文档解析失败: {file_path.name} - {e}") from e

    def parse_batch(
        self,
        file_paths: list[str | Path],
        max_num_pages: int | None = None,
        max_file_size: int | None = None,
        raises_on_error: bool = False,
    ) -> Iterator[ConversionResult]:
        """批量解析多个文档

        使用 Docling 的 convert_all 方法进行高效批量处理。

        Args:
            file_paths: 文档文件路径列表
            max_num_pages: 最大页数限制
            max_file_size: 最大文件大小限制
            raises_on_error: 是否在单个文档失败时抛出异常

        Yields:
            每个文档的 ConversionResult

        Raises:
            ParserError: 如果 raises_on_error=True 且某个文档解析失败
        """
        # 验证文件存在性
        sources = []
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                if raises_on_error:
                    raise ParserError(f"文件不存在: {path}")
                logger.warning(f"跳过不存在的文件: {path}")
                continue
            sources.append(str(path))

        if not sources:
            logger.warning("没有有效的文件需要处理")
            return

        logger.info(f"开始批量解析 {len(sources)} 个文档...")

        # 确定页数和大小限制
        max_pages = max_num_pages or self.config.max_num_pages
        max_size = max_file_size or self.config.max_file_size

        try:
            # 构建转换参数
            convert_kwargs: dict[str, Any] = {
                "source": sources,
                "raises_on_error": raises_on_error,
            }
            if max_pages is not None:
                convert_kwargs["max_num_pages"] = max_pages
            if max_size is not None:
                convert_kwargs["max_file_size"] = max_size

            for result in self.converter.convert_all(**convert_kwargs):
                logger.debug(f"完成解析: {result.input.file}")
                yield result

            logger.info("批量解析完成")
        except Exception as e:
            raise ParserError(f"批量解析失败: {e}") from e

    def parse_to_markdown(self, file_path: str | Path) -> str:
        """解析文档并导出为 Markdown

        Args:
            file_path: 文档文件路径

        Returns:
            Markdown 格式的文档内容
        """
        result = self.parse(file_path)
        return result.document.export_to_markdown()

    def parse_to_dict(self, file_path: str | Path) -> dict[str, Any]:
        """解析文档并导出为字典

        Args:
            file_path: 文档文件路径

        Returns:
            文档的结构化字典表示
        """
        result = self.parse(file_path)
        return result.document.export_to_dict()

    def get_page_count(self, result: ConversionResult) -> int:
        """获取文档总页数

        Args:
            result: Docling 解析结果

        Returns:
            文档总页数
        """
        doc = result.document

        # 优先从 pages 属性获取
        if hasattr(doc, "pages") and doc.pages:
            return len(doc.pages)

        # 从 provenance 中提取最大页码
        max_page = 0

        # 检查文本内容
        if hasattr(doc, "texts"):
            for item in doc.texts:
                if hasattr(item, "prov") and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, "page_no") and prov.page_no:
                            max_page = max(max_page, prov.page_no)

        # 检查表格
        if hasattr(doc, "tables"):
            for item in doc.tables:
                if hasattr(item, "prov") and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, "page_no") and prov.page_no:
                            max_page = max(max_page, prov.page_no)

        # 检查图片
        if hasattr(doc, "pictures"):
            for item in doc.pictures:
                if hasattr(item, "prov") and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, "page_no") and prov.page_no:
                            max_page = max(max_page, prov.page_no)

        return max_page

    def reset(self) -> None:
        """重置解析器状态

        清除已初始化的 converter 和 pipeline options，
        下次调用时会重新创建。
        """
        self._converter = None
        self._pipeline_options = None
        logger.debug("解析器状态已重置")


def create_parser_for_chinese_pdf(use_gpu: bool = False) -> DoclingParser:
    """创建适合中文 PDF 的解析器

    预配置了中文 OCR 和优化的表格识别。

    Args:
        use_gpu: 是否使用 GPU 加速

    Returns:
        配置好的 DoclingParser 实例
    """
    config = DoclingParserConfig(
        do_ocr=True,
        ocr_lang=["ch_sim", "en"],
        do_table_structure=True,
        table_mode="accurate",
        do_cell_matching=True,
        accelerator_device="cuda" if use_gpu else "cpu",
        num_threads=4,
    )
    return DoclingParser(config)


def create_fast_parser() -> DoclingParser:
    """创建快速解析器

    牺牲一些精度以换取更快的处理速度。

    Returns:
        配置好的 DoclingParser 实例
    """
    config = DoclingParserConfig(
        do_ocr=False,  # 禁用 OCR 以加速
        do_table_structure=True,
        table_mode="fast",  # 使用快速表格模式
        do_cell_matching=False,
        accelerator_device="auto",
        num_threads=8,  # 更多线程
    )
    return DoclingParser(config)
