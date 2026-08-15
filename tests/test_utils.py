"""utils 工具函数测试"""
import os
import random
import sys
import types

import utils


def test_calc_jitter_range():
    for _ in range(50):
        seconds = random.uniform(1, 100)
        j = utils.calc_jitter(seconds)
        assert 0.1 <= j <= seconds * 1.2 + 1e-9


def test_calc_jitter_max_cap():
    # 超过 150s 时抖动封顶 30s
    j = utils.calc_jitter(500)
    assert 470 <= j <= 530


def test_read_utf8(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello", encoding="utf-8")
    assert utils.read_with_encoding_fallback(str(p)) == "hello"


def test_read_gbk_fallback(tmp_path):
    p = tmp_path / "b.txt"
    p.write_bytes("中文内容".encode("gbk"))
    assert utils.read_with_encoding_fallback(str(p)) == "中文内容"


def test_project_root():
    root = utils.project_root()
    assert os.path.isabs(root)
    assert os.path.isfile(os.path.join(root, "main.py"))


def test_yaml_roundtrip(tmp_path):
    p = str(tmp_path / "cfg.yaml")
    data = {"tech": [["骨架狙击枪托", -1]], "flag": None}
    utils.dump_yaml_rt(p, data)
    loaded = utils.load_ruamel(p)
    assert loaded["tech"][0][0] == "骨架狙击枪托"
    assert loaded["flag"] is None
    # safe_load 也能读同一文件
    assert utils.load_yaml(p)["tech"][0][1] == -1


def test_resolve_tesseract_configured(tmp_path):
    fake = tmp_path / "tesseract.exe"
    fake.write_bytes(b"x")
    assert utils.resolve_tesseract_path(str(fake)) == str(fake)


def test_resolve_tesseract_missing_falls_back():
    # 配置路径不存在时回退到 dist/Tesseract-OCR（仓库内存在）
    resolved = utils.resolve_tesseract_path("Z:\\no\\such\\tesseract.exe")
    assert resolved == os.path.join(utils.project_root(), "dist", "Tesseract-OCR", "tesseract.exe")


def test_click_at_jitter(monkeypatch):
    calls = {}
    fake_pg = types.SimpleNamespace()
    fake_pg.moveTo = lambda x, y, duration: calls.update(x=x, y=y, duration=duration)
    fake_pg.click = lambda: calls.update(clicked=True)
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pg)

    utils.click_at(100, 200)
    assert calls.get("clicked") is True
    assert 97 <= calls["x"] <= 103
    assert 197 <= calls["y"] <= 203
