import cv2
import numpy as np
import os
import shutil
import pytesseract
import pyautogui
import yaml
import re
import time
import keyboard
try:
    import winsound
except ImportError:
    winsound = None
import hashlib
import random
import win32gui, win32con
from PIL import ImageGrab
from datetime import datetime, timedelta
from rapidfuzz import fuzz
from datetime import datetime
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
import ctypes
import sys
from utils import calc_jitter, read_with_encoding_fallback

try:
    from daily_fetcher import maybe_update_recipes
    _HAS_FETCHER = True
except ImportError:
    _HAS_FETCHER = False

# ── 项目根目录（兼容 PyInstaller EXE 模式） ──────────────
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class IncorrectPageError(Exception):
    def __init__(self, message="未检测到特勤处建造界面"):
        self.message = message
        super().__init__(self.message)


# ── 全局停止信号 ──────────────────────────────────────
_global_stop_event = None


def _interruptible_sleep(seconds):
    """可中断休眠（加入 ±20% 随机波动，最大 30s），停止事件触发时立即返回 True"""
    actual = calc_jitter(seconds)
    global _global_stop_event
    if _global_stop_event is not None:
        return _global_stop_event.wait(timeout=actual)
    time.sleep(actual)
    return False


class IncorrectResolution(Exception):
    def __init__(self, message="分辨率错误"):
        self.message = message
        super().__init__(self.message)

config = yaml.safe_load(read_with_encoding_fallback(os.path.join(PROJECT_ROOT, 'config.yaml')))

user_config = yaml.safe_load(read_with_encoding_fallback(os.path.join(PROJECT_ROOT, 'user_config.yaml')))

OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'log')
TESSERACT_PATH = user_config['TESSERACT_PATH']
# 如果配置路径不存在，尝试相对于项目根目录的 dist/Tesseract-OCR
if not os.path.exists(TESSERACT_PATH):
    dev_path = os.path.join(
        PROJECT_ROOT, 'dist', 'Tesseract-OCR', 'tesseract.exe',
    )
    if os.path.exists(dev_path):
        TESSERACT_PATH = dev_path

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
        'armor': None
    }

# Setup
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
    
    user_config = yaml.safe_load(read_with_encoding_fallback(os.path.join(PROJECT_ROOT, 'user_config.yaml')))
    
    for dep in ['tech', 'work', 'medical', 'armor']:
        if not user_config[dep]:
            wait_list[dep] = None
            continue
        
        find_match(dep)
        
def write_user_config(department):
    # Configure YAML settings
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    yaml.width = 120
    
    # Load the existing config with comments
    user_config = yaml.load(read_with_encoding_fallback(os.path.join(PROJECT_ROOT, 'user_config.yaml')))

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
    with open(os.path.join(PROJECT_ROOT, 'user_config.yaml'), 'w', encoding='utf-8') as file:
        yaml.dump(user_config, file)

valid_resolution = {(1920, 1080), (2560, 1440), (3840, 2160)}
def set_screen_resolution():
    width, height = pyautogui.size()
    if (width, height) not in valid_resolution:
        raise IncorrectResolution(f'非法分辨率: {width}x{height}, 只支持 {valid_resolution}\n以游戏分辨率为准')
    global scale_factor
    print(f'当前分辨率: {width} x {height}')
    scale_factor = width / 1920

# Mouse
def click_position(position):
    x = position[0] + random.randint(-3, 3)
    y = position[1] + random.randint(-3, 3)
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.5))
    pyautogui.click()

def scroll_down_x4(position):
    pyautogui.moveTo(position[0], position[1], duration=0.3)
    for _ in range(4):
        pyautogui.scroll(-120)
        pyautogui.sleep(0.1)
    _interruptible_sleep(1)

def craft(coordination, department=None):
    build_position = departments_coords['build_position']
    click_position(coordination)
    _interruptible_sleep(1)
    has_all_materials = initalize_preparation()
    if has_all_materials:
        click_position(build_position)
        _interruptible_sleep(3)
        # 点击建造成功后才消耗队列（避免制造失败时丢失配置项）
        if department:
            write_user_config(department)
        keyboard.send('esc')
        _interruptible_sleep(1)
        return True
    keyboard.send('esc')
    _interruptible_sleep(1)
    return False


# Image
def cut_by_lines(list_img, horizontal_lines, min_area, prefix='cell'):
    '''
    return list of (image, y position) array
    '''
    cells = []
    height, width = list_img.shape
    horizontal_lines.append(height)
    horizontal_lines = sorted(horizontal_lines)

    prev_y = 0
    for y in horizontal_lines:
        if y > prev_y:
            cell = list_img[prev_y:y, 0:width]
            # area = # black pixel
            area = cell.size
            if area > min_area:
                # center y coord
                center_y = prev_y + (y - prev_y) // 2
                cells.append((cell, center_y))
            prev_y = y
    return cells

# Screenshot
def screenshot(type='binary', hint='placeholder', region=None):
    """
    region (x, y, w, h)
    """
    if region:
        x, y, w, h = region
        pil_img = ImageGrab.grab(bbox=(x, y, x+w, y+h))
    else:
        pil_img = ImageGrab.grab()

    frame = np.array(pil_img)

    if frame is None:
        raise Exception(f'! Failed: screenshot !')

    original_img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
    otsu_thresh, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    min_thresh = 50
    final_thresh = max(otsu_thresh, min_thresh)
    if not region:
        final_thresh -= 10

    _, binary = cv2.threshold(gray, final_thresh, 255, cv2.THRESH_BINARY)

    if debug_mode:
        red_channel = original_img[:, :, 2]
        _, red_binary = cv2.threshold(red_channel, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        combined_binary = cv2.bitwise_xor(binary, red_binary)
        save_image([
            (original_img, f'{hint}_original', None),
            (gray, f'{hint}_gray', None),
            (binary, f'{hint}_binary', None),
            (combined_binary, f'{hint}_combinedBinary', None)
        ])

    if type == 'binary':
        return binary
    elif type == 'original':
        return original_img
    elif type == 'gray':
        return gray
    elif type == 'combined_binary':
        red_channel = original_img[:, :, 2]
        _, red_binary = cv2.threshold(red_channel, 128, 255, cv2.THRESH_BINARY)
        combined_binary = cv2.bitwise_xor(binary, red_binary)
        return combined_binary
    else:
        raise ValueError('! Error: unsupported image type !')



def cropImage(image, region):
    x, y, w, h = region
    cropped = image[y:y+h, x:x+w]

    if debug_mode:
        save_image([(cropped, 'cropped', region)])
    return cropped


# Debug
def show_image(image):
    cv2.imshow('image', image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
def save_image(image_hint_region_tuples):
    '''
    (image, hint, region)
    '''
    timestamp = datetime.now().strftime("%H_%M_%S_%f")[:-3]  # hh:mm:ss:sss
    for image, hint, region in image_hint_region_tuples:
        if region:
            x, y, w, h = region
            cv2.imwrite(os.path.join(OUTPUT_DIR, f'{timestamp}_{hint}_{x},{y},{w},{h}.png'), image)
        else:
            cv2.imwrite(os.path.join(OUTPUT_DIR, f'{timestamp}_{hint}.png'), image)

def debug_visualize_lines(image, lines):
    # Create a copy of the image in RGB format
    image_with_lines = cv2.cvtColor(image.copy(), cv2.COLOR_BGR2RGB)

    # Draw all lines on the image
    for line in lines:
        x1, y1, x2, y2 = line[0]
        cv2.line(image_with_lines, (x1, y1), (x2, y2), (0, 255, 0), 1)  # green line thickness = 1 px
        
    # show_image(image_with_lines)
    
    # Generate unique hash from image data
    image_hash = hashlib.md5(image_with_lines.tobytes()).hexdigest()[:8]
    
    save_image([(image_with_lines, 'list_lines', None)])

# OCR
def OCR_remain_time(image):
    t_config = r'--psm 7 -c tessedit_char_whitelist=0123456789:'
    text = pytesseract.image_to_string(image, config=t_config)
    if text != '':
        return text.strip()
    return None

def OCR_is_free(image):
    t_config = r'-l chi_sim'
    text = pytesseract.image_to_string(image, config=t_config)
    match_score = fuzz.ratio(text, '空闲中')
    return match_score > 60

def OCR_item_name(image, dep):
    OCR_config = config['OCR_configs'][dep]
    text = pytesseract.image_to_string(image, config=OCR_config)

    # manual improvement
    text = text.replace("番", "盔")
    if debug_mode:
        print(f"List Item OCR: {text}")
    return text.strip()

def OCR_price(image):
    t_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist="0123456789,"'
    text = pytesseract.image_to_string(image, config=t_config)
    price = re.sub(r'[^\d]', '', text)
    if price == '':
        return None
    print(f'✅ OCR 价格: {price}')
    return int(price)

def is_main_page():
    region = departments_coords['tech_dep_region']
    # 确保日志目录存在（debug_mode 关闭时也需要保存调试截图）
    os.makedirs(OUTPUT_DIR, exist_ok=True)
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
    pil_img = ImageGrab.grab(bbox=(region[0], region[1], region[0]+region[2], region[1]+region[3]))
    frame = np.array(pil_img)
    region_color = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    save_image([(region_color, 'main_page_fail_region', region)])
    print(f'[DEBUG is_main_page] 已保存截图到 {OUTPUT_DIR}/，请查看 main_page_fail_full 和 main_page_fail_region')
    return False

def best_match_item(str1, reference):
    str1 = str1.strip()
    max_score = 0
    best_match = None
    for item in reference:
        score = fuzz.ratio(str1, item)
        if score > max_score:
            max_score = score
            best_match = item
    return best_match, max_score


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
    x, y = departments_coords['price_point']
    w, h = departments_coords['price_size']
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
            click_position(departments_coords['price_position'])
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
    buy_points = departments_coords['buy_points']
    w, h = departments_coords['buy_size']
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
    click_position(departments_coords['buy_positions'][buy_state])
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
    def time_to_seconds(time_str):
        if time_str is None:
            return None
        try:
            hh, mm, ss = map(int, time_str.split(':'))
            return hh * 3600 + mm * 60 + ss
        except:
            return None  # 解析失败返回 None 而非固定 1800，避免"完成"状态被误判为"占用中"

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

def match_list_items():
    x, y = departments_coords['list_point']
    w, h = departments_coords['list_size']
    list_OCR_img = screenshot('gray', 'list', (x, y, w, h))
    list_edge_img = cv2.Canny(list_OCR_img, 10, 40)

    if list_edge_img is None or list_OCR_img is None:
        raise Exception('! Error: fail to capture list image !')

    list_size = departments_coords['list_size']
    item_size = departments_coords['item_size']
    minLength = list_size[0] * 0.8
    minArea = int(item_size[0] * item_size[1] * 0.8)

    # find split lines
    lines = cv2.HoughLinesP(list_edge_img, 1, np.pi / 180, threshold=100, minLineLength=minLength, maxLineGap=50)
    
    if debug_mode:
        debug_visualize_lines(list_edge_img, lines)
        
    if lines is None:
        raise Exception('! Error: no line was found !')
    horizontal_lines = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if abs(y2 - y1) < 5:  # k approx 0
            horizontal_lines.append(y1)
    if horizontal_lines is None:
        raise Exception('! Error: no horizontal line was found, check debug image !')

    # cut image
    cells = cut_by_lines(list_OCR_img, horizontal_lines, minArea)

    if cells:
        return cells
    raise Exception('! Error: cells is empty. Please check images !')

def dash_page():
    def get_remain_times(dash_img):
        status = []
        for dep, coords in departments_coords['dash_page'].items():
            status.append((dep, department_status(dash_img, coords, dep)))
        return status

    if debug_mode:
        setup_output_directory(OUTPUT_DIR)

    if not is_main_page():
        print(f'[DEBUG dash_page] is_main_page() 返回 False，将抛出 IncorrectPageError')
        print(f'[DEBUG dash_page] departments_coords[\'tech_dep_region\'] = {departments_coords["tech_dep_region"]}')
        print(f'[DEBUG dash_page] 缩放因子 scale_factor = {scale_factor}')
        print(f'[DEBUG dash_page] 请检查 log/ 目录下的 main_page_fail_*.png 截图确认当前画面')
        raise IncorrectPageError()

    dash_img = screenshot('gray', 'department_status')

    status = get_remain_times(dash_img)
    processing_department = set()

    for dep, state in status:
        if state == -1:
            click_position(departments_coords['dash_page'][dep]['free'])
            if _interruptible_sleep(3):
                return []
            keyboard.send('space')
            if _interruptible_sleep(3):
                return []
            state = -2
        if state == -2 and wait_list[dep]:
            # 队列消耗在 craft() 中点击建造后执行，此处仅打开制造列表
            click_position(departments_coords['dash_page'][dep]['free'])
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
            if state == -1 and wait_list[dep]:
                # 刚完成的部门：收集并重新制造
                click_position(departments_coords['dash_page'][dep]['free'])
                if _interruptible_sleep(3):
                    return []
                keyboard.send('space')
                if _interruptible_sleep(3):
                    return []
                click_position(departments_coords['dash_page'][dep]['free'])
                if _interruptible_sleep(3):
                    return []
                list_page(dep)
                if _interruptible_sleep(0.5):
                    return []
                processing_department.add(dep)
                has_new_work = True
            elif state == -2 and wait_list[dep]:
                # 刚空闲的部门：启动制造
                click_position(departments_coords['dash_page'][dep]['free'])
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
            if wait_list[dep]:
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
    category, target = wait_list[department]
    return list_page_operation(department, category, target)

def list_page_operation(department, category, target):
    reference = config['departments'][department][category]
    list_size = departments_coords['list_size']
    list_point = departments_coords['list_point']
    x = list_point[0] + int(list_size[0] / 2)
    y_offset = list_point[1]
    last_top_item = ''
    black_spot = departments_coords['list_black_spot']
    pyautogui.moveTo(black_spot[0], black_spot[1], duration=0.3)

    for k in range(100):
        if _interruptible_sleep(0.05):
            keyboard.send('esc')
            return False
        y1 = 2
        cells = match_list_items()
        # (image, y position)
        img, y1 = cells[0]
        factor = config['OCR_factors'][department]

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
            if debug_mode:
                print(f'{text}, {match}, {score}')
            if match is None:
                continue
            if match == target and score >= factor :
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
    global _global_stop_event
    _global_stop_event = stop_event

    print('###### 程序初始化 ######')
    # 每天首次运行时，从 orzice.com 获取今日制造推荐
    if _HAS_FETCHER:
        try:
            maybe_update_recipes()
        except Exception as e:
            print(f"[WARN] 获取今日配方失败: {e}，将使用现有配置继续")
    else:
        print("[INFO] daily_fetcher 未就绪（缺少依赖？），跳过自动更新")
    background_mode = user_config['background_mode']
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

            set_screen_resolution()
            global departments_coords
            departments_coords = {k: scale_coords(v) for k, v in config['departments_coords'].items()}

            update_wait_list()
            remain_times = dash_page()
            update_wait_list()

            # 报告状态
            if status_callback:
                status_callback(remain_times, wait_list)

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
                    status_callback([0, 0, 0, 0], {k: None for k in wait_list})
                return
            else:
                input('程序异常, 按 *回车* 键退出')
                return
            

def list_OCR_test(department, categories):
    global departments_coords
    departments_coords = {k: scale_coords(v) for k, v in config['departments_coords'].items()}
    hwnd = win32gui.FindWindow('UnrealWindow', '三角洲行动  ')
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    time.sleep(4)
    
    list_size = departments_coords['list_size']
    list_point = departments_coords['list_point']
    x = list_point[0] + int(list_size[0] / 2)
    y_offset = list_point[1]
    factor = config['OCR_factors'][department]

    for category in categories:
        reference = config['departments'][department][category]
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
                    if match == target and score >= factor :
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
                    scroll_down_x4(config['departments_coords']['list_black_spot'])
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
    set_screen_resolution()
    update_wait_list()
    print(wait_list)
    global departments_coords
    departments_coords = {k: scale_coords(v) for k, v in config['departments_coords'].items()}
    write_user_config('tech')
    update_wait_list()
    print(wait_list)


if __name__ == "__main__":
    main()
    # list_OCR_test('tech',['握把'])