"""单账号制造业务流程。

主循环 main()、仪表盘 dash_page()、列表导航、自动购买材料等。
识别/图像/配置分别来自 ocr / vision / config_store。
"""

import os
import time
from datetime import datetime, timedelta

import cv2
import numpy as np
import keyboard
import pyautogui
import win32gui
import win32con
try:
    import winsound
except ImportError:
    winsound = None
import pytesseract

from core import config_store as cs
from core.utils import calc_jitter, click_at
from core.vision import screenshot, save_image, cropImage, match_list_items
from core.ocr import (
    OCR_remain_time,
    OCR_is_free,
    OCR_item_name,
    OCR_price,
    best_match_item,
    time_to_seconds,
)


class IncorrectPageError(Exception):
    def __init__(self, message="未检测到特勤处建造界面"):
        self.message = message
        super().__init__(self.message)


# ── 可中断休眠 ────────────────────────────────────────

def _interruptible_sleep(seconds):
    """可中断休眠（加入 ±20% 随机波动，最大 30s），停止事件触发时立即返回 True"""
    actual = calc_jitter(seconds)
    if cs._global_stop_event is not None:
        return cs._global_stop_event.wait(timeout=actual)
    time.sleep(actual)
    return False


# Mouse
def click_position(position):
    # 坐标已在 scale_coords() 中缩放，直接点击
    click_at(position[0], position[1])


def scroll_down_x4(position):
    pyautogui.moveTo(position[0], position[1], duration=0.3)
    for _ in range(4):
        pyautogui.scroll(-120)
        pyautogui.sleep(0.1)
    _interruptible_sleep(1)


def craft(coordination, department=None):
    build_position = cs.departments_coords['build_position']
    click_position(coordination)
    _interruptible_sleep(1)
    has_all_materials = initalize_preparation()
    if has_all_materials:
        click_position(build_position)
        _interruptible_sleep(3)
        # 点击建造成功后才消耗队列（避免制造失败时丢失配置项）
        if department:
            cs.write_user_config(department)
        keyboard.send('esc')
        _interruptible_sleep(1)
        return True
    keyboard.send('esc')
    _interruptible_sleep(1)
    return False


# Other function
def high_beep():
    if winsound:
        winsound.Beep(2000, 500)


def low_beep():
    if winsound:
        winsound.Beep(500, 500)


def alt_tab():
    keyboard.press('alt')
    time.sleep(0.13)
    keyboard.press('tab')
    time.sleep(0.1)
    keyboard.release('tab')
    time.sleep(0.02)
    keyboard.release('alt')


def buy_material():
    # purchase page
    x, y = cs.departments_coords['price_point']
    w, h = cs.departments_coords['price_size']
    price = None

    trial = 11
    for i in range(trial):
        image = screenshot('combined_binary', 'materialPricePage', (x, y, w, h))
        price = OCR_price(image)
        if price is not None:
            if i == trial - 1:
                keyboard.send('esc')
                _interruptible_sleep(1)
                return -1
            # cleck price to buy
            click_position(cs.departments_coords['price_position'])
            _interruptible_sleep(3)
        else:
            return price
    return -1


def find_buy_state():
    '''
    -1: not exist buy icon
    0:  three materials
    1:  four materials
    '''
    buy_points = cs.departments_coords['buy_points']
    w, h = cs.departments_coords['buy_size']
    full_page = screenshot('binary', 'buyState')
    for index, value in enumerate(buy_points):
        x, y = value
        binary_img = cropImage(full_page, (x, y, w, h))
        white_pix = np.sum(binary_img == 255)
        white_ratio = white_pix / binary_img.size
        if white_ratio >= 0.05:
            return index
    return -1


def initalize_preparation():
    buy_state = find_buy_state()
    if buy_state == -1:
        return True

    # go to buy page
    click_position(cs.departments_coords['buy_positions'][buy_state])
    _interruptible_sleep(3)
    price = buy_material()
    if price == -1:
        print(f'! 物品购买失败, 达到了最大尝试次数, 可能是交易行缺货')
    elif price == 0:
        print(f'! 缺少无法购买的物品, 例如高级燃料， 钛合金')
        keyboard.send('esc')
        _interruptible_sleep(1)
    buy_state = find_buy_state()
    return buy_state == -1


def department_status(dash_img, dep_coords, dep_name=''):
    '''
    return remain time in sec
    -1: done (completed & ready to collect)
    -2: not started (idle)
    '''
    prefix = f'[{dep_name}]' if dep_name else ''

    # check 设备处于空闲状态
    x, y = dep_coords['free']
    w, h = dep_coords['free_size']
    center_img = cropImage(dash_img, (x, y, w, h))
    is_free = OCR_is_free(center_img)
    t_config = r'-l chi_sim'
    free_text = pytesseract.image_to_string(center_img, config=t_config)
    print(f'{prefix} [DEBUG department_status] 空闲检测区域 ({x},{y},{w},{h}) OCR: "{free_text.strip()}" → 匹配空闲中: {is_free}')
    if is_free:
        return -2

    # read remain time: success -> in progress, fail -> unknown
    x, y = dep_coords['timmer']
    w, h = dep_coords['timmer_size']
    timmer_img = cropImage(dash_img, (x, y, w, h))
    remain_time_str = OCR_remain_time(timmer_img)
    print(f'{prefix} [DEBUG department_status] 计时器区域 ({x},{y},{w},{h}) OCR: "{remain_time_str}"')

    # OCR 返回 None → 计时器区域空白 → 制造已完成可领取
    if remain_time_str is None:
        return -1

    # 有文本但无法解析为时间格式 → 非空闲中+非合法计时器=已完成
    #（完成状态的计时器区域是空白，但 OCR 可能捡到残余像素产生 "7" 等噪声）
    remain_time = time_to_seconds(remain_time_str)
    if remain_time is None:
        return -1

    return remain_time


def is_main_page():
    region = cs.departments_coords['tech_dep_region']
    # 确保日志目录存在（debug_mode 关闭时也需要保存调试截图）
    os.makedirs(cs.OUTPUT_DIR, exist_ok=True)
    for i in range(2):
        image = screenshot('binary', 'main_page', region)
        t_config = r'-l chi_sim --psm 7'
        text = pytesseract.image_to_string(image, config=t_config)
        print(f'[DEBUG is_main_page] 尝试 {i+1}/2 — 区域: {region} — OCR 原始文本: "{text.strip()}"')
        if '技术中心' in text:
            return True
    # 两次都失败：保存截图到 log 目录方便肉眼确认
    print(f'[DEBUG is_main_page] 检测失败！坐标区域 {region} 中未识别到"技术中心"')
    print(f'[DEBUG is_main_page] 两次 OCR 结果均不含目标文字，请检查截图确认 UI 布局是否变化')
    # 保存全屏截图
    full = screenshot('original', 'main_page_fail_full')
    save_image([(full, 'main_page_fail_full', None)])
    # 保存区域彩色截图（更易肉眼辨认）
    from PIL import ImageGrab
    pil_img = ImageGrab.grab(bbox=(region[0], region[1], region[0]+region[2], region[1]+region[3]))
    frame = np.array(pil_img)
    region_color = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    save_image([(region_color, 'main_page_fail_region', region)])
    print(f'[DEBUG is_main_page] 已保存截图到 {cs.OUTPUT_DIR}/，请查看 main_page_fail_full 和 main_page_fail_region')
    return False


def dash_page():
    def get_remain_times(dash_img):
        status = []
        for dep, coords in cs.departments_coords['dash_page'].items():
            status.append((dep, department_status(dash_img, coords, dep)))
        return status

    if cs.debug_mode:
        cs.setup_output_directory(cs.OUTPUT_DIR)

    if not is_main_page():
        print(f'[DEBUG dash_page] is_main_page() 返回 False，将抛出 IncorrectPageError')
        print(f'[DEBUG dash_page] departments_coords[\'tech_dep_region\'] = {cs.departments_coords["tech_dep_region"]}')
        print(f'[DEBUG dash_page] 缩放因子 scale_factor = {cs.scale_factor}')
        print(f'[DEBUG dash_page] 请检查 log/ 目录下的 main_page_fail_*.png 截图确认当前画面')
        raise IncorrectPageError()

    dash_img = screenshot('gray', 'department_status')

    status = get_remain_times(dash_img)
    processing_department = set()

    for dep, state in status:
        if state == -1:
            click_position(cs.departments_coords['dash_page'][dep]['free'])
            if _interruptible_sleep(3):
                return []
            keyboard.send('space')
            if _interruptible_sleep(3):
                return []
            state = -2
        if state == -2 and cs.wait_list[dep]:
            # 队列消耗在 craft() 中点击建造后执行，此处仅打开制造列表
            click_position(cs.departments_coords['dash_page'][dep]['free'])
            if _interruptible_sleep(3):
                return []
            if list_page(dep):  # craft() 返回 True = 建造按钮已点击
                processing_department.add(dep)
            # 若返回 False（物品未找到/材料不足），不在 processing_department 中
            # 重试轮次会再次尝试

    # 重试轮次：某些部门可能在其他部门处理期间变为完成/空闲，或 OCR 误判导致第一轮漏处理
    for retry in range(3):
        if _interruptible_sleep(5):
            return []
        retry_img = screenshot('gray', 'department_status_retry')
        retry_status = get_remain_times(retry_img)
        # 截屏有效性检查：如果没有任一个部门显示有效计时器（>0），说明截屏时机不对
        # 此时所有部门的 -1 可能只是"OCR 读不到数字"而非真正完成，跳过本轮重试
        valid_timer_count = sum(1 for _, s in retry_status if s > 0)
        if valid_timer_count == 0:
            continue
        has_new_work = False
        for dep, state in retry_status:
            if dep in processing_department:
                continue
            if state == -1 and cs.wait_list[dep]:
                # 刚完成的部门：收集并重新制造
                click_position(cs.departments_coords['dash_page'][dep]['free'])
                if _interruptible_sleep(3):
                    return []
                keyboard.send('space')
                if _interruptible_sleep(3):
                    return []
                click_position(cs.departments_coords['dash_page'][dep]['free'])
                if _interruptible_sleep(3):
                    return []
                list_page(dep)
                if _interruptible_sleep(0.5):
                    return []
                processing_department.add(dep)
                has_new_work = True
            elif state == -2 and cs.wait_list[dep]:
                # 刚空闲的部门：启动制造
                click_position(cs.departments_coords['dash_page'][dep]['free'])
                if _interruptible_sleep(3):
                    return []
                if list_page(dep):  # craft() 返回 True = 制造成功启动
                    processing_department.add(dep)
                    has_new_work = True
                # 返回 False 则仍空闲，等待下一次 main() 循环重试
        if not has_new_work:
            break

    dash_img = screenshot('gray', 'department_status')
    status = get_remain_times(dash_img)
    remain_times = []
    print(f'制造界面:')
    for dep, state in status:
        if state == -2:
            if cs.wait_list[dep]:
                remain_times.append(0)
            print(f'\t{dep}\t 未占用')
        elif state == -1:
            remain_times.append(0)
            print(f'\t{dep}\t 完成!')
        else:
            remain_times.append(state)
            print(f'\t{dep}\t 占用中, 剩余时间:\t{state // 3600}:{(state % 3600) // 60:02d}:{state % 60:02d}')

    return remain_times


def list_page(department):
    category, target = cs.wait_list[department]
    return list_page_operation(department, category, target)


def list_page_operation(department, category, target):
    from rapidfuzz import fuzz

    reference = cs.config['departments'][department][category]
    list_size = cs.departments_coords['list_size']
    list_point = cs.departments_coords['list_point']
    x = list_point[0] + int(list_size[0] / 2)
    y_offset = list_point[1]
    last_top_item = ''
    black_spot = cs.departments_coords['list_black_spot']
    pyautogui.moveTo(black_spot[0], black_spot[1], duration=0.3)

    for k in range(100):
        if _interruptible_sleep(0.05):
            keyboard.send('esc')
            return False
        y1 = 2
        cells = match_list_items()
        # (image, y position)
        img, y1 = cells[0]
        factor = cs.config['OCR_factors'][department]

        # same top item -> reached bottom
        current_top_item = OCR_item_name(img, department)
        score = 0
        if last_top_item:
            score = fuzz.ratio(last_top_item, current_top_item)

        specialcase = '侧置' in last_top_item

        if score >= factor and not specialcase:
            print(f'! {department}.{category}.{target} 未找到')
            print(f'具体信息: last: {last_top_item}, OCR 结果: {current_top_item}, 相似度: {score}')
            keyboard.send('esc')
            return False

        last_top_item = current_top_item

        # loop list
        for i in cells:
            img, y = i
            text = OCR_item_name(img, department)
            match, score = best_match_item(text, reference)
            if cs.debug_mode:
                print(f'{text}, {match}, {score}')
            if match is None:
                continue
            if match == target and score >= factor:
                return craft((x, y_offset + y), department)
        scroll_down_x4(black_spot)
    # 兜底：如果 for 循环跑满 100 次仍未找到也未触发"已到末尾"，确保返回仪表盘
    keyboard.send('esc')
    _interruptible_sleep(0.3)
    return False


def print_restart_info(remain_time):
    restart_time = datetime.now() + timedelta(seconds=remain_time)

    time_str = f"距离下一次激活: {remain_time // 3600}:{(remain_time % 3600) // 60:02d}:{remain_time % 60:02d}"
    restart_str = f"下一次激活时间: {restart_time.strftime('%H:%M:%S')}"
    max_length = max(len(time_str), len(restart_str)) + 15
    border = '#' * max_length

    output = (
        f"\n{border}\n"
        f"#{time_str.center(max_length - 9)}#\n"
        f"#{restart_str.center(max_length - 9)}#\n"
        f"{border}\n\n"
    )

    print(output)


def main(stop_event=None, status_callback=None, single_cycle=False):
    """自动制造主循环

    Args:
        stop_event: threading.Event, 设置后中断循环
        status_callback: callable, 每次迭代报告 (remain_times, wait_list) 状态
        single_cycle: bool, 仅执行一轮 dash_page 后返回（多账号使用）
    """
    cs._global_stop_event = stop_event

    print('###### 程序初始化 ######')
    background_mode = cs.user_config['background_mode']
    hwnd = win32gui.FindWindow('UnrealWindow', '三角洲行动  ')

    while stop_event is None or not stop_event.is_set():
        try:
            high_beep()
            if _interruptible_sleep(1):
                print("用户手动停止")
                return
            if background_mode:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                if _interruptible_sleep(3):
                    print("用户手动停止")
                    return
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            if _interruptible_sleep(6):
                print("用户手动停止")
                return

            cs.set_screen_resolution()
            cs.departments_coords = {k: cs.scale_coords(v) for k, v in cs.config['departments_coords'].items()}

            cs.update_wait_list()
            remain_times = dash_page()
            cs.update_wait_list()

            # 报告状态
            if status_callback:
                status_callback(remain_times, cs.wait_list)

            if single_cycle:
                print('单次模式：完成一轮制造检测')
                return

            if _interruptible_sleep(3):
                print("用户手动停止")
                return

            remain_time = min(remain_times) if remain_times else 0
            remain_time += 30     # 30 sec buffer

            if background_mode:
                alt_tab()

            print_restart_info(remain_time)
            low_beep()

            # 可中断休眠
            if _interruptible_sleep(remain_time):
                print("用户手动停止")
                return
        except IncorrectPageError as e:
            low_beep()
            print(f'界面异常: {e}')
            if single_cycle:
                return
            if _interruptible_sleep(30):
                print("用户手动停止")
                return
            else:
                print('等待 30 秒后自动重试...')
        except Exception as e:
            low_beep()
            print(e)
            if single_cycle:
                return
            if stop_event is not None:
                if status_callback:
                    status_callback([0, 0, 0, 0], {k: None for k in cs.wait_list})
                return
            else:
                input('程序异常, 按 *回车* 键退出')
                return
