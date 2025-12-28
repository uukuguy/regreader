"""测试标题检测功能"""

from grid_code.parser.page_extractor import PageExtractor


def test_detect_heading_from_text():
    """测试智能标题识别"""
    extractor = PageExtractor("test")

    # 测试用例: (文本, 期望的级别)
    test_cases = [
        # 数字编号格式
        ("2.1.2.1. 系统结构", 4),
        ("2.1.2.1.1 锦苏直流送端安全稳定控制系统", 4),
        ("2.1. 配置说明", 2),
        ("3.2.1. 操作步骤", 3),
        ("1. 概述", 1),

        # 中文章节标记
        ("第一章 总则", 1),
        ("第二节 系统配置", 2),
        ("第三章 安全规范", 1),

        # 普通文本（不应识别为标题）
        ("这是一段普通文本，不是标题", None),
        ("锦屏站安控装置1（2）", None),
        ("复龙站安控装置1、宜宾站安控装置1", None),

        # 短编号 + 中文
        ("1 概述", 2),
        ("2 系统结构", 2),

        # 带括号的编号
        ("（一）基本要求", 3),
        ("(1) 操作规范", 3),

        # 字母编号
        ("A. 附录", 4),
        ("a) 说明", 4),
    ]

    print("\n标题检测测试结果:")
    print("=" * 80)

    all_passed = True
    for text, expected_level in test_cases:
        detected_level = extractor._detect_heading_from_text(text)
        status = "✓" if detected_level == expected_level else "✗"

        if detected_level != expected_level:
            all_passed = False

        if detected_level is not None:
            print(f"{status} [{text:50}] -> L{detected_level} (期望: L{expected_level})")
        else:
            print(f"{status} [{text:50}] -> 普通文本 (期望: {'普通文本' if expected_level is None else f'L{expected_level}'})")

    print("=" * 80)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")

    return all_passed


def test_chapter_path_update():
    """测试章节路径更新"""
    extractor = PageExtractor("test")

    print("\n章节路径更新测试:")
    print("=" * 80)

    # 模拟处理一系列标题
    headings = [
        ("第一章 总则", 1),
        ("1.1. 适用范围", 2),
        ("1.1.1 系统概述", 3),
        ("第二章 系统配置", 1),
        ("2.1. 基本配置", 2),
        ("2.1.1. 硬件要求", 3),
        ("2.1.1.1 服务器配置", 4),
    ]

    for text, level in headings:
        extractor._update_chapter_path(text, level)
        path_str = " > ".join(extractor._current_chapter_path)
        print(f"L{level} [{text:30}] -> 路径: {path_str}")

    print("=" * 80)
    print(f"✓ 最终章节路径: {' > '.join(extractor._current_chapter_path)}")

    # 验证最终路径
    expected_path = ["第二章 系统配置", "2.1. 基本配置", "2.1.1. 硬件要求", "2.1.1.1 服务器配置"]
    if extractor._current_chapter_path == expected_path:
        print("✓ 章节路径正确")
        return True
    else:
        print(f"✗ 章节路径不正确，期望: {expected_path}")
        return False


if __name__ == "__main__":
    # 运行测试
    test1_passed = test_detect_heading_from_text()
    test2_passed = test_chapter_path_update()

    print("\n" + "=" * 80)
    if test1_passed and test2_passed:
        print("✓ 所有测试通过")
        exit(0)
    else:
        print("✗ 部分测试失败")
        exit(1)
