"""查询提示提取器

从用户查询中提取结构化提示信息（hints），供框架和子智能体使用。
不再进行路由决策 - 子智能体选择由框架的 LLM 自主完成。
"""

import re
from typing import Any


class QueryAnalyzer:
    """查询提示提取器

    从用户查询中提取有用的结构化提示信息：
    - chapter_scope: 章节范围（如「第六章」）
    - table_hint: 表格标识（如「表6-2」）
    - annotation_hint: 注释标识（如「注1」）
    - scheme_hint: 方案标识（如「方案A」）
    - reference_text: 引用文本（如「见第六章」）
    - section_number: 章节编号（如「2.1.4」）
    - reg_id: 规程标识（如果明确提到）

    这些提示将传递给子智能体，帮助它们更好地理解查询意图。

    注意：
    - 本类不再负责路由决策（不返回 QueryIntent）
    - 子智能体选择由框架（Claude SDK/Pydantic AI/LangGraph）的 LLM 自主完成
    - 子智能体通过配置中的 description 字段被 LLM 理解和选择
    """

    def __init__(self):
        """初始化提取器"""
        self._hint_patterns = self._build_hint_patterns()

    def _build_hint_patterns(self) -> dict[str, re.Pattern]:
        """构建提示信息提取模式

        Returns:
            提示类型到正则模式的映射
        """
        return {
            # 章节范围：「第六章」「第6章」
            "chapter_scope": re.compile(r"第([一二三四五六七八九十\d]+)章"),
            # 表格标识：「表6-2」「表 6-2」
            "table_hint": re.compile(r"表\s*(\d+[-]?\d*)"),
            # 注释标识：「注1」「注①」「注一」
            "annotation_hint": re.compile(
                r"注\s*([0-9一二三四五六七八九十①②③④⑤⑥⑦⑧⑨⑩]+)"
            ),
            # 方案标识：「方案A」「方案甲」
            "scheme_hint": re.compile(r"方案\s*([A-Za-z甲乙丙丁戊己庚辛壬癸]+)"),
            # 引用文本：「见第六章」「参见表6-2」
            "reference_text": re.compile(
                r"(见|参见|参照|详见)\s*(第.+章|表.+|附录.+|第.+条)"
            ),
            # 章节编号：「2.1.4」「2.1.4.1.6」
            "section_number": re.compile(r"\b(\d+(?:\.\d+){2,})\b"),
            # 规程关键词
            "reg_hint_angui": re.compile(r"安规|安全自动|安控|稳控"),
            "reg_hint_wengui": re.compile(r"稳规|稳定装置|频率电压"),
        }

    async def extract_hints(self, query: str) -> dict[str, Any]:
        """提取查询中的提示信息（异步版本）

        Args:
            query: 用户查询

        Returns:
            提示信息字典，可能包含：
            - chapter_scope: 章节范围（str）
            - table_hint: 表格标识（str）
            - annotation_hint: 注释标识（str）
            - scheme_hint: 方案标识（str）
            - reference_text: 引用文本（str）
            - section_number: 章节编号（str）
            - reg_id: 规程标识（str，如 'angui_2024'）
        """
        return self._extract_hints_sync(query)

    def extract_hints_sync(self, query: str) -> dict[str, Any]:
        """提取查询中的提示信息（同步版本）

        Args:
            query: 用户查询

        Returns:
            提示信息字典
        """
        return self._extract_hints_sync(query)

    def _extract_hints_sync(self, query: str) -> dict[str, Any]:
        """提取提示信息的内部实现

        Args:
            query: 用户查询

        Returns:
            提示信息字典
        """
        hints = {}

        # 提取章节范围
        match = self._hint_patterns["chapter_scope"].search(query)
        if match:
            hints["chapter_scope"] = match.group(0)

        # 提取表格标识
        match = self._hint_patterns["table_hint"].search(query)
        if match:
            hints["table_hint"] = match.group(0)

        # 提取注释标识
        match = self._hint_patterns["annotation_hint"].search(query)
        if match:
            hints["annotation_hint"] = match.group(0)

        # 提取方案标识
        match = self._hint_patterns["scheme_hint"].search(query)
        if match:
            hints["scheme_hint"] = match.group(0)

        # 提取引用文本
        match = self._hint_patterns["reference_text"].search(query)
        if match:
            hints["reference_text"] = match.group(0)

        # 提取章节编号
        match = self._hint_patterns["section_number"].search(query)
        if match:
            hints["section_number"] = match.group(1)

        # 推断规程
        if self._hint_patterns["reg_hint_angui"].search(query):
            hints["reg_id"] = "angui_2024"
        elif self._hint_patterns["reg_hint_wengui"].search(query):
            hints["reg_id"] = "wengui_2024"

        return hints
