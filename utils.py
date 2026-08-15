"""共享工具函数"""
import os
import random
import sys
import time

import yaml as _pyyaml
from ruamel.yaml import YAML as _RuamelYAML


def project_root():
    """项目根目录：源码模式为仓库根目录，EXE 模式为 EXE 所在目录"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def calc_jitter(seconds):
    """计算 ±20% 随机波动后的时长（最大抖动 30s），不执行休眠"""
    jitter = min(seconds * 0.2, 30)
    return max(0.1, seconds + random.uniform(-jitter, jitter))


def jitter_sleep(seconds):
    """休眠（加入 ±20% 随机波动，最大 30s）"""
    time.sleep(calc_jitter(seconds))


def read_with_encoding_fallback(path, primary='utf-8', fallback='gbk'):
    """读取文件，主编码失败时回退到备用编码。

    用于兼容中文 Windows 下可能以 GBK 保存的旧配置文件。
    写操作一律使用 UTF-8，确保新文件编码统一。
    """
    try:
        with open(path, 'r', encoding=primary) as f:
            return f.read()
    except UnicodeDecodeError:
        print(f"[utils] 文件编码不是 {primary}，尝试 {fallback} 编码读取: {path}")
        with open(path, 'r', encoding=fallback) as f:
            return f.read()


# ── 配置读取/写入 ─────────────────────────────────────

def load_yaml(path):
    """PyYAML safe_load + 编码回退（不保留注释，适合只读场景）"""
    return _pyyaml.safe_load(read_with_encoding_fallback(path))


def _new_ruamel():
    yaml = _RuamelYAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    yaml.width = 120
    return yaml


def load_ruamel(path):
    """ruamel 加载（保留注释/格式），配合 dump_yaml_rt 写回"""
    return _new_ruamel().load(read_with_encoding_fallback(path))


def dump_yaml_rt(path, data):
    """ruamel 写回（保留注释/格式），UTF-8"""
    with open(path, 'w', encoding='utf-8') as f:
        _new_ruamel().dump(data, f)


# ── Tesseract 定位 ────────────────────────────────────

def resolve_tesseract_path(configured_path=None):
    """定位 tesseract.exe：配置路径 → dist/Tesseract-OCR → 项目根/Tesseract-OCR

    返回存在的路径；全部不存在时返回 None。
    """
    candidates = []
    if configured_path:
        candidates.append(configured_path)
    candidates.append(os.path.join(project_root(), 'dist', 'Tesseract-OCR', 'tesseract.exe'))
    candidates.append(os.path.join(project_root(), 'Tesseract-OCR', 'tesseract.exe'))
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


# ── 鼠标点击 ──────────────────────────────────────────

def click_at(x, y, jitter=3):
    """在指定屏幕坐标点击（不做缩放），加入 ±jitter 随机偏移和随机移动时长"""
    x += random.randint(-jitter, jitter)
    y += random.randint(-jitter, jitter)
    import pyautogui
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.5))
    pyautogui.click()
