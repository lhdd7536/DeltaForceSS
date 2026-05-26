"""
WeGame 账号切换 + 游戏退出工具模块。

纯固定位置点击方案，无密码处理、无 OCR、无滑块验证。
坐标基于 1920×1080 基准，运行时自动缩放。
"""

import time
import os
import pyautogui
import win32gui
import win32con
import keyboard


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
    """移动鼠标并点击（接受缩放前的基准坐标）"""
    x, y = scale_pos(position)
    pyautogui.moveTo(x, y, duration=0.3)
    pyautogui.click()


# ── 窗口操作 ──────────────────────────────────────────

def find_window(class_name, title, timeout=0):
    """查找窗口，可选超时轮询（间隔 0.5 秒）"""
    elapsed = 0
    interval = 0.5
    while True:
        hwnd = win32gui.FindWindow(class_name, title)
        if hwnd:
            return hwnd
        if timeout <= 0 or elapsed >= timeout:
            return None
        time.sleep(interval)
        elapsed += interval


def restore_window(hwnd):
    """恢复并前置窗口"""
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)


def is_window_exist(class_name, title):
    """检查窗口是否存在"""
    return win32gui.FindWindow(class_name, title) != 0


# ── WeGame 管理 ──────────────────────────────────────

def activate_wegame(wegame_path=None):
    """
    激活 WeGame 窗口。
    如果 WeGame 未运行，尝试从指定路径启动。
    返回窗口句柄，失败返回 None。
    """
    hwnd = find_window(None, None, timeout=3)

    # 遍历窗口查找 WeGame
    wegame_hwnd = None

    def enum_callback(hwnd, _):
        nonlocal wegame_hwnd
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and 'wegame' in title.lower():
                wegame_hwnd = hwnd
    win32gui.EnumWindows(enum_callback, None)

    if wegame_hwnd:
        restore_window(wegame_hwnd)
        time.sleep(1)
        return wegame_hwnd

    # 未找到，尝试启动
    if wegame_path and os.path.exists(wegame_path):
        os.startfile(wegame_path)
        time.sleep(5)
        # 再次查找
        win32gui.EnumWindows(enum_callback, None)
        if wegame_hwnd:
            restore_window(wegame_hwnd)
            time.sleep(1)
            return wegame_hwnd
        # 如果还是没找到，给更多时间
        time.sleep(5)
        win32gui.EnumWindows(enum_callback, None)
        if wegame_hwnd:
            restore_window(wegame_hwnd)
            time.sleep(1)
            return wegame_hwnd

    return None


# ── 账号点击 ──────────────────────────────────────────

def click_account(position):
    """在 WeGame 登录窗口点击指定账号"""
    click_position(position)
    time.sleep(0.5)


def click_login(login_btn_pos):
    """点击 WeGame 登录按钮"""
    click_position(login_btn_pos)
    time.sleep(2)


# ── 导航链路（步骤 1-9） ──────────────────────────────

def click_account_management(pos):
    """步骤 1：点击账号管理按钮"""
    click_position(pos)
    time.sleep(1)


def click_account_avatar(pos):
    """步骤 12：点击当前账号头像（打开切换用户菜单）"""
    click_position(pos)
    time.sleep(1)


def click_game_app(pos):
    """步骤 4：在 WeGame 游戏库中点击三角洲行动应用"""
    click_position(pos)
    time.sleep(1)


def click_launch_btn(pos):
    """步骤 5：点击启动按钮"""
    click_position(pos)
    time.sleep(2)


def click_game_mode(pos):
    """步骤 6：在游戏大厅中点击烽火地带模式"""
    click_position(pos)
    time.sleep(1)


def press_space_x3():
    """步骤 7：按 3 次空格跳过开场动画/弹窗"""
    for _ in range(3):
        keyboard.send('space')
        time.sleep(0.5)


def press_tab():
    """步骤 8：按 Tab 键切换 UI 焦点"""
    keyboard.send('tab')
    time.sleep(0.5)


def click_dash_entry(pos):
    """步骤 9：点击特勤处入口"""
    click_position(pos)
    time.sleep(3)


def click_switch_user(pos):
    """步骤 13：点击切换用户按钮"""
    click_position(pos)
    time.sleep(2)


# ── 游戏窗口 ──────────────────────────────────────────

def wait_game_window(timeout=120):
    """等待三角洲行动游戏窗口出现，返回句柄"""
    hwnd = find_window(GAME_CLASS, GAME_TITLE, timeout=timeout)
    if hwnd:
        time.sleep(3)
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
            time.sleep(0.5)
            keyboard.send('alt+f4')
        time.sleep(2)
    elif method == 'wm_close':
        hwnd = win32gui.FindWindow(GAME_CLASS, GAME_TITLE)
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        time.sleep(2)
    elif method == 'taskkill':
        os.system(f'taskkill /f /fi "WINDOWTITLE eq {GAME_TITLE}"')
        time.sleep(2)


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
        time.sleep(interval)
        elapsed += interval

    # 超时强制结束
    os.system(f'taskkill /f /fi "WINDOWTITLE eq {GAME_TITLE}"')
    time.sleep(2)
    return False
