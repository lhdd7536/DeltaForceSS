"""账号面板完成时间解析测试（纯逻辑，不需要 Tk 窗口）"""
import pytest

from gui.account_panel import parse_end_time


@pytest.mark.parametrize('raw,expected', [
    ('', ''),            # 空 -> 未设置
    ('   ', ''),
    ('—', ''),           # 制造后"无需制造"的占位符
    ('-', ''),
    ('08:30', '08:30'),
    ('8:5', '08:05'),    # 自动补零
    ('8：30', '08:30'),   # 全角冒号
    ('00:00', '00:00'),
    ('23:59', '23:59'),
])
def test_parse_end_time_ok(raw, expected):
    assert parse_end_time(raw) == (expected, None)


@pytest.mark.parametrize('raw', ['24:00', '12:60', 'abc', '12', '12:345', '1:2:3', '：'])
def test_parse_end_time_invalid(raw):
    value, err = parse_end_time(raw)
    assert value is None
    assert err
