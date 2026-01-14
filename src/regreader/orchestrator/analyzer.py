"""查询意图分析器

分析用户查询，确定应该调用哪些 Subagent。
"""

import re
from dataclasses import dataclass, field
from typing import Any

from regreader.subagents.config import (
    SUBAGENT_CONFIGS,
    SubagentConfig,
    SubagentType,
    get_enabled_configs,
)


@dataclass
class QueryIntent:
    """查询意图分析结果

    Attributes:
        primary_type: 主要 Subagent 类型
        secondary_types: 次要 Subagent 类型列表
        confidence: 置信度
        hints: 提取的提示信息
        requires_multi_hop: 是否需要多跳推理
    """

    primary_type: SubagentType
    """主要 Subagent 类型"""

    secondary_types: list[SubagentType] = field(default_factory=list)
    """次要 Subagent 类型（复杂查询可能需要多个）"""

    confidence: float = 1.0
    """置信度（0.0-1.0）"""

    hints: dict[str, Any] = field(default_factory=dict)
    """提取的提示信息

    可能包含：
    - chapter_scope: 章节范围（如「第六章」）
    - table_hint: 表格标识（如「表6-2」）
    - annotation_hint: 注释标识（如「注1」）
    - reference_text: 引用文本（如「见第六章」）
    - reg_id: 规程标识（如果明确提到）
    """

    requires_multi_hop: bool = False
    """是否需要多跳推理"""

    @property
    def all_types(self) -> list[SubagentType]:
        """所有需要调用的 Subagent 类型"""
        return [self.primary_type] + self.secondary_types

    @property
    def is_multi_agent(self) -> bool:
        """是否需要多个 Subagent"""
        return len(self.secondary_types) > 0


class QueryAnalyzer:
    """查询意图分析器

    分析用户查询，确定：
    1. 应该调用哪个（或哪些）Subagent
    2. 提取有用的提示信息（章节、表格、注释等）
    3. 判断是否需要多跳推理

    使用规则匹配 + 关键词评分的方式进行分析。
    """

    def __init__(self):
        """初始化分析器"""
        self._configs = get_enabled_configs()
        self._keyword_patterns = self._build_keyword_patterns()
        self._hint_patterns = self._build_hint_patterns()

    def _build_keyword_patterns(self) -> dict[SubagentType, list[re.Pattern]]:
        """构建关键词正则模式

        Returns:
            类型到模式列表的映射
        """
        patterns = {}
        for config in self._configs:
            patterns[config.agent_type] = [
                re.compile(kw, re.IGNORECASE) for kw in config.keywords
            ]
        return patterns

    def _build_hint_patterns(self) -> dict[str, re.Pattern]:
        """构建提示信息提取模式

        Returns:
            提示类型到模式的映射
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

    async def analyze(self, query: str) -> QueryIntent:
        """分析查询意图

        Args:
            query: 用户查询

        Returns:
            QueryIntent 分析结果
        """
        # 1. 提取提示信息
        hints = self._extract_hints(query)

        # 2. 关键词评分
        scores = self._keyword_score(query)

        # 3. 规则调整
        scores = self._apply_rules(query, scores, hints)

        # 4. 确定主次 Subagent
        return self._determine_intent(scores, hints)

    def _extract_hints(self, query: str) -> dict[str, Any]:
        """提取提示信息

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

    def _keyword_score(self, query: str) -> dict[SubagentType, float]:
        """计算关键词匹配得分

        Args:
            query: 用户查询

        Returns:
            类型到得分的映射
        """
        scores = {agent_type: 0.0 for agent_type in self._keyword_patterns}

        for agent_type, patterns in self._keyword_patterns.items():
            for pattern in patterns:
                if pattern.search(query):
                    scores[agent_type] += 0.25
            # 限制最大得分
            scores[agent_type] = min(scores[agent_type], 1.0)

        return scores

    def _apply_rules(
        self,
        query: str,
        scores: dict[SubagentType, float],
        hints: dict[str, Any],
    ) -> dict[SubagentType, float]:
        """应用规则调整得分

        Args:
            query: 用户查询
            scores: 当前得分
            hints: 提取的提示

        Returns:
            调整后的得分
        """
        # 规则1：明确提到表格 → TableAgent 加分
        if hints.get("table_hint"):
            scores[SubagentType.TABLE] += 0.5

        # 规则2：明确提到注释 → TableAgent 或 ReferenceAgent 加分
        if hints.get("annotation_hint") or hints.get("scheme_hint"):
            scores[SubagentType.TABLE] += 0.3
            scores[SubagentType.REFERENCE] += 0.2

        # 规则3：明确提到引用 → ReferenceAgent 加分
        if hints.get("reference_text"):
            scores[SubagentType.REFERENCE] += 0.5

        # 规则4：比较/相似类查询 → DiscoveryAgent 加分
        if SubagentType.DISCOVERY in scores:
            compare_keywords = ["比较", "区别", "差异", "相似", "类似"]
            if any(kw in query for kw in compare_keywords):
                scores[SubagentType.DISCOVERY] += 0.5

        # 限制所有得分
        return {k: min(v, 1.0) for k, v in scores.items()}

    def _determine_intent(
        self,
        scores: dict[SubagentType, float],
        hints: dict[str, Any],
    ) -> QueryIntent:
        """确定最终意图

        Args:
            scores: 各 Subagent 得分
            hints: 提取的提示

        Returns:
            QueryIntent
        """
        # 按得分排序
        sorted_agents = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        # 过滤禁用的 Subagent
        enabled_types = {c.agent_type for c in self._configs}
        sorted_agents = [
            (t, s) for t, s in sorted_agents
            if t in enabled_types
        ]

        if not sorted_agents:
            # 回退到 SearchAgent
            return QueryIntent(
                primary_type=SubagentType.SEARCH,
                confidence=0.3,
                hints=hints,
            )

        primary_type, primary_score = sorted_agents[0]

        # 判断是否需要多个 Subagent
        secondary_types = []
        requires_multi_hop = False

        if primary_score >= 0.7:
            # 高置信度 - 单一 Subagent
            pass
        elif primary_score >= 0.4:
            # 中等置信度 - 可能需要多个
            for agent_type, score in sorted_agents[1:]:
                if score >= 0.3:
                    secondary_types.append(agent_type)
            requires_multi_hop = len(secondary_types) > 0
        else:
            # 低置信度 - 默认 SearchAgent
            primary_type = SubagentType.SEARCH
            primary_score = 0.3

        # 特殊规则：表格+注释 → 同时需要 TableAgent 和 ReferenceAgent
        if (
            hints.get("table_hint")
            and hints.get("annotation_hint")
            and SubagentType.REFERENCE not in secondary_types
            and primary_type != SubagentType.REFERENCE
        ):
            secondary_types.append(SubagentType.REFERENCE)
            requires_multi_hop = True

        return QueryIntent(
            primary_type=primary_type,
            secondary_types=secondary_types,
            confidence=primary_score,
            hints=hints,
            requires_multi_hop=requires_multi_hop,
        )

    def analyze_sync(self, query: str) -> QueryIntent:
        """同步分析（用于简单场景）

        Args:
            query: 用户查询

        Returns:
            QueryIntent
        """
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self.analyze(query))
