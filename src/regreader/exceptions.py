"""RegReader 自定义异常类"""


class RegReaderError(Exception):
    """RegReader 基础异常类"""

    pass


class ParserError(RegReaderError):
    """文档解析错误"""

    pass


class StorageError(RegReaderError):
    """存储操作错误"""

    pass


class IndexError(RegReaderError):
    """索引操作错误"""

    pass


class RegulationNotFoundError(RegReaderError):
    """规程不存在错误"""

    def __init__(self, reg_id: str):
        self.reg_id = reg_id
        super().__init__(f"规程 '{reg_id}' 不存在")


class PageNotFoundError(RegReaderError):
    """页面不存在错误"""

    def __init__(self, reg_id: str, page_num: int):
        self.reg_id = reg_id
        self.page_num = page_num
        super().__init__(f"规程 '{reg_id}' 的页面 {page_num} 不存在")


class InvalidPageRangeError(RegReaderError):
    """无效的页码范围"""

    def __init__(self, start_page: int, end_page: int):
        self.start_page = start_page
        self.end_page = end_page
        super().__init__(f"无效的页码范围: {start_page} - {end_page}")


class ChapterNotFoundError(RegReaderError):
    """章节不存在错误"""

    def __init__(self, reg_id: str, section_number: str):
        self.reg_id = reg_id
        self.section_number = section_number
        super().__init__(f"规程 '{reg_id}' 的章节 '{section_number}' 不存在")


class AnnotationNotFoundError(RegReaderError):
    """注释不存在错误"""

    def __init__(self, reg_id: str, annotation_id: str):
        self.reg_id = reg_id
        self.annotation_id = annotation_id
        super().__init__(f"规程 '{reg_id}' 中未找到注释 '{annotation_id}'")


class TableNotFoundError(RegReaderError):
    """表格不存在错误"""

    def __init__(self, reg_id: str, table_id: str):
        self.reg_id = reg_id
        self.table_id = table_id
        super().__init__(f"规程 '{reg_id}' 中未找到表格 '{table_id}'")


class ReferenceResolutionError(RegReaderError):
    """交叉引用解析错误"""

    def __init__(self, reference_text: str, reason: str):
        self.reference_text = reference_text
        self.reason = reason
        super().__init__(f"无法解析引用 '{reference_text}': {reason}")
