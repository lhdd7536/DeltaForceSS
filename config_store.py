"""配置加载与全局状态（单账号制造）。

集中管理 config.yaml / user_config.yaml 的加载、可变状态
（scale_factor / departments_coords / wait_list / _global_stop_event 等）
与相关设置函数。其他模块通过 ``import config_store as cs`` 实时访问。
"""

import os
import shutil

import pytesseract
from ruamel.yaml.comments import CommentedSeq

from utils import (
    project_root,
    load_yaml,
    load_ruamel,
    dump_yaml_rt,
    resolve_tesseract_path,
)


# ── 项目根目录 ────────────────────────────────────────
PROJECT_ROOT = project_root()

# ── 配置（import 时加载，与原 main.py 行为一致） ────────
config = load_yaml(os.path.join(PROJECT_ROOT, 'config.yaml'))
user_config = load_yaml(os.path.join(PROJECT_ROOT, 'user_config.yaml'))

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'log')
TESSERACT_PATH = user_config['TESSERACT_PATH']
# 配置路径失效时自动回退到 dist/Tesseract-OCR 或项目根/Tesseract-OCR
_resolved_tess = resolve_tesseract_path(TESSERACT_PATH)
if _resolved_tess:
    TESSERACT_PATH = _resolved_tess
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

scale_factor = 1
departments_coords = None
debug_mode = user_config['debug_mode']

wait_list = {
    # None -> skip this department
    # [dep, item_name]
    'tech': None,
    'work': None,
    'medical': None,
    'armor': None,
}

# 全局停止信号（automator 的可中断休眠读取，main() 写入）
_global_stop_event = None

valid_resolution = {(1920, 1080), (2560, 1440), (3840, 2160)}


class IncorrectResolution(Exception):
    def __init__(self, message="分辨率错误"):
        self.message = message
        super().__init__(self.message)


# ── 设置函数 ──────────────────────────────────────────

def setup_output_directory(output_dir):
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)


def scale_coords(coords):
    if isinstance(coords, (list, tuple)):
        if all(isinstance(item, (list, tuple)) for item in coords):
            return [scale_coords(item) for item in coords]
        else:
            return [int(x * scale_factor) for x in coords]
    elif isinstance(coords, dict):
        return {k: scale_coords(v) for k, v in coords.items()}
    else:
        return coords


def update_wait_list():
    def find_match(dep):
        target_name = user_config[dep][0][0]
        for key, value in config['departments'][dep].items():
            for item_name in value:
                if item_name == target_name:
                    wait_list[dep] = [key, target_name]
                    return
        raise ValueError(f'Incorrect name: {target_name}')

    user_config = load_yaml(os.path.join(PROJECT_ROOT, 'user_config.yaml'))

    for dep in ['tech', 'work', 'medical', 'armor']:
        if not user_config[dep]:
            wait_list[dep] = None
            continue
        find_match(dep)


def write_user_config(department):
    # Load the existing config with comments
    user_config = load_ruamel(os.path.join(PROJECT_ROOT, 'user_config.yaml'))

    if not user_config.get(department):
        return

    first_item = user_config[department][0]
    print(first_item)
    _, quantity = first_item

    # Modify the quantity
    if quantity in (0, 1):
        user_config[department].pop(0)
    elif quantity > 1:
        first_item[1] -= 1

    # Post-processing to maintain perfect formatting
    for key in user_config:
        # Convert empty lists to None to prevent "[]" output
        if isinstance(user_config[key], list) and not user_config[key]:
            user_config[key] = None
        # Ensure flow style for all list items
        elif isinstance(user_config[key], CommentedSeq):
            for item in user_config[key]:
                if isinstance(item, list):
                    item.fa.set_flow_style()

    # Write back to file
    dump_yaml_rt(os.path.join(PROJECT_ROOT, 'user_config.yaml'), user_config)


def set_screen_resolution():
    import pyautogui
    width, height = pyautogui.size()
    print(f'[DEBUG] pyautogui.size() = {width}x{height}')
    if (width, height) not in valid_resolution:
        raise IncorrectResolution(f'非法分辨率: {width}x{height}, 只支持 {valid_resolution}\n以游戏分辨率为准')
    global scale_factor
    print(f'当前分辨率: {width} x {height}')
    scale_factor = width / 1920
