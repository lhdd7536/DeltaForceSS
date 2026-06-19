"""
WeGame 账号切换 + 游戏退出工具模块。

纯固定位置点击方案，无密码处理、无 OCR、无滑块验证。
坐标基于 1920×1080 基准，运行时自动缩放。
"""

import time
import os
import random
import ctypes
import psutil
import pyautogui
pyautogui.FAILSAFE = False  # 自动化脚本中禁用角落保护，避免误触中断
import win32gui
import win32process
import win32con
import keyboard
from utils import calc_jitter

# user32 API：SwitchToThisWindow 不受前台窗口权限限制
_user32 = ctypes.windll.user32
_SwitchToThisWindow = _user32.SwitchToThisWindow
_SwitchToThisWindow.argtypes = [ctypes.c_int, ctypes.c_bool]


# ── 随机波动休眠 ────────────────────────────────────────

def _jitter_sleep(seconds):
    """休眠（加入 ±20% 随机波动，最大 30s）"""
    time.sleep(calc_jitter(seconds))


# ── 窗口标识 ──────────────────────────────────────────

GAME_CLASS = 'UnrealWindow'
GAME_TITLE = '三角洲行动  '
WEGAME_EXE = 'wegame.exe'


# ── 坐标缩放 ──────────────────────────────────────────

def _get_scale_factor() -> float:
    """检测当前分辨率并计算缩放因子（基准 1920×1080）"""
    width, height = pyautogui.size()
    return width / 1920


def scale_pos(pos):
    """将 1920×1080 基准坐标缩放到当前分辨率"""
    sf = _get_scale_factor()
    return (int(pos[0] * sf), int(pos[1] * sf))


# ── 鼠标操作 ──────────────────────────────────────────

def click_position(position):
    """移动鼠标并点击（接受缩放前的基准坐标），加入 ±3px 随机偏移"""
    x, y = scale_pos(position)
    x += random.randint(-3, 3)
    y += random.randint(-3, 3)
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.5))
    pyautogui.click()


# ── 窗口操作 ──────────────────────────────────────────

def find_window(class_name, title, timeout=0):
    """查找窗口，可选超时轮询（间隔 0.5 秒）。超时后用 EnumWindows 模糊匹配标题。"""
    elapsed = 0
    interval = 0.5
    while True:
        hwnd = win32gui.FindWindow(class_name, title)
        if hwnd:
            return hwnd
        if timeout > 0 and elapsed < timeout:
            _jitter_sleep(interval)
            elapsed += interval
            continue
        break

    # 超时降级：遍历窗口，模糊匹配标题（容错标题末尾空格等细微差异）
    targets = []
    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if class_name:
            actual_class = win32gui.GetClassName(hwnd)
            if actual_class != class_name:
                return True
        actual_title = win32gui.GetWindowText(hwnd)
        if title and title.strip() and title.strip() in actual_title:
            targets.append(hwnd)
        return True

    win32gui.EnumWindows(enum_callback, None)
    return targets[0] if targets else None


def restore_window(hwnd):
    """恢复并前置窗口（使用 SwitchToThisWindow 绕过前台窗口权限限制）"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    _SwitchToThisWindow(hwnd, True)


def bring_to_foreground(hwnd, max_retries=2):
    """
    将指定窗口置为前台。
    - 第1次：直接尝试 SwitchToThisWindow
    - 若失败：杀 GameInputSvc.exe（常见抢前台进程）后再试 1 次
    返回 True 表示成功，False 表示最终未能置前。
    """
    _, target_pid = win32process.GetWindowThreadProcessId(hwnd)

    def _check():
        fg_hwnd = win32gui.GetForegroundWindow()
        if fg_hwnd and fg_hwnd == hwnd:
            return True
        if fg_hwnd:
            _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            return fg_pid == target_pid
        return False

    # 第一次尝试
    restore_window(hwnd)
    _jitter_sleep(1)
    if _check():
        return True

    fg_title = '<无前台窗口>'
    if fg_hwnd := win32gui.GetForegroundWindow():
        fg_title = win32gui.GetWindowText(fg_hwnd)
    print(f'[wegame] 置前失败，当前前台: "{fg_title}"，杀 GameInputSvc.exe...')

    # 杀 GameInputSvc 后重试
    os.system('taskkill /f /im GameInputSvc.exe >nul 2>&1')
    _jitter_sleep(1)
    restore_window(hwnd)
    _jitter_sleep(1)
    return _check()


def is_window_exist(class_name, title):
    """检查窗口是否存在"""
    return win32gui.FindWindow(class_name, title) != 0


def ensure_wegame_foreground():
    """
    检查 WeGame 是否在前台，若被 GameInputSvc 抢占则自动处理。
    如果暂时找不到窗口（登录切换过渡期），轮询等待最多 3 秒。
    返回 True 表示 WeGame 在前台或已处理，False 表示无法恢复。
    """
    # 轮询等待 WeGame 窗口出现（过渡期窗口可能正在重建）
    wegame_hwnd = None
    for _ in range(6):
        wegame_hwnd = _find_wegame_hwnd()
        if wegame_hwnd:
            break
        _jitter_sleep(0.5)

    if not wegame_hwnd:
        print('[wegame] 无法找到 WeGame 窗口')
        return False

    _, target_pid = win32process.GetWindowThreadProcessId(wegame_hwnd)

    fg_hwnd = win32gui.GetForegroundWindow()
    if fg_hwnd:
        _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
        if fg_pid == target_pid:
            return True  # WeGame 已在前台
        try:
            fg_proc = psutil.Process(fg_pid)
            fg_name = fg_proc.name()
        except Exception:
            fg_name = '?'
        fg_title = win32gui.GetWindowText(fg_hwnd)
        print(f'[wegame] 前台不是 WeGame，当前: {fg_name} - "{fg_title}"')

        # 如果是 GameInputSvc 抢前台 → 杀进程后重新置前
        if fg_name and 'gameinput' in fg_name.lower():
            print(f'[wegame] GameInputSvc 抢前台，自动杀进程...')
            os.system('taskkill /f /im GameInputSvc.exe >nul 2>&1')
            _jitter_sleep(1)
    else:
        print('[wegame] 无前台窗口')

    # 尝试将 WeGame 置前
    if bring_to_foreground(wegame_hwnd):
        print(f'[wegame] 已恢复 WeGame 到前台')
        return True
    else:
        print(f'[wegame] 无法恢复 WeGame 到前台')
        return False


# ── WeGame 管理 ──────────────────────────────────────

def _find_wegame_hwnd():
    """遍历窗口查找 WeGame 句柄（通过标题和进程名双重匹配）"""

    # 先收集 wegame.exe 进程下的所有窗口句柄
    wegame_pids = set()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == 'wegame.exe':
                wegame_pids.add(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    target_hwnds = []  # 属于 wegame.exe 进程的可见窗口

    def enum_callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        # 只匹配属于 wegame.exe 进程的窗口
        if not wegame_pids:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid in wegame_pids:
            target_hwnds.append(hwnd)

    win32gui.EnumWindows(enum_callback, None)
    if not target_hwnds:
        return None

    # 优先返回到标题含 "wegame" 的窗口（主窗口），否则返回第一个
    for hwnd in target_hwnds:
        title = win32gui.GetWindowText(hwnd)
        if title and 'wegame' in title.lower():
            return hwnd
    return target_hwnds[0]


def _find_wegame_path():
    """自动查找 WeGame 安装路径"""
    # 先从正在运行的进程中获取路径
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == 'wegame.exe':
                exe = proc.info.get('exe')
                if exe and os.path.isfile(exe):
                    return exe
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # 常见安装路径
    candidates = [
        os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Tencent', 'wegame', 'wegame.exe'),
        os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Tencent', 'wegame', 'wegame.exe'),
        'H:\\wegame\\wegame.exe',
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    # 遍历各盘符
    for drive in 'DEFGH':
        p = f'{drive}:\\Tencent\\wegame\\wegame.exe'
        if os.path.isfile(p):
            return p
    return None


def activate_wegame(wegame_path=None):
    """
    确保 WeGame 在运行并返回窗口句柄（不强制置顶前台）。
    如果 WeGame 未运行，尝试从指定路径启动。
    返回窗口句柄，失败返回 None。

    改进策略：
    1. 先尝试查找现有窗口（快速路径）
    2. 如果没找到窗口，但进程存在 → 先杀进程再重新启动
    3. 如果既没进程也没窗口 → 直接启动
    """
    # 第一步：尝试查找现有窗口
    wegame_hwnd = None
    for _ in range(6):
        wegame_hwnd = _find_wegame_hwnd()
        if wegame_hwnd:
            title = win32gui.GetWindowText(wegame_hwnd)
            print(f'[wegame] 找到现有窗口: "{title}" hwnd={wegame_hwnd}')
            break
        _jitter_sleep(1)

    if wegame_hwnd:
        if bring_to_foreground(wegame_hwnd):
            print(f'[wegame] 成功置前')
        else:
            print(f'[wegame] 置前失败，继续执行')
        _jitter_sleep(0.5)
        return wegame_hwnd

    # 第二步：没找到窗口 → 先杀残留进程再启动（确保干净环境）
    exit_wegame()
    _jitter_sleep(7)

    # 第三步：启动 WeGame
    if not wegame_path or not os.path.exists(wegame_path):
        wegame_path = _find_wegame_path()
    if wegame_path and os.path.exists(wegame_path):
        print(f'[wegame] 启动: {wegame_path}')
        os.startfile(wegame_path)
        for _ in range(12):  # 最多等 24 秒
            _jitter_sleep(2)
            wegame_hwnd = _find_wegame_hwnd()
            if wegame_hwnd:
                title = win32gui.GetWindowText(wegame_hwnd)
                print(f'[wegame] 启动成功: "{title}"，等待 WeGame 初始化完成...')
                _jitter_sleep(3)  # 等待 WeGame 完全初始化后再置前
                if bring_to_foreground(wegame_hwnd):
                    print(f'[wegame] 成功置前')
                else:
                    print(f'[wegame] 置前失败，继续执行')
                _jitter_sleep(2)  # 等待 WeGame 界面完全渲染稳定
                return wegame_hwnd
        print(f'[wegame] 启动后未检测到窗口（等待超时）')

    return None


# ── 账号点击 ──────────────────────────────────────────

def click_account(position):
    """在 WeGame 登录窗口点击指定账号"""
    click_position(position)
    _jitter_sleep(0.5)


def scroll_then_click(position, scroll_times=1):
    """移动到指定位置 → 向下滚轮 N 次 → 点击（用于第4、5个账号登录）"""
    if scroll_times <= 0:
        click_position(position)
        return
    x, y = scale_pos(position)
    x += random.randint(-3, 3)
    y += random.randint(-3, 3)
    pyautogui.moveTo(x, y, duration=random.uniform(0.2, 0.5))
    _jitter_sleep(0.3)
    for _ in range(scroll_times):
        pyautogui.scroll(-120)
        _jitter_sleep(0.15)
    _jitter_sleep(0.3)
    # 同一位置点击（带随机偏移）
    x2 = x + random.randint(-2, 2)
    y2 = y + random.randint(-2, 2)
    pyautogui.moveTo(x2, y2, duration=random.uniform(0.1, 0.3))
    pyautogui.click()
    _jitter_sleep(0.5)


def click_login(login_btn_pos):
    """点击 WeGame 登录按钮"""
    click_position(login_btn_pos)
    _jitter_sleep(2)


# ── 导航链路（步骤 1-9） ──────────────────────────────

def click_account_management(pos):
    """步骤 1：点击账号管理按钮"""
    click_position(pos)
    _jitter_sleep(1)


def click_game_app(pos):
    """步骤 4：在 WeGame 游戏库中点击三角洲行动应用"""
    click_position(pos)
    _jitter_sleep(1)


def click_launch_btn(pos):
    """步骤 5：点击启动按钮"""
    click_position(pos)
    _jitter_sleep(2)


def click_game_mode(pos):
    """步骤 6：在游戏大厅中点击烽火地带模式"""
    click_position(pos)
    print(f'  已点击烽火地带 {pos}')
    _jitter_sleep(1)


def press_space_x3():
    """步骤 7：按 3 次空格跳过开场动画/弹窗"""
    for _ in range(3):
        keyboard.send('space')
        _jitter_sleep(0.5)


def press_tab():
    """步骤 8：按 Tab 键切换 UI 焦点"""
    keyboard.send('tab')
    _jitter_sleep(0.5)


def click_dash_entry(pos):
    """步骤 9：点击特勤处入口"""
    click_position(pos)
    _jitter_sleep(3)


# ── 游戏窗口 ──────────────────────────────────────────

def wait_game_window(timeout=120):
    """等待三角洲行动游戏窗口出现，返回句柄"""
    hwnd = find_window(GAME_CLASS, GAME_TITLE, timeout=timeout)
    if hwnd:
        _jitter_sleep(3)
    return hwnd


# ── 退出游戏 ──────────────────────────────────────────

def exit_game(method='alt_f4'):
    """退出三角洲行动游戏"""
    if not is_window_exist(GAME_CLASS, GAME_TITLE):
        return

    if method == 'alt_f4':
        hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
        if hwnd:
            restore_window(hwnd)
            _jitter_sleep(0.5)
            keyboard.send('alt+f4')
        _jitter_sleep(2)
    elif method == 'wm_close':
        hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        _jitter_sleep(2)
    elif method == 'taskkill':
        hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
        if hwnd:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            os.system(f'taskkill /f /pid {pid}')
        else:
            os.system(f'taskkill /f /fi "WINDOWTITLE eq {GAME_TITLE}"')
        _jitter_sleep(2)


def wait_game_exit(timeout=30):
    """
    等待游戏窗口关闭。
    超时则 taskkill 强制结束。
    返回 True=正常关闭，False=强制结束。
    """
    elapsed = 0
    interval = 1
    while elapsed < timeout:
        if not is_window_exist(GAME_CLASS, GAME_TITLE):
            return True
        _jitter_sleep(interval)
        elapsed += interval

    # 超时强制结束
    hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
    if hwnd:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        os.system(f'taskkill /f /pid {pid}')
    else:
        os.system(f'taskkill /f /fi "WINDOWTITLE eq {GAME_TITLE}"')
    _jitter_sleep(2)
    return False


def exit_wegame():
    """退出 WeGame 进程（进程不存在时静默）"""
    os.system('taskkill /f /im wegame.exe >nul 2>&1')
    _jitter_sleep(1)
