"""GridCode 自定义异常类"""


class GridCodeError(Exception):
    """GridCode 基础异常类"""

    pass


class ParserError(GridCodeError):
    """文档解析错误"""

    pass


class StorageError(GridCodeError):
    """存储操作错误"""

    pass


class IndexError(GridCodeError):
    """索引操作错误"""

    pass


class RegulationNotFoundError(GridCodeError):
    """规程不存在错误"""

    def __init__(self, reg_id: str):
        self.reg_id = reg_id
        super().__init__(f"规程 '{reg_id}' 不存在")


class PageNotFoundError(GridCodeError):
    """页面不存在错误"""

    def __init__(self, reg_id: str, page_num: int):
        self.reg_id = reg_id
        self.page_num = page_num
        super().__init__(f"规程 '{reg_id}' 的页面 {page_num} 不存在")


class InvalidPageRangeError(GridCodeError):
    """无效的页码范围"""

    def __init__(self, start_page: int, end_page: int):
        self.start_page = start_page
        self.end_page = end_page
        super().__init__(f"无效的页码范围: {start_page} - {end_page}")
