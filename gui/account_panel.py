"""
多账号管理面板 - 嵌入 MainWindow 的"多账号"标签页。

管理账号列表、WeGame 配置，按顺序调度多账号自动制造。
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import os
import sys

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pyautogui
import wegame_switcher

ACCOUNTS_FILE = os.path.join(PROJECT_ROOT, 'data', 'accounts.yaml')


def _load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _dump_yaml(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class AccountPanel(ttk.Frame):
    """多账号管理面板"""

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.stop_event = main_window.stop_event
        self.scheduler_thread = None
        self._timer_fired = False
        self._user_stop = False

        self.accounts = []
        self._load_accounts()
        self._build_ui()

    # ── 数据加载/保存 ──────────────────────────────────

    def _load_accounts(self):
        """从 data/accounts.yaml 加载账号和 WeGame 配置"""
        try:
            cfg = _load_yaml(ACCOUNTS_FILE)
            self.accounts = cfg.get('accounts', [])
            self.wegame_cfg = cfg.get('wegame', {})
        except Exception:
            self.accounts = []
            self.wegame_cfg = {}

    def _save_accounts(self):
        """保存账号和 WeGame 配置到 data/accounts.yaml"""
        data = {
            'accounts': self.accounts,
            'wegame': self.wegame_cfg,
        }
        os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
        _dump_yaml(ACCOUNTS_FILE, data)

    def _refresh_list(self):
        """刷新 Treeview 显示"""
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, acc in enumerate(self.accounts, 1):
            enabled = '是' if acc.get('enabled', True) else '否'
            pos = acc.get('click_pos', [0, 0])
            pos_str = f'{pos[0]}, {pos[1]}'
            self.tree.insert('', tk.END, values=(i, acc.get('name', ''), pos_str, enabled),
                             tags=('disabled',) if not acc.get('enabled', True) else ())

    # ── 构建界面 ───────────────────────────────────────

    def _build_ui(self):
        # ── 账号列表 ──
        list_frame = ttk.LabelFrame(self, text='账号列表', padding=4)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        columns = ('#', '名称', '坐标', '启用')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                 height=8, selectmode='browse')
        self.tree.heading('#', text='#')
        self.tree.heading('名称', text='名称')
        self.tree.heading('坐标', text='坐标')
        self.tree.heading('启用', text='启用')
        self.tree.column('#', width=30, anchor=tk.CENTER)
        self.tree.column('名称', width=120)
        self.tree.column('坐标', width=120, anchor=tk.CENTER)
        self.tree.column('启用', width=50, anchor=tk.CENTER)
        self.tree.tag_configure('disabled', foreground='gray')

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击编辑
        self.tree.bind('<Double-1>', lambda e: self._edit_account())

        # ── 账号操作按钮 ──
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(btn_frame, text='+ 添加', command=self._add_account).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(btn_frame, text='编辑', command=self._edit_account).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text='删除', command=self._delete_account).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text='↑ 上移', command=self._move_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text='↓ 下移', command=self._move_down).pack(side=tk.LEFT, padx=2)

        # ── 控制区 ──
        ctrl_frame = ttk.LabelFrame(self, text='控制面板', padding=4)
        ctrl_frame.pack(fill=tk.X, pady=(0, 4))

        ctrl_row = ttk.Frame(ctrl_frame)
        ctrl_row.pack(fill=tk.X, pady=2)
        self.btn_start = ttk.Button(ctrl_row, text='▶ 启动全部', command=self._start_scheduler)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_stop = ttk.Button(ctrl_row, text='⏹ 停止', command=self._stop_scheduler, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_row, text='循环执行', variable=self.loop_var).pack(side=tk.LEFT, padx=(10, 4))

        ttk.Label(ctrl_row, text='每账号时长(秒):').pack(side=tk.LEFT, padx=(10, 2))
        self.timeout_var = tk.StringVar(value=str(self.wegame_cfg.get('account_timeout', 600)))
        self.timeout_entry = ttk.Entry(ctrl_row, width=6, textvariable=self.timeout_var)
        self.timeout_entry.pack(side=tk.LEFT)

        # 当前运行状态
        self.status_label = ttk.Label(ctrl_frame, text='就绪', foreground='gray')
        self.status_label.pack(anchor=tk.W, pady=(2, 0))

        # ── WeGame 配置（13 步坐标） ──
        wg_frame = ttk.LabelFrame(self, text='WeGame 配置（步骤 1-13）', padding=4)
        wg_frame.pack(fill=tk.X, pady=(0, 4))

        # 坐标字段定义: (label, step, config_key, default)
        coord_fields = [
            ('账号管理', '1', 'switch_account_btn_pos', [60, 60]),
            ('当前头像', '12', 'account_avatar_pos', [60, 60]),
            ('登录按钮', '3', 'login_btn_pos', [960, 640]),
            ('三角洲应用', '4', 'game_app_pos', [150, 400]),
            ('启动按钮', '5', 'launch_btn_pos', [960, 800]),
            ('烽火地带', '6', 'mode_btn_pos', [300, 500]),
            ('特勤处入口', '9', 'dash_entry_pos', [600, 350]),
            ('切换用户', '13', 'switch_user_btn_pos', [1200, 100]),
        ]

        self._wg_vars = {}
        for i, (label, step, key, default) in enumerate(coord_fields):
            row = ttk.Frame(wg_frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f'步骤{step} {label}:', width=12).pack(side=tk.LEFT)

            val = self.wegame_cfg.get(key, default)
            x_var = tk.StringVar(value=str(val[0]))
            y_var = tk.StringVar(value=str(val[1]))
            self._wg_vars[key] = (x_var, y_var)

            ttk.Entry(row, width=6, textvariable=x_var).pack(side=tk.LEFT, padx=1)
            ttk.Label(row, text=',').pack(side=tk.LEFT)
            ttk.Entry(row, width=6, textvariable=y_var).pack(side=tk.LEFT, padx=1)
            ttk.Button(row, text='获取',
                       command=lambda vx=x_var, vy=y_var: self._capture_position(vx, vy)
                       ).pack(side=tk.LEFT, padx=(4, 0))

        # 退出方式 + 保存
        wg_bottom = ttk.Frame(wg_frame)
        wg_bottom.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(wg_bottom, text='退出方式:').pack(side=tk.LEFT)
        self.exit_method_var = tk.StringVar(value=self.wegame_cfg.get('exit_method', 'alt_f4'))
        exit_combo = ttk.Combobox(wg_bottom, textvariable=self.exit_method_var,
                                  values=['alt_f4', 'wm_close', 'taskkill'], width=10, state='readonly')
        exit_combo.pack(side=tk.LEFT, padx=2)
        ttk.Button(wg_bottom, text='保存配置', command=self._save_wg_config).pack(side=tk.LEFT, padx=(10, 0))

        # 初始化列表
        self._refresh_list()

    # ── 账号管理 ───────────────────────────────────────

    def _add_account(self):
        """添加账号"""
        dialog = _AccountDialog(self, title='添加账号')
        if dialog.result:
            name, click_pos = dialog.result
            self.accounts.append({
                'name': name,
                'click_pos': click_pos,
                'enabled': True,
            })
            self._save_accounts()
            self._refresh_list()

    def _edit_account(self):
        """编辑选中的账号"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('提示', '请先选择一个账号')
            return
        idx = self.tree.index(sel[0])
        acc = self.accounts[idx]

        dialog = _AccountDialog(self, title='编辑账号', name=acc['name'], click_pos=acc.get('click_pos', [0, 0]))
        if dialog.result:
            name, click_pos = dialog.result
            self.accounts[idx]['name'] = name
            self.accounts[idx]['click_pos'] = click_pos
            self._save_accounts()
            self._refresh_list()

    def _delete_account(self):
        """删除选中的账号"""
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        name = self.accounts[idx].get('name', '')
        if messagebox.askyesno('确认', f'确定删除账号 "{name}"？'):
            del self.accounts[idx]
            self._save_accounts()
            self._refresh_list()

    def _move_up(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx <= 0:
            return
        self.accounts[idx], self.accounts[idx - 1] = self.accounts[idx - 1], self.accounts[idx]
        self._save_accounts()
        self._refresh_list()
        self.tree.selection_set(self.tree.get_children()[idx - 1])

    def _move_down(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx >= len(self.accounts) - 1:
            return
        self.accounts[idx], self.accounts[idx + 1] = self.accounts[idx + 1], self.accounts[idx]
        self._save_accounts()
        self._refresh_list()
        self.tree.selection_set(self.tree.get_children()[idx + 1])

    # ── WeGame 配置 ────────────────────────────────────

    def _save_wg_config(self):
        """保存 WeGame 配置（全部坐标字段）"""
        try:
            # 保存所有坐标字段
            coord_keys = [
                'switch_account_btn_pos', 'account_avatar_pos',
                'login_btn_pos', 'game_app_pos',
                'launch_btn_pos', 'mode_btn_pos', 'dash_entry_pos', 'switch_user_btn_pos',
            ]
            for key in coord_keys:
                if key in self._wg_vars:
                    x_var, y_var = self._wg_vars[key]
                    self.wegame_cfg[key] = [int(x_var.get()), int(y_var.get())]

            self.wegame_cfg['exit_method'] = self.exit_method_var.get()
            try:
                self.wegame_cfg['account_timeout'] = int(self.timeout_var.get())
            except ValueError:
                pass
            self._save_accounts()
            print('[多账号] WeGame 配置已保存')
        except ValueError:
            messagebox.showerror('错误', '坐标必须为数字')

    def _capture_position(self, entry_x, entry_y):
        """3 秒后捕获鼠标位置（不阻塞 GUI）"""
        def capture():
            for i in range(3, 0, -1):
                self.status_label.config(text=f'捕获中: {i} 秒后将鼠标移到目标位置...', foreground='blue')
                time.sleep(1)
            x, y = pyautogui.position()
            self.after(0, lambda: entry_x.set(str(x)))
            self.after(0, lambda: entry_y.set(str(y)))
            self.after(0, lambda: self.status_label.config(text=f'已捕获: ({x}, {y})', foreground='green'))

        threading.Thread(target=capture, daemon=True).start()

    # ── 调度控制 ───────────────────────────────────────

    @property
    def _is_running(self):
        return self.scheduler_thread is not None and self.scheduler_thread.is_alive()

    def _start_scheduler(self):
        if self._is_running:
            return
        if self.main_window.worker_thread and self.main_window.worker_thread.is_alive():
            messagebox.showinfo('提示', '单账号模式正在运行，请先停止')
            return
        if not self.accounts:
            messagebox.showinfo('提示', '请先添加账号')
            return

        # 保存当前配置
        self._save_wg_config()

        self._user_stop = False
        self.stop_event.clear()
        self._set_ui_running(True)
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        print('=== 多账号调度已启动 ===')

    def _stop_scheduler(self):
        print('[多账号] 正在停止...')
        self._user_stop = True
        self.stop_event.set()
        self.status_label.config(text='正在停止...', foreground='orange')

    def _set_ui_running(self, running):
        state = tk.DISABLED if running else tk.NORMAL
        self.btn_start.config(state=state)
        self.btn_stop.config(state=tk.NORMAL if running else tk.DISABLED)

    # ── 调度逻辑（13 步完整流程） ──────────────────────────

    def _login_and_navigate(self, account, wg_cfg):
        """步骤 1-9：完整登录导航流程，成功返回 True"""
        name = account.get('name', '未知')

        # 步骤 1：点击切换账号按钮（可选）
        switch_btn = wg_cfg.get('switch_account_btn_pos')
        if switch_btn:
            print(f'{name}: 步骤1 点击切换账号 {switch_btn}')
            wegame_switcher.click_account_management(switch_btn)

        # 步骤 2：点击账号
        click_pos = account.get('click_pos', [400, 300])
        print(f'{name}: 步骤2 点击账号 {click_pos}')
        wegame_switcher.click_account(click_pos)

        # 步骤 3：点击登录按钮
        login_pos = wg_cfg.get('login_btn_pos', [960, 640])
        print(f'{name}: 步骤3 点击登录 {login_pos}')
        wegame_switcher.click_login(login_pos)

        # 步骤 4：等待 6 秒 → 点击三角洲行动应用
        print(f'{name}: 步骤4 等待 6 秒后点击三角洲应用...')
        if self._wait_check(6):
            return False
        game_pos = wg_cfg.get('game_app_pos', [150, 400])
        wegame_switcher.click_game_app(game_pos)

        # 步骤 5：点击启动按钮
        launch_pos = wg_cfg.get('launch_btn_pos', [960, 800])
        print(f'{name}: 步骤5 点击启动 {launch_pos}')
        wegame_switcher.click_launch_btn(launch_pos)

        # 步骤 6：等待 50 秒 → 点击烽火地带模式
        print(f'{name}: 步骤6 等待游戏加载 50 秒...')
        if not wegame_switcher.wait_game_window(50):
            print(f'{name}: 游戏启动超时，跳过')
            return False
        mode_pos = wg_cfg.get('mode_btn_pos', [300, 500])
        wegame_switcher.click_game_mode(mode_pos)

        # 步骤 7：等待 10 秒 → 按 3 次空格
        print(f'{name}: 步骤7 等待 10 秒后跳过动画...')
        if self._wait_check(10):
            return False
        wegame_switcher.press_space_x3()

        # 步骤 8：按 Tab 键
        print(f'{name}: 步骤8 按 Tab')
        wegame_switcher.press_tab()
        time.sleep(1)

        # 步骤 9：点击特勤处
        dash_pos = wg_cfg.get('dash_entry_pos', [600, 350])
        print(f'{name}: 步骤9 点击特勤处 {dash_pos}')
        wegame_switcher.click_dash_entry(dash_pos)
        return True

    def _prepare_next_account(self, wg_cfg):
        """步骤 12-13：点击当前账号头像 → 切换用户"""
        avatar_pos = wg_cfg.get('account_avatar_pos')
        if avatar_pos:
            print(f'步骤12 点击当前账号头像 {avatar_pos}')
            wegame_switcher.click_account_avatar(avatar_pos)
            time.sleep(1)
        switch_user = wg_cfg.get('switch_user_btn_pos')
        if switch_user:
            print(f'步骤13 点击切换用户 {switch_user}')
            wegame_switcher.click_switch_user(switch_user)

    def _wait_check(self, seconds):
        """等待指定秒数，期间检查停止信号，返回 True=应停止"""
        interval = 0.5
        elapsed = 0
        while elapsed < seconds:
            if self._user_stop:
                return True
            time.sleep(interval)
            elapsed += interval
        return False

    def _run_scheduler(self):
        """在工作线程中运行多账号调度（13 步完整流程）"""
        try:
            self._load_accounts()
            cfg = _load_yaml(ACCOUNTS_FILE)
            accounts = [a for a in cfg.get('accounts', []) if a.get('enabled', True)]
            wg_cfg = cfg.get('wegame', {})
            try:
                timeout = int(self.timeout_var.get())
            except ValueError:
                timeout = 600
            loop_mode = self.loop_var.get()

            if not accounts:
                print('[多账号] 没有已启用的账号')
                return

            while True:
                for account in accounts:
                    if self._user_stop:
                        print('[多账号] 用户已停止')
                        return

                    name = account.get('name', '未知')
                    print(f'=== {name}: 开始 ===')
                    self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 登录中...', foreground='blue'))

                    # 激活 WeGame
                    if not wegame_switcher.activate_wegame():
                        print(f'{name}: 无法找到/启动 WeGame，跳过')
                        self.after(0, lambda n=name: self.status_label.config(text=f'{n}: WeGame 不可用', foreground='red'))
                        continue

                    # 步骤 1-9：登录 + 导航到特勤处
                    if not self._login_and_navigate(account, wg_cfg):
                        print(f'{name}: 导航失败，跳过')
                        self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 导航失败', foreground='red'))
                        continue

                    # 步骤 10：自动制造
                    print(f'{name}: 步骤10 开始制造（{timeout} 秒）')
                    self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 制造中...', foreground='blue'))

                    self.stop_event.clear()
                    self._timer_fired = False

                    timer = threading.Timer(timeout, self._on_timer_fired)
                    timer.daemon = True
                    timer.start()

                    import main as auto_module
                    try:
                        auto_module.main(
                            stop_event=self.stop_event,
                            status_callback=self.main_window.status_queue.put
                        )
                    except Exception as e:
                        print(f'{name}: 制造异常: {e}')
                    finally:
                        timer.cancel()

                    if self._user_stop:
                        print('[多账号] 用户已停止')
                        self._exit_game(wg_cfg.get('exit_method', 'alt_f4'))
                        return

                    # 步骤 11：退出游戏
                    print(f'{name}: 步骤11 退出游戏')
                    self._exit_game(wg_cfg.get('exit_method', 'alt_f4'))

                    # 步骤 12-13：准备下一个账号
                    self._prepare_next_account(wg_cfg)

                    print(f'{name}: 完成')
                    self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 已完成', foreground='green'))

                if not loop_mode:
                    break
                print('[多账号] 循环模式：所有账号已完成，重新开始')

        except Exception as e:
            print(f'[多账号] 调度异常: {e}')
        finally:
            self.after(0, self._on_scheduler_stopped)

    def _exit_game(self, exit_method):
        """退出游戏（带超时强制结束）"""
        try:
            wegame_switcher.exit_game(exit_method)
            wegame_switcher.wait_game_exit(30)
        except Exception as e:
            print(f'[多账号] 退出游戏异常: {e}')

    def _on_timer_fired(self):
        """账号超时回调"""
        self._timer_fired = True
        self.stop_event.set()
        print('[多账号] 当前账号制造时间到，准备切换')

    def _on_scheduler_stopped(self):
        """调度线程结束"""
        self._set_ui_running(False)
        self.status_label.config(text='已停止', foreground='gray')
        print('=== 多账号调度已停止 ===')
        self.main_window._refresh_recipe_display()


# ── 账号添加/编辑对话框 ──────────────────────────────

class _AccountDialog(tk.Toplevel):
    """添加/编辑账号的模态对话框"""

    def __init__(self, parent, title='账号', name='', click_pos=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None

        self._click_pos = click_pos or [0, 0]

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # 名称
        ttk.Label(frame, text='名称:').grid(row=0, column=0, sticky=tk.W, pady=4)
        self.name_var = tk.StringVar(value=name)
        ttk.Entry(frame, width=24, textvariable=self.name_var).grid(row=0, column=1, columnspan=2, pady=4)

        # 坐标
        ttk.Label(frame, text='点击坐标:').grid(row=1, column=0, sticky=tk.W, pady=4)
        self.x_var = tk.StringVar(value=str(self._click_pos[0]))
        ttk.Entry(frame, width=8, textvariable=self.x_var).grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(frame, text=',').grid(row=1, column=1, pady=4, padx=(50, 0))
        self.y_var = tk.StringVar(value=str(self._click_pos[1]))
        ttk.Entry(frame, width=8, textvariable=self.y_var).grid(row=1, column=2, sticky=tk.W, pady=4)

        ttk.Button(frame, text='获取鼠标位置',
                   command=self._capture).grid(row=2, column=0, columnspan=3, pady=4)

        self.capture_status = ttk.Label(frame, text='', foreground='gray')
        self.capture_status.grid(row=3, column=0, columnspan=3, pady=(0, 4))

        # 按钮
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=4, column=0, columnspan=3, pady=(8, 0))
        ttk.Button(btn_row, text='确定', command=self._ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text='取消', command=self.destroy).pack(side=tk.LEFT, padx=4)

        # 模态
        self.grab_set()
        self.wait_window()

    def _capture(self):
        """3 秒后捕获鼠标位置"""
        def capture():
            for i in range(3, 0, -1):
                self.capture_status.config(text=f'将在 {i} 秒后捕获，请移动鼠标...')
                time.sleep(1)
            x, y = pyautogui.position()
            self.after(0, lambda: self.x_var.set(str(x)))
            self.after(0, lambda: self.y_var.set(str(y)))
            self.after(0, lambda: self.capture_status.config(text=f'已捕获: ({x}, {y})', foreground='green'))

        threading.Thread(target=capture, daemon=True).start()

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror('错误', '请输入名称', parent=self)
            return
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
        except ValueError:
            messagebox.showerror('错误', '坐标必须为数字', parent=self)
            return
        self.result = (name, [x, y])
        self.destroy()
