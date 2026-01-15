"""增强版 CLI 显示组件单元测试"""

import pytest
from datetime import datetime
from io import StringIO
from rich.console import Console
from regreader.agents.shared.enhanced_display import (
    DisplayState,
    StepRecord,
    HistoryManager,
    HybridDisplay,
    EnhancedAgentStatusDisplay,
)


class TestStepRecord:
    """测试 StepRecord 数据类"""

    def test_step_record_creation(self):
        """测试步骤记录创建"""
        step = StepRecord(
            step_number=1,
            description="测试步骤",
            state=DisplayState.ANALYZING,
            start_time=datetime.now(),
        )
        assert step.step_number == 1
        assert step.description == "测试步骤"
        assert step.state == DisplayState.ANALYZING
        assert not step.is_completed()

    def test_step_record_completion(self):
        """测试步骤完成状态"""
        step = StepRecord(
            step_number=1,
            description="测试步骤",
            state=DisplayState.COMPLETED,
            start_time=datetime.now(),
        )
        assert step.is_completed()

    def test_get_icon(self):
        """测试获取状态图标"""
        step = StepRecord(
            step_number=1,
            description="测试",
            state=DisplayState.COMPLETED,
            start_time=datetime.now(),
        )
        assert step.get_icon() == "✓"

    def test_get_color(self):
        """测试获取状态颜色"""
        step = StepRecord(
            step_number=1,
            description="测试",
            state=DisplayState.COMPLETED,
            start_time=datetime.now(),
        )
        assert step.get_color() == "green"


class TestHistoryManager:
    """测试 HistoryManager 历史记录管理器"""

    def test_add_step(self):
        """测试添加步骤"""
        manager = HistoryManager(max_size=10)
        step = manager.add_step("测试步骤", DisplayState.ANALYZING)
        
        assert step.step_number == 1
        assert step.description == "测试步骤"
        assert step.state == DisplayState.ANALYZING

    def test_update_step(self):
        """测试更新步骤状态"""
        manager = HistoryManager(max_size=10)
        step = manager.add_step("测试步骤", DisplayState.ANALYZING)
        
        manager.update_step(step, state=DisplayState.COMPLETED, result_summary="完成")
        
        assert step.state == DisplayState.COMPLETED
        assert step.result_summary == "完成"
        assert step.end_time is not None
        assert step.duration is not None

    def test_max_size_limit(self):
        """测试历史记录大小限制"""
        manager = HistoryManager(max_size=5)
        
        # 添加 10 个步骤
        for i in range(10):
            manager.add_step(f"步骤 {i}", DisplayState.COMPLETED)
        
        # 应该只保留最后 5 个
        assert len(manager._history) == 5
        assert manager._current_step_number == 10

    def test_depth_tracking(self):
        """测试嵌套深度追踪"""
        manager = HistoryManager(max_size=10)
        
        step1 = manager.add_step("步骤 1", DisplayState.ANALYZING)
        assert step1.depth == 0
        
        manager.enter_context(step1)
        step2 = manager.add_step("步骤 2", DisplayState.ANALYZING)
        assert step2.depth == 1
        
        manager.exit_context()
        step3 = manager.add_step("步骤 3", DisplayState.ANALYZING)
        assert step3.depth == 0


class TestHybridDisplay:
    """测试 HybridDisplay 混合显示管理器"""

    def test_print_completed_step(self):
        """测试完成步骤的输出"""
        # 使用 StringIO 捕获输出（不使用颜色）
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120, legacy_windows=False)
        display = HybridDisplay(console, detail_mode="auto")

        step = StepRecord(
            step_number=1,
            description="调用 get_toc()",
            state=DisplayState.COMPLETED,
            start_time=datetime.now(),
            duration=0.5,
            result_summary="✓ 返回 15 个章节",
        )

        # 输出完成步骤
        display.print_completed_step(step)

        # 验证输出包含关键信息
        output_text = output.getvalue()
        assert "调用 get_toc()" in output_text
        assert "0.5s" in output_text
        assert "✓ 返回 15 个章节" in output_text

    def test_print_completed_step_without_result(self):
        """测试无返回值的完成步骤"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        display = HybridDisplay(console, detail_mode="auto")

        step = StepRecord(
            step_number=1,
            description="调用 smart_search(...)",
            state=DisplayState.COMPLETED,
            start_time=datetime.now(),
            duration=1.2,
            result_summary=None,  # 无返回值
        )

        display.print_completed_step(step)

        output_text = output.getvalue()
        assert "调用 smart_search(...)" in output_text
        assert "1.2s" in output_text

    def test_format_summary_auto_mode_short(self):
        """测试自适应模式 - 短内容"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        display = HybridDisplay(console, detail_mode="auto")

        short_summary = "✓ 找到 5 个结果"
        formatted = display._format_summary(short_summary)

        # 短内容应该完整显示
        assert formatted == short_summary

    def test_format_summary_auto_mode_long(self):
        """测试自适应模式 - 长内容"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        display = HybridDisplay(console, detail_mode="auto")

        long_summary = "✓ " + "x" * 150
        formatted = display._format_summary(long_summary)

        # 长内容应该被截断
        assert len(formatted) <= 103  # 100 + "..."
        assert formatted.endswith("...")

    def test_format_summary_full_mode(self):
        """测试完整模式"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        display = HybridDisplay(console, detail_mode="full")

        long_summary = "✓ " + "x" * 150
        formatted = display._format_summary(long_summary)

        # 完整模式应该显示全部内容
        assert formatted == long_summary
        assert len(formatted) > 100

    def test_format_summary_summary_mode(self):
        """测试摘要模式"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        display = HybridDisplay(console, detail_mode="summary")

        long_summary = "✓ " + "x" * 150
        formatted = display._format_summary(long_summary)

        # 摘要模式应该强制截断
        assert len(formatted) <= 103
        assert formatted.endswith("...")
