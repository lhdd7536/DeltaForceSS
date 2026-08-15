"""ocr 模块纯函数测试（无需真实截图/OCR）"""
from core.ocr import best_match_item, time_to_seconds


def test_best_match_exact():
    match, score = best_match_item("M249轻机枪", ["M249轻机枪", "AKM突击步枪"])
    assert match == "M249轻机枪"
    assert score == 100.0


def test_best_match_whitespace_trimmed():
    match, score = best_match_item("  M249轻机枪  ", ["M249轻机枪"])
    assert match == "M249轻机枪"
    assert score == 100.0


def test_best_match_no_hit():
    match, score = best_match_item("", ["AKM突击步枪"])
    assert match is None
    assert score == 0


def test_best_match_empty_reference():
    match, score = best_match_item("M249轻机枪", [])
    assert match is None
    assert score == 0


def test_time_to_seconds_hms():
    assert time_to_seconds("1:30:05") == 5405


def test_time_to_seconds_ms():
    # 既有行为：仅支持 HH:MM:SS 三段格式；MM:SS 解包失败返回 None
    # （若游戏计时器为 MM:SS 会被 department_status 视为"已完成"，已知限制）
    assert time_to_seconds("05:30") is None


def test_time_to_seconds_none():
    assert time_to_seconds(None) is None


def test_time_to_seconds_garbage():
    assert time_to_seconds("abc") is None
    assert time_to_seconds("7") is None
