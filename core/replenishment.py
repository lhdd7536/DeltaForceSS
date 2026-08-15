"""
制造材料补货模块。

在多账号模式下，导航到军需处 -> 收集品界面，检查钛合金和高级燃料库存，
低于阈值时自动补货。

坐标由调用方传入（从 config.yaml replenish_coords 加载），基于 1920x1080 基准，
click_position 内部会自动缩放，OCR 截图区域在此模块内缩放。
"""

import cv2
import numpy as np
import pyautogui
import pytesseract
from PIL import ImageGrab
import keyboard
from core.wegame_switcher import click_position
from core.utils import jitter_sleep, resolve_tesseract_path

# ── Tesseract 路径初始化 ──────────────────────────────────
# 优先 dist/Tesseract-OCR（开发环境），fallback Tesseract-OCR（打包后）
_tess_path = resolve_tesseract_path()
if _tess_path:
    pytesseract.pytesseract.tesseract_cmd = _tess_path


def _get_scale_factor():
    """检测当前分辨率并计算缩放因子（基准 1920x1080）"""
    width, _ = pyautogui.size()
    return width / 1920


def OCR_quantity(image):
    """OCR 识别材料数量（9x17 px 数字区域）"""
    t_config = r'--psm 7 -c tessedit_char_whitelist=0123456789'
    text = pytesseract.image_to_string(image, config=t_config)
    text = text.strip()
    try:
        return int(text) if text else 0
    except ValueError:
        return 0


def do_replenish_materials(coords, threshold, quantity):
    """
    补货主流程。

    Args:
        coords: 1920x1080 基准的原始坐标 dict（含 materials 嵌套）
                click_position 会内部缩放，region 在此函数内缩放
        threshold: 低于此值触发补货
        quantity: 步骤15 增加购买数量 按钮点击次数
    """
    # 步骤 9-12：导航到收集品界面
    _navigate_to_collectibles(coords)

    materials = [
        ('钛合金', coords['materials']['titanium_alloy']),
        ('高级燃料', coords['materials']['advanced_fuel']),
    ]

    for name, mat in materials:
        print(f'[补货] 检查 {name}...')
        click_position(mat['click'])
        jitter_sleep(1)

        # 步骤 14：OCR 当前数量（region 需先缩放）
        x, y, w, h = mat['quantity_region']
        sf = _get_scale_factor()
        sx, sy = int(x * sf), int(y * sf)
        sw, sh = max(1, int(w * sf)), max(1, int(h * sf))
        pil_img = ImageGrab.grab(bbox=(sx, sy, sx + sw, sy + sh))
        frame = np.array(pil_img)
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        current_qty = OCR_quantity(binary)
        print(f'[补货] {name} 当前数量: {current_qty}')

        if current_qty >= threshold:
            print(f'[补货] {name} 数量充足 ({current_qty} >= {threshold})，跳过')
            continue

        print(f'[补货] {name} 不足 ({current_qty} < {threshold})，补货 {quantity} 次')
        for i in range(quantity):
            click_position(coords['increase_btn'])
            jitter_sleep(0.3)
        click_position(coords['fill_btn'])
        jitter_sleep(1)
        click_position(coords['buy_btn'])
        jitter_sleep(1)
        click_position(coords['buy_btn'])
        jitter_sleep(2)
        print(f'[补货] {name} 已购买')

    # 步骤 18-21：整理仓库
    print('[补货] 步骤18: 按 ESC')
    keyboard.send('esc')
    jitter_sleep(1)
    print('[补货] 步骤19: 点击仓库')
    click_position(coords['warehouse_tab'])
    jitter_sleep(1)
    print('[补货] 步骤20: 点击整理')
    click_position(coords['sort_btn'])
    jitter_sleep(1)
    print('[补货] 步骤21: 确认整理')
    click_position(coords['confirm_sort'])
    jitter_sleep(1)

    print('[补货] 全部材料处理完毕')


def _navigate_to_collectibles(coords):
    """从主基地导航到军需处 -> 医疗部门 -> 收集品界面（步骤 9-12）"""
    print('[补货] 步骤9: 点击部门')
    click_position(coords['dep_tab'])
    jitter_sleep(1)

    print('[补货] 步骤10: 点击军需处')
    click_position(coords['quartermaster'])
    jitter_sleep(1)

    print('[补货] 步骤11: 点击医疗部门')
    click_position(coords['medical_dep'])
    jitter_sleep(1)

    print('[补货] 步骤12: 点击收集品界面')
    click_position(coords['collectibles_tab'])
    jitter_sleep(1)
