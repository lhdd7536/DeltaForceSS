"""Delta Force 自动制造 - 单账号模式入口（薄壳）。

业务逻辑已拆分：
- ``config_store`` — 配置加载与全局状态
- ``vision`` — 截图与图像处理
- ``ocr`` — OCR 识别与文本匹配
- ``automator`` — 业务流程（main / dash_page / list_page ...）

本文件保留主循环入口 ``main()``（GUI / 多账号模块通过
``import main as auto_module; auto_module.main(...)`` 调用）、
调试测试函数与命令行入口。
"""

import time

import pyautogui
import win32gui
import win32con

from core import config_store as cs
from core.automator import main, high_beep, low_beep, scroll_down_x4, IncorrectPageError  # noqa: F401
from core.vision import match_list_items
from core.ocr import OCR_item_name, best_match_item


def list_OCR_test(department, categories):
    cs.departments_coords = {k: cs.scale_coords(v) for k, v in cs.config['departments_coords'].items()}
    hwnd = win32gui.FindWindow('UnrealWindow', '三角洲行动  ')
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(4)

    list_size = cs.departments_coords['list_size']
    list_point = cs.departments_coords['list_point']
    x = list_point[0] + int(list_size[0] / 2)
    y_offset = list_point[1]
    factor = cs.config['OCR_factors'][department]

    for category in categories:
        reference = cs.config['departments'][department][category]
        for target in reference:
            y1 = 2
            t = True
            print(f"#########################: {target}")
            while t:
                cells = match_list_items()
                # (image, y position)
                img, y1 = cells[0]

                # loop list
                for i in cells:
                    img, y = i
                    OCR_text = OCR_item_name(img, department)
                    match, score = best_match_item(OCR_text, reference)
                    if match is None:
                        continue
                    if match == target and score >= factor:
                        print(f'!!!! {OCR_text} match: {match} at: {score}')
                        t = False
                        pyautogui.scroll(5000)
                        pyautogui.sleep(0.5)
                        low_beep()
                        time.sleep(2)
                        break
                    else:
                        print(f'xxxx {OCR_text} match: {match} at: {score}')

                if t:
                    scroll_down_x4(cs.config['departments_coords']['list_black_spot'])
    high_beep()


def test1():
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            if title:  # Only show windows with titles
                print(f"HWND: {hwnd}, Class Name: {class_name}, Title: {title}")

    win32gui.EnumWindows(callback, None)


def test2():
    cs.set_screen_resolution()
    cs.update_wait_list()
    print(cs.wait_list)
    cs.departments_coords = {k: cs.scale_coords(v) for k, v in cs.config['departments_coords'].items()}
    cs.write_user_config('tech')
    cs.update_wait_list()
    print(cs.wait_list)


if __name__ == "__main__":
    main()
    # list_OCR_test('tech',['握把'])
