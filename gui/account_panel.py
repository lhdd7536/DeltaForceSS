"""
多账号管理面板 - 嵌入 MainWindow 的"多账号"标签页。

管理账号列表、WeGame 配置，按顺序调度多账号自动制造。
"""

import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import random
import traceback
from datetime import datetime, timedelta
import os
import sys
import win32gui
import win32process
import psutil

from ruamel.yaml import YAML
_yaml_dumper = YAML()
_yaml_dumper.indent(mapping=2, sequence=4, offset=2)
_yaml_dumper.preserve_quotes = True

if getattr(sys, 'frozen', False):
    # PyInstaller EXE 模式：使用 EXE 所在目录
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    # 源码模式：使用项目根目录
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pyautogui
import wegame_switcher
from utils import jitter_sleep, read_with_encoding_fallback
import replenishment


ACCOUNTS_FILE = os.path.join(PROJECT_ROOT, 'data', 'accounts.yaml')
USER_CONFIG_FILE = os.path.join(PROJECT_ROOT, 'user_config.yaml')


def _load_yaml(path):
    data = _yaml_dumper.load(read_with_encoding_fallback(path))
    return data or {}


def _dump_yaml(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        _yaml_dumper.dump(data, f)


class AccountPanel(ttk.Frame):
    """多账号管理面板"""

    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.stop_event = main_window.stop_event
        self.scheduler_thread = None
        self._schedule_thread = None
        self._schedule_lock = threading.Lock()
        self._user_stop = False
        self.next_cycle_time = None
        self._cycle_has_failure = False
        self._retry_count = 0
        self._max_retries = 3

        self.accounts = []
        self._load_accounts()
        self._auto_run_hour = self._load_auto_hour()
        # 补货配置
        self._auto_replenish = self._load_auto_replenish()
        self._replenish_after_cycle = False
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

    def _load_auto_hour(self):
        """从 user_config.yaml 加载自动执行截止小时"""
        try:
            cfg = _load_yaml(USER_CONFIG_FILE)
            return int(cfg.get('auto_run_until_hour', 10))
        except Exception:
            return 10

    def _load_auto_replenish(self):
        """从 user_config.yaml 加载自动补货配置"""
        try:
            cfg = _load_yaml(USER_CONFIG_FILE)
            return cfg.get('auto_replenish', {'enabled': False, 'threshold': 3, 'quantity': 3})
        except Exception:
            return {'enabled': False, 'threshold': 3, 'quantity': 3}

    def _save_user_config(self):
        """保存 auto_run_until_hour 到 user_config.yaml"""
        try:
            cfg = _load_yaml(USER_CONFIG_FILE)
            cfg['auto_run_until_hour'] = self._auto_run_hour
            cfg['auto_replenish'] = {
                'enabled': self._replenish_var.get(),
                'threshold': int(self._replenish_threshold_var.get()),
                'quantity': int(self._replenish_qty_var.get()),
            }
            _dump_yaml(USER_CONFIG_FILE, cfg)
        except Exception as e:
            print(f'[多账号] 保存 auto_run_until_hour 失败: {e}')

    def _refresh_list(self):
        """刷新 Treeview 显示"""
        for row in self.tree.get_children():
            self.tree.delete(row)
        for i, acc in enumerate(self.accounts, 1):
            enabled = '是' if acc.get('enabled', True) else '否'
            pos = acc.get('click_pos', [0, 0])
            pos_str = f'{pos[0]}, {pos[1]}'
            end_time = acc.get('estimated_end', '') or ''
            scroll = acc.get('scroll_before_click', 0)
            self.tree.insert('', tk.END, values=(i, acc.get('name', ''), pos_str, scroll, enabled, end_time),
                             tags=('disabled',) if not acc.get('enabled', True) else ())

    # ── 构建界面 ───────────────────────────────────────

    def _build_ui(self):
        # ── 账号列表 ──
        list_frame = ttk.LabelFrame(self, text='账号列表', padding=4)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        columns = ('#', '名称', '坐标', '滚轮', '启用', '完成时间')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                                 height=8, selectmode='browse')
        self.tree.heading('#', text='#')
        self.tree.heading('名称', text='名称')
        self.tree.heading('坐标', text='坐标')
        self.tree.heading('滚轮', text='滚轮')
        self.tree.heading('启用', text='启用')
        self.tree.heading('完成时间', text='完成时间')
        self.tree.column('#', width=30, anchor=tk.CENTER)
        self.tree.column('名称', width=120)
        self.tree.column('坐标', width=110, anchor=tk.CENTER)
        self.tree.column('滚轮', width=50, anchor=tk.CENTER)
        self.tree.column('启用', width=50, anchor=tk.CENTER)
        self.tree.column('完成时间', width=80, anchor=tk.CENTER)
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
        ttk.Button(btn_frame, text='启用/禁用', command=self._toggle_enabled).pack(side=tk.LEFT, padx=2)

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
        ttk.Checkbutton(ctrl_row, text='循环执行', variable=self.loop_var, command=self._on_loop_toggle).pack(side=tk.LEFT, padx=(10, 4))

        ttk.Label(ctrl_row, text='循环间隔(秒):').pack(side=tk.LEFT, padx=(10, 2))
        self.loop_interval_var = tk.StringVar(value=str(self.wegame_cfg.get('loop_interval', 28800)))
        ttk.Entry(ctrl_row, width=7, textvariable=self.loop_interval_var).pack(side=tk.LEFT)

        ttk.Label(ctrl_row, text='自动执行至时:').pack(side=tk.LEFT, padx=(10, 2))
        self.auto_hour_var = tk.StringVar(value=str(self._auto_run_hour))
        auto_spin = ttk.Spinbox(ctrl_row, from_=0, to=23, width=3,
                                textvariable=self.auto_hour_var, command=self._on_auto_hour_changed)
        auto_spin.pack(side=tk.LEFT)
        auto_spin.bind('<FocusOut>', lambda e: self._on_auto_hour_changed())
        auto_spin.bind('<Return>', lambda e: self._on_auto_hour_changed())

        # ── 自动补货配置 ──
        ttk.Separator(ctrl_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4))
        self._replenish_var = tk.BooleanVar(value=self._auto_replenish.get('enabled', False))
        ttk.Checkbutton(ctrl_row, text='每日2-5点自动补货',
                        variable=self._replenish_var,
                        command=self._save_user_config).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Label(ctrl_row, text='阈值:').pack(side=tk.LEFT, padx=(4, 2))
        self._replenish_threshold_var = tk.StringVar(
            value=str(self._auto_replenish.get('threshold', 3)))
        ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
                    textvariable=self._replenish_threshold_var,
                    command=self._save_user_config).pack(side=tk.LEFT)

        ttk.Label(ctrl_row, text='补货量:').pack(side=tk.LEFT, padx=(4, 2))
        self._replenish_qty_var = tk.StringVar(
            value=str(self._auto_replenish.get('quantity', 3)))
        ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
                    textvariable=self._replenish_qty_var,
                    command=self._save_user_config).pack(side=tk.LEFT)

        self.next_cycle_label = ttk.Label(ctrl_row, text='', foreground='gray')
        self.next_cycle_label.pack(side=tk.LEFT, padx=(10, 0))

        # 当前运行状态
        self.status_label = ttk.Label(ctrl_frame, text='就绪', foreground='gray')
        self.status_label.pack(anchor=tk.W, pady=(2, 0))

        # ── WeGame 配置（按阶段分组，支持滚动） ──
        wg_outer = ttk.LabelFrame(self, text='WeGame 配置', padding=4)
        wg_outer.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        # 可滚动画布
        wg_canvas = tk.Canvas(wg_outer, borderwidth=0, highlightthickness=0)
        wg_scrollbar = ttk.Scrollbar(wg_outer, orient=tk.VERTICAL, command=wg_canvas.yview)
        wg_inner = ttk.Frame(wg_canvas)
        wg_inner.bind('<Configure>', lambda e: wg_canvas.configure(scrollregion=wg_canvas.bbox('all')))
        wg_canvas.create_window((0, 0), window=wg_inner, anchor='nw')
        wg_canvas.configure(yscrollcommand=wg_scrollbar.set)

        wg_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        wg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 鼠标滚轮绑定（进入区域时启用，离开时禁用，避免干扰其他区域）
        def _on_mousewheel(event):
            wg_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        wg_canvas.bind('<Enter>', lambda e: wg_canvas.bind_all('<MouseWheel>', _on_mousewheel))
        wg_canvas.bind('<Leave>', lambda e: wg_canvas.unbind_all('<MouseWheel>'))

        self._wg_vars = {}
        self._wait_vars = {}

        def _add_coord_row(parent, step, label, key, default):
            """添加一行坐标配置"""
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=f'步骤{step} {label}:', width=14).pack(side=tk.LEFT)
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

        def _add_wait_row(parent, label, key, default):
            """添加一行等待时长配置"""
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, width=14).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(self.wegame_cfg.get(key, default)))
            self._wait_vars[key] = var
            ttk.Entry(row, width=6, textvariable=var).pack(side=tk.LEFT, padx=1)
            ttk.Label(row, text='秒').pack(side=tk.LEFT)

        wg_inner.columnconfigure(0, weight=1)
        wg_inner.columnconfigure(1, weight=1)

        # ── 登录阶段（步骤 1-3） ──
        phase1 = ttk.LabelFrame(wg_inner, text='登录阶段（步骤 1-3）', padding=4)
        phase1.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        _add_coord_row(phase1, '1', '账号管理', 'switch_account_btn_pos', [60, 60])
        ttk.Label(phase1, text='步骤2 点击账号:  从上方账号列表中选择').pack(anchor=tk.W, pady=1)
        _add_coord_row(phase1, '3', '登录按钮', 'login_btn_pos', [960, 640])

        # ── 启动阶段（步骤 4-5） ──
        phase2 = ttk.LabelFrame(wg_inner, text='启动阶段（步骤 4-5）', padding=4)
        phase2.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        _add_coord_row(phase2, '4', '三角洲应用', 'game_app_pos', [150, 400])
        _add_wait_row(phase2, '     等待:', 'wait_before_app', 6)
        _add_coord_row(phase2, '5', '启动按钮', 'launch_btn_pos', [960, 800])

        # ── 导航阶段（步骤 6-9） ──
        phase3 = ttk.LabelFrame(wg_inner, text='导航阶段（步骤 6-9）', padding=4)
        phase3.grid(row=1, column=0, sticky='nsew', padx=2, pady=2)
        _add_coord_row(phase3, '6', '烽火地带', 'mode_btn_pos', [300, 500])
        _add_wait_row(phase3, '     游戏加载等待:', 'wait_game_launch', 80)
        ttk.Label(phase3, text='步骤7 按空格:  (自动执行，跳过开场动画)').pack(anchor=tk.W, pady=1)
        _add_wait_row(phase3, '     跳动画前等待:', 'wait_before_space', 10)
        ttk.Label(phase3, text='步骤8 按 Tab:  (自动执行)').pack(anchor=tk.W, pady=1)
        _add_coord_row(phase3, '9', '特勤处入口', 'dash_entry_pos', [600, 350])

        # ── 退出阶段（步骤 11） ──
        phase4 = ttk.LabelFrame(wg_inner, text='退出阶段（步骤 11）', padding=4)
        phase4.grid(row=1, column=1, sticky='nsew', padx=2, pady=2)
        exit_row = ttk.Frame(phase4)
        exit_row.pack(fill=tk.X, pady=1)
        ttk.Label(exit_row, text='退出方式:', width=14).pack(side=tk.LEFT)
        self.exit_method_var = tk.StringVar(value=self.wegame_cfg.get('exit_method', 'taskkill'))
        exit_combo = ttk.Combobox(exit_row, textvariable=self.exit_method_var,
                                  values=['alt_f4', 'wm_close', 'taskkill'], width=10, state='readonly')
        exit_combo.pack(side=tk.LEFT, padx=2)

        # WeGame 路径
        path_row = ttk.Frame(wg_inner)
        ttk.Label(path_row, text='WeGame 路径:', width=14).pack(side=tk.LEFT)
        self.wegame_path_var = tk.StringVar(value=self.wegame_cfg.get('wegame_path', ''))
        ttk.Entry(path_row, width=50, textvariable=self.wegame_path_var).pack(side=tk.LEFT, padx=1)
        path_row.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(4, 0))

        # 保存按钮
        save_row = ttk.Frame(wg_inner)
        save_row.grid(row=4, column=0, columnspan=2, sticky='e', pady=(4, 0))
        ttk.Button(save_row, text='保存配置', command=self._save_wg_config).pack(side=tk.RIGHT)

        # 初始化列表
        self._refresh_list()
        # 启动下次执行时间刷新
        self._poll_next_cycle()

    # ── 账号管理 ───────────────────────────────────────

    def _add_account(self):
        """添加账号"""
        dialog = _AccountDialog(self, title='添加账号')
        if dialog.result:
            name, click_pos, scroll = dialog.result
            self.accounts.append({
                'name': name,
                'click_pos': click_pos,
                'scroll_before_click': scroll,
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

        dialog = _AccountDialog(self, title='编辑账号',
                                name=acc['name'],
                                click_pos=acc.get('click_pos', [0, 0]),
                                scroll_before_click=acc.get('scroll_before_click', 0))
        if dialog.result:
            name, click_pos, scroll = dialog.result
            self.accounts[idx]['name'] = name
            self.accounts[idx]['click_pos'] = click_pos
            self.accounts[idx]['scroll_before_click'] = scroll
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

    def _toggle_enabled(self):
        """切换选中账号的启用/禁用状态"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('提示', '请先选择一个账号')
            return
        idx = self.tree.index(sel[0])
        self.accounts[idx]['enabled'] = not self.accounts[idx].get('enabled', True)
        status = '启用' if self.accounts[idx]['enabled'] else '禁用'
        print(f'[多账号] 账号 "{self.accounts[idx]["name"]}" 已{status}')
        self._save_accounts()
        self._refresh_list()

    # ── 自动执行时段 ────────────────────────────────────

    def _on_auto_hour_changed(self):
        """保存 auto_run_until_hour 到 user_config.yaml"""
        try:
            val = int(self.auto_hour_var.get())
            self._auto_run_hour = max(0, min(23, val))
            self.auto_hour_var.set(str(self._auto_run_hour))
            self._save_user_config()
            print(f'[多账号] 自动执行截止时已设为 {self._auto_run_hour} 时')
        except ValueError:
            pass

    # ── WeGame 配置 ────────────────────────────────────

    def _save_wg_config(self):
        """保存 WeGame 配置（全部坐标字段 + 等待时长）"""
        try:
            # 保存所有坐标字段
            coord_keys = [
                'switch_account_btn_pos', 'login_btn_pos', 'game_app_pos',
                'launch_btn_pos', 'mode_btn_pos', 'dash_entry_pos',
            ]
            for key in coord_keys:
                if key in self._wg_vars:
                    x_var, y_var = self._wg_vars[key]
                    self.wegame_cfg[key] = [int(x_var.get()), int(y_var.get())]

            # 保存等待时长
            for key in self._wait_vars:
                try:
                    self.wegame_cfg[key] = int(self._wait_vars[key].get())
                except ValueError:
                    pass

            self.wegame_cfg['loop_interval'] = int(self.loop_interval_var.get())
            self.wegame_cfg['exit_method'] = self.exit_method_var.get()
            self.wegame_cfg['wegame_path'] = self.wegame_path_var.get()
            self._save_accounts()
            print('[多账号] WeGame 配置已保存')
        except ValueError:
            messagebox.showerror('错误', '坐标必须为数字')

    def _capture_position(self, entry_x, entry_y):
        """3 秒后捕获鼠标位置（不阻塞 GUI）"""
        def capture():
            for i in range(3, 0, -1):
                self.status_label.config(text=f'捕获中: {i} 秒后将鼠标移到目标位置...', foreground='blue')
                jitter_sleep(1)
            x, y = pyautogui.position()
            self.after(0, lambda: entry_x.set(str(x)))
            self.after(0, lambda: entry_y.set(str(y)))
            self.after(0, lambda: self.status_label.config(text=f'已捕获: ({x}, {y})', foreground='green'))

        threading.Thread(target=capture, daemon=True).start()

    # ── 调度控制 ───────────────────────────────────────

    @property
    def _is_running(self):
        return self.scheduler_thread is not None and self.scheduler_thread.is_alive()

    @property
    def _is_monitoring(self):
        return self._schedule_thread is not None and self._schedule_thread.is_alive()

    # ── 循环执行（预约监控） ─────────────────────────────

    def _on_loop_toggle(self):
        """循环执行复选框切换：启动/停止预约监控"""
        if self.loop_var.get():
            if self._is_running:
                print('[多账号] 当前正在执行，预约将在本轮完成后生效')
                return
            if self._is_monitoring:
                return
            self._start_schedule_monitor()
        else:
            self._stop_schedule_monitor()

    def _replenish_watchdog(self):
        """2 点定时器：休眠到每天 2:00，检查补货条件"""
        while not self._user_stop:
            now = datetime.now()
            next_2am = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now >= next_2am:
                next_2am += timedelta(days=1)
            sleep_seconds = (next_2am - now).total_seconds()

            # 可中断休眠到下次 2:00
            if self._wait_check(sleep_seconds):
                return

            # 读取最新配置
            self._auto_replenish = self._load_auto_replenish()
            if not self._auto_replenish.get('enabled', False):
                print('[补货] 自动补货未启用，跳过')
                continue

            print(f'[补货] 2:00 定时触发，检查调度状态...')

            if self._is_running:
                # 情况①：制造循环正在运行 → 等制造完再补
                print('[补货] 制造进行中，标记"制造完成后补货"')
                self._replenish_after_cycle = True
            else:
                # 计算下次制造预约时间
                self._load_accounts()
                enabled = [a for a in self.accounts if a.get('enabled', True)]
                if enabled:
                    next_mfg = self._calc_next_cycle_time(enabled)
                    next_mfg_dt = datetime.fromtimestamp(next_mfg)
                    if next_mfg_dt.hour >= 3:
                        # 情况②：3 点后才预约 → 直接补货
                        print(f'[补货] 下次制造预约在 {next_mfg_dt.hour}:{next_mfg_dt.minute:02d}（3 点后），直接补货')
                        self._start_replenish_cycle()
                    else:
                        # 情况③：3 点前有预约 → 等制造完再补
                        print(f'[补货] 下次制造预约在 {next_mfg_dt.hour}:{next_mfg_dt.minute:02d}（3 点前），等制造完补货')
                        self._replenish_after_cycle = True
                else:
                    # 没有启用账号或没有预约 → 直接补货
                    print('[补货] 无制造预约，直接开始补货')
                    self._start_replenish_cycle()

    def _schedule_monitor_thread(self):
        """预约监控：等待 → 弹窗确认 → 启动一轮 → 重复"""
        try:
            while self.loop_var.get() and not self._user_stop:
                self._load_accounts()
                accounts = [a for a in self.accounts if a.get('enabled', True)]
                if not accounts:
                    print('[多账号] 没有已启用的账号，预约监控退出')
                    break

                # 计算下次执行时间
                next_ts = self._calc_next_cycle_time(accounts)
                remaining = max(0, next_ts - time.time())
                self.next_cycle_time = next_ts

                if remaining > 1:
                    print(f'[多账号] 预约等待：距下次执行还有 {remaining:.0f} 秒')
                    self.after(0, lambda: self.status_label.config(text='预约等待中...', foreground='orange'))
                    # 可中断等待，同时检测循环执行是否被取消
                    interval = 0.5
                    waited = 0
                    while waited < remaining:
                        if self._user_stop or not self.loop_var.get():
                            return
                        jitter_sleep(interval)
                        waited += interval
                elif remaining > 0:
                    jitter_sleep(1)

                if self._user_stop or not self.loop_var.get():
                    return

                # 弹窗确认（auto_run_until_hour 之前自动执行，不弹窗）
                now_hour = datetime.now().hour
                if now_hour <= self._auto_run_hour:
                    print(f'[多账号] {self._auto_run_hour} 时前自动执行，跳过弹窗')
                elif not self._confirm_next_cycle():
                    break

                # 启动一轮制造
                self._start_one_cycle()

                # 等待本轮制造完成
                while self._is_running:
                    if self._user_stop or not self.loop_var.get():
                        return
                    jitter_sleep(1)

                if self._user_stop:
                    return
        finally:
            self.next_cycle_time = None
            self.after(0, lambda: self.status_label.config(text='预约已停止', foreground='gray'))
            with self._schedule_lock:
                self._schedule_thread = None

    def _get_next_run_time(self, accounts):
        """取所有账号中最晚完成时间 + 1 分钟，返回 datetime，失败返回 None"""
        now = datetime.now()
        latest = None
        for acc in accounts:
            est = acc.get('estimated_end', '') or ''
            if est and est != '—':
                try:
                    t = datetime.strptime(est, '%H:%M')
                    dt = now.replace(hour=t.hour, minute=t.minute, second=0)
                    if latest is None or dt > latest:
                        latest = dt
                except ValueError:
                    pass
        if latest is not None:
            latest += timedelta(minutes=1)
            if latest <= now:
                latest += timedelta(days=1)
        return latest

    def _calc_next_cycle_time(self, accounts):
        """计算下次执行时间戳（降级用固定间隔）"""
        next_dt = self._get_next_run_time(accounts)
        if next_dt:
            return next_dt.timestamp()
        return time.time() + int(self.wegame_cfg.get('loop_interval', 28800))

    def _start_schedule_monitor(self):
        """启动预约监控线程"""
        if self._is_monitoring:
            return
        self._user_stop = False
        self.stop_event.clear()
        self._schedule_thread = threading.Thread(target=self._schedule_monitor_thread, daemon=True)
        self._schedule_thread.start()

        if not hasattr(self, '_replenish_watchdog_thread') or not self._replenish_watchdog_thread.is_alive():
            self._replenish_watchdog_thread = threading.Thread(
                target=self._replenish_watchdog, daemon=True)
            self._replenish_watchdog_thread.start()
        print('[多账号] 预约监控已启动')
        self.after(0, lambda: self.status_label.config(text='预约监控中...', foreground='blue'))

    def _stop_schedule_monitor(self):
        """停止预约监控（loop_var 已由复选框置 False，监控线程自行退出）"""
        with self._schedule_lock:
            if self._schedule_thread:
                print('[多账号] 预约监控已停止')
            self._schedule_thread = None

    # ── 手动启动 ─────────────────────────────────────────

    def _start_one_cycle(self):
        """内部启动一轮制造（被预约监控调用）"""
        self._user_stop = False
        self.stop_event.clear()
        self._set_ui_running(True)
        self.scheduler_thread = threading.Thread(target=self._run_one_cycle, daemon=True)
        self.scheduler_thread.start()

    def _start_scheduler(self):
        """手动启动全部：立即执行一轮，停止预约监控"""
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
        # 停止预约监控（取消勾选，让监控线程自行退出）
        if self._is_monitoring:
            self.loop_var.set(False)

        self._user_stop = False
        self.stop_event.clear()
        self._set_ui_running(True)
        self.scheduler_thread = threading.Thread(target=self._run_one_cycle, daemon=True)
        self.scheduler_thread.start()

        # 启动补货看门狗（守护线程）
        self._replenish_watchdog_thread = threading.Thread(
            target=self._replenish_watchdog, daemon=True)
        self._replenish_watchdog_thread.start()
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

    def _login_and_navigate(self, account, wg_cfg):
        """步骤 1-9：完整登录导航流程，成功返回 True"""
        name = account.get('name', '未知')

        # 步骤 1：点击切换账号按钮（可选）
        switch_btn = wg_cfg.get('switch_account_btn_pos')
        if switch_btn:
            print(f'{name}: 步骤1 点击切换账号 {switch_btn}')
            wegame_switcher.click_account_management(switch_btn)
            jitter_sleep(1)

        # 步骤 2：点击账号（scroll_before_click > 0 时先在同一位置向下滚动）
        click_pos = account.get('click_pos', [400, 300])
        scroll_times = int(account.get('scroll_before_click', 0) or 0)
        if scroll_times > 0:
            print(f'{name}: 步骤2 账号列表滚轮 {scroll_times} 次后点击 {click_pos}')
            wegame_switcher.scroll_then_click(click_pos, scroll_times)
        else:
            print(f'{name}: 步骤2 点击账号 {click_pos}')
            wegame_switcher.click_account(click_pos)

        # 步骤 3：点击登录按钮
        login_pos = wg_cfg.get('login_btn_pos', [960, 640])
        print(f'{name}: 步骤3 点击登录 {login_pos}')
        wegame_switcher.click_login(login_pos)

        # 步骤 4：等待 → 点击三角洲行动应用
        wait_before_app = int(wg_cfg.get('wait_before_app', 6))
        print(f'{name}: 步骤4 等待 {wait_before_app} 秒后点击三角洲应用...')
        if self._wait_check(wait_before_app):
            return False
        # 以前台进程为依据：若 GameInputSvc 抢前台则杀进程
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
            fg_title = win32gui.GetWindowText(fg_hwnd)
            fg_proc = psutil.Process(fg_pid)
            fg_name = fg_proc.name()
            print(f'{name}: 点击三角洲应用前前台进程 [PID={fg_pid}] {fg_name} - "{fg_title}"')
            if 'gameinput' in fg_name.lower():
                print(f'{name}: GameInputSvc 抢前台，自动杀进程...')
                wegame_switcher._hide_cmd('taskkill /f /im GameInputSvc.exe >nul 2>&1')
                jitter_sleep(1)
        except Exception as e:
            print(f'{name}: 获取前台进程信息失败: {e}')
        jitter_sleep(0.5)
        game_pos = wg_cfg.get('game_app_pos', [150, 400])
        wegame_switcher.click_game_app(game_pos)

        # 步骤 5：点击启动按钮
        launch_pos = wg_cfg.get('launch_btn_pos', [960, 800])
        print(f'{name}: 步骤5 点击启动 {launch_pos}')
        wegame_switcher.click_launch_btn(launch_pos)

        # 步骤 6：等待游戏加载 → 点击烽火地带模式
        # 分两阶段：① 轮询直到窗口出现 ② 继续等待剩余时间让游戏完全加载
        wait_launch = int(wg_cfg.get('wait_game_launch', 80))
        launch_start = time.time()
        print(f'{name}: 等待游戏加载（最长 {wait_launch} 秒）...')
        hwnd = None
        while time.time() - launch_start < wait_launch:
            if self._user_stop:
                print(f'{name}: 用户停止')
                return False
            hwnd = wegame_switcher.find_window(wegame_switcher.GAME_CLASS, wegame_switcher.GAME_TITLE)
            if hwnd:
                elapsed = int(time.time() - launch_start)
                print(f'{name}: 游戏窗口已出现（耗时 {elapsed} 秒），剩余等待游戏加载...')
                break
            elapsed = int(time.time() - launch_start)
            if elapsed > 0 and elapsed % 10 == 0:
                print(f'{name}: 等待游戏启动 {elapsed}/{wait_launch} 秒...')
            jitter_sleep(1)

        if not hwnd:
            print(f'{name}: 游戏窗口未找到，跳过')
            return False

        # 等满 wait_launch 总时间，让游戏加载到主菜单
        remaining = wait_launch - int(time.time() - launch_start)
        if remaining > 0:
            print(f'{name}: 继续等待游戏加载（剩余 {remaining} 秒）...')
            if self._wait_check(remaining):
                return False

        wegame_switcher.bring_to_foreground(hwnd)
        jitter_sleep(1)
        mode_pos = wg_cfg.get('mode_btn_pos', [300, 500])
        wegame_switcher.click_game_mode(mode_pos)
        jitter_sleep(1)
        wegame_switcher.click_game_mode(mode_pos)
        print(f'{name}: 步骤6 已双击烽火地带 {mode_pos}')

        # 步骤 7：等待 → 按 3 次空格跳过动画
        wait_space = int(wg_cfg.get('wait_before_space', 10))
        print(f'{name}: 步骤7 等待 {wait_space} 秒后跳过动画...')
        if self._wait_check(wait_space):
            return False
        wegame_switcher.press_space_x3()

        # 步骤 8：按 Tab 键
        print(f'{name}: 步骤8 按 Tab')
        wegame_switcher.press_tab()
        jitter_sleep(1)

        # 步骤 9：点击特勤处
        dash_pos = wg_cfg.get('dash_entry_pos', [600, 350])
        print(f'{name}: 步骤9 点击特勤处 {dash_pos}')
        wegame_switcher.click_dash_entry(dash_pos)
        return True

    def _wait_check(self, seconds):
        """等待指定秒数，期间检查停止信号，返回 True=应停止"""
        interval = 0.5
        elapsed = 0
        while elapsed < seconds:
            if self._user_stop:
                return True
            jitter_sleep(interval)
            elapsed += interval
        return False

    def _poll_next_cycle(self):
        """每秒刷新下次执行时间显示（使用监控线程计算的时间）"""
        next_str = None
        if self.next_cycle_time:
            next_dt = datetime.fromtimestamp(self.next_cycle_time)
            next_str = next_dt.strftime('%H:%M:%S')
        self.next_cycle_label.config(text=f'下次执行: {next_str}' if next_str else '')
        self.after(1000, self._poll_next_cycle)

    def _confirm_next_cycle(self):
        """在主线程弹窗确认是否继续下一轮循环"""
        result = [False]
        event = threading.Event()

        def ask():
            self.main_window.bring_to_front()
            result[0] = messagebox.askyesno(
                '预约制造',
                '下次执行时间已到，是否开始自动制造？\n\n'
                '确认后将自动启动 WeGame 并执行多账号制造。'
            )
            event.set()

        self.after(0, ask)
        event.wait()
        return result[0]

    def _run_one_cycle(self):
        """在工作线程中运行一轮多账号制造，遍历所有已启用账号后结束"""
        try:
            self._load_accounts()
            accounts = [a for a in self.accounts if a.get('enabled', True)]
            wg_cfg = self.wegame_cfg

            if not accounts:
                print('[多账号] 没有已启用的账号')
                return

            self._cycle_has_failure = False

            for account in accounts:
                if self._user_stop:
                    print('[多账号] 用户已停止')
                    return

                name = account.get('name', '未知')
                print(f'=== {name}: 开始 ===')
                self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 登录中...', foreground='blue'))

                # 激活 WeGame
                if not wegame_switcher.activate_wegame(wg_cfg.get('wegame_path', '')):
                    print(f'{name}: 无法找到/启动 WeGame，跳过')
                    self.after(0, lambda n=name: self.status_label.config(text=f'{n}: WeGame 不可用', foreground='red'))
                    self._cycle_has_failure = True
                    continue

                # 等待 WeGame 界面稳定（刚启动/还原后需要时间渲染）
                print(f'{name}: WeGame 已激活，等待界面稳定...')
                if self._wait_check(3):
                    print('[多账号] 用户已停止')
                    return

                # 输出前台进程调试信息
                try:
                    fg_hwnd = win32gui.GetForegroundWindow()
                    _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
                    fg_title = win32gui.GetWindowText(fg_hwnd)
                    fg_proc = psutil.Process(fg_pid)
                    print(f'{name}: 前台进程 [PID={fg_pid}] {fg_proc.name()} - "{fg_title}"')
                except Exception as e:
                    print(f'{name}: 获取前台进程信息失败: {e}')

                # 步骤 1-9：登录 + 导航到特勤处
                if not self._login_and_navigate(account, wg_cfg):
                    print(f'{name}: 导航失败，跳过')
                    self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 导航失败', foreground='red'))
                    self._cycle_has_failure = True
                    continue

                # ── 步骤 10：启动制造（完整一轮 dash_page，启动即走） ──
                print(f'{name}: 步骤10 启动制造（执行一轮完整检测，不等完成）')
                self.after(0, lambda n=name: self.status_label.config(text=f'{n}: 启动制造中...', foreground='blue'))

                self.stop_event.clear()

                # 捕获 dash_page 返回的剩余时间，用于估计完成时间
                latest_remain_times = [0, 0, 0, 0]

                def _capture_callback(remain_times, wait_list):
                    nonlocal latest_remain_times
                    latest_remain_times = remain_times
                    self.main_window.status_queue.put((remain_times, wait_list))

                import main as auto_module
                try:
                    auto_module.main(
                        stop_event=self.stop_event,
                        status_callback=_capture_callback,
                        single_cycle=True
                    )
                except Exception as e:
                    print(f'{name}: 制造异常: {e}')

                # 计算预计完成时间（取各部门最短剩余时间）
                valid_times = [t for t in latest_remain_times[1:] if t > 0]
                min_remain = min(valid_times) if valid_times else 0
                if min_remain > 0:
                    est_end = datetime.now() + timedelta(seconds=min_remain)
                    account['estimated_end'] = est_end.strftime('%H:%M')
                    print(f'{name}: 制造启动，预计完成 {account["estimated_end"]}')
                else:
                    account['estimated_end'] = '—'
                    print(f'{name}: 无需制造')
                self._save_accounts()
                self.after(0, self._refresh_list)

                if self._user_stop:
                    print('[多账号] 用户已停止')
                    self._exit_game(wg_cfg.get('exit_method', 'taskkill'))
                    return

                # 步骤 11：退出游戏（不等制造完成）
                print(f'{name}: 步骤11 退出游戏')
                self._exit_game(wg_cfg.get('exit_method', 'taskkill'))
                if self._user_stop:
                    print('[多账号] 用户已停止')
                    return

                # 退出 WeGame，下个账号循环会重新启动全新 WeGame
                print(f'{name}: 退出 WeGame，为下个账号做准备...')
                wegame_switcher.exit_wegame()
                if self._wait_check(3):
                    print('[多账号] 用户已停止')
                    return

                print(f'{name}: 完成')
                est = account.get('estimated_end', '')
                hint = f'{name}: 已完成' + (f'，预计 {est}' if est and est != '—' else '')
                self.after(0, lambda h=hint: self.status_label.config(text=h, foreground='green'))

            # 检查账号间完成时间差异：最早最晚相差超过 8h 说明部分账号制造失败
            end_times = []
            for acc in accounts:
                est = acc.get('estimated_end', '') or ''
                if est and est != '—':
                    try:
                        t = datetime.strptime(est, '%H:%M')
                        end_times.append(t.hour * 60 + t.minute)
                    except ValueError:
                        pass
            if len(end_times) >= 2:
                diff = max(end_times) - min(end_times)
                if diff > 720:  # 跨天修正（如 22:00~06:00）
                    diff = 1440 - diff
                if diff > 480:
                    print(f'[多账号] 完成时间差 {diff//60}h{diff%60}m 超过 8h，判定有账号制造失败')
                    self._cycle_has_failure = True

            # 所有账号处理完毕，退出 WeGame
            print('[多账号] 本轮制造完成，退出 WeGame')
            wegame_switcher.exit_wegame()

        except Exception as e:
            print(f'[多账号] 调度异常: {e}')
            self._cycle_has_failure = True
        finally:
            # 预约模式下：有账号失败则自动重试（最多 _max_retries 次）
            if (self._cycle_has_failure and self._is_monitoring and self.loop_var.get()
                    and not self._user_stop):
                self._retry_count += 1
                if self._retry_count <= self._max_retries:
                    print(f'[多账号] 有账号失败，自动重试第 {self._retry_count}/{self._max_retries} 轮...')
                    self.after(0, lambda: self.status_label.config(
                        text=f'自动重试 {self._retry_count}/{self._max_retries}', foreground='orange'))
                    self._start_one_cycle()
                    return
                else:
                    print(f'[多账号] 重试 {self._max_retries} 次后仍有失败，停止重试')
            else:
                self._retry_count = 0
            # 制造完成后检查是否有补货待执行
            if self._replenish_after_cycle:
                self._replenish_after_cycle = False
                print('[补货] 制造循环结束，开始执行补货循环')
                self._run_replenish_cycle()
            else:
                self.after(0, self._on_scheduler_stopped)

    def _start_replenish_cycle(self):
        """启动补货循环"""
        if self._is_running:
            return
        self._user_stop = False
        self.stop_event.clear()
        self._set_ui_running(True)
        self.scheduler_thread = threading.Thread(target=self._run_replenish_cycle, daemon=True)
        self.scheduler_thread.start()
        print('=== 补货循环已启动 ===')


    def _run_replenish_cycle(self):
        """补货循环：遍历所有启用账号，登录 -> 补货 -> 退出"""
        try:
            self._load_accounts()
            accounts = [a for a in self.accounts if a.get('enabled', True)]
            wg_cfg = self.wegame_cfg

            if not accounts:
                print('[补货] 没有已启用的账号')
                return

            # 读取阈值和补货量
            threshold = int(self._replenish_threshold_var.get())
            qty = int(self._replenish_qty_var.get())

            # 从 config.yaml 加载补货坐标
            import yaml
            config = yaml.safe_load(read_with_encoding_fallback(
                os.path.join(PROJECT_ROOT, 'config.yaml')))
            replenish_coords = config['replenish_coords']

            for account in accounts:
                if self._user_stop:
                    print('[补货] 用户已停止')
                    return

                name = account.get('name', '未知')
                print(f'=== 补货 {name}: 开始 ===')
                self.after(0, lambda n=name: self.status_label.config(
                    text=f'{n}: 登录中（补货）...', foreground='blue'))

                # 激活 WeGame
                if not wegame_switcher.activate_wegame(wg_cfg.get('wegame_path', '')):
                    print(f'{name}: 无法找到/启动 WeGame，跳过')
                    self.after(0, lambda n=name: self.status_label.config(
                        text=f'{n}: WeGame 不可用', foreground='red'))
                    continue

                if self._wait_check(3):
                    return

                # 步骤 1-8：登录导航（复用现有方法）
                if not self._login_and_navigate(account, wg_cfg):
                    print(f'{name}: 导航失败，跳过')
                    self.after(0, lambda n=name: self.status_label.config(
                        text=f'{n}: 导航失败', foreground='red'))
                    continue

                # 步骤 9-17：执行补货
                print(f'{name}: 执行补货...')
                self.after(0, lambda n=name: self.status_label.config(
                    text=f'{n}: 补货中...', foreground='blue'))
                try:
                    replenishment.do_replenish_materials(replenish_coords, threshold, qty)
                except Exception as e:
                    print(f'{name}: 补货异常: {e}')

                # 退出游戏
                print(f'{name}: 退出游戏')
                self._exit_game(wg_cfg.get('exit_method', 'taskkill'))
                if self._user_stop:
                    return

                # 退出 WeGame
                wegame_switcher.exit_wegame()
                if self._wait_check(3):
                    return

                print(f'{name}: 补货完成')
                self.after(0, lambda n=name: self.status_label.config(
                    text=f'{n}: 补货完成', foreground='green'))

            print('[补货] 所有账号补货完毕')
            wegame_switcher.exit_wegame()

        except Exception as e:
            print(f'[补货] 异常: {e}')
        finally:
            self.after(0, self._on_scheduler_stopped)

    def _exit_game(self, exit_method):
        """退出游戏（带超时强制结束，可被停止信号中断）"""
        try:
            existed = wegame_switcher.is_window_exist(
                wegame_switcher.GAME_CLASS, wegame_switcher.GAME_TITLE)
            print(f'[退出游戏] 方法={exit_method}, 窗口存在={existed}')

            wegame_switcher.exit_game(exit_method)

            # 轮询等待游戏退出，期间检查停止信号
            elapsed = 0
            timeout = 30
            while elapsed < timeout:
                if self._user_stop:
                    print('[多账号] 停止信号，跳过退出等待')
                    return

                if not wegame_switcher.is_window_exist(
                    wegame_switcher.GAME_CLASS, wegame_switcher.GAME_TITLE
                ):
                    print(f'[退出游戏] 窗口已关闭（耗时 {elapsed:.0f} 秒）')
                    return
                if elapsed % 5 == 0:
                    print(f'[退出游戏] 等待窗口关闭... {elapsed:.0f}/{timeout} 秒')
                jitter_sleep(1)
                elapsed += 1
            # 超时强制结束
            print(f'[退出游戏] 等待 {timeout} 秒超时，强制执行 taskkill')
            wegame_switcher.exit_game('taskkill')
            still_exist = wegame_switcher.is_window_exist(
                wegame_switcher.GAME_CLASS, wegame_switcher.GAME_TITLE)
            print(f'[退出游戏] taskkill 后窗口仍然存在={still_exist}')
        except Exception as e:
            print(f'[退出游戏] 异常: {e}')

    def _on_scheduler_stopped(self):
        """调度线程结束"""
        self._set_ui_running(False)
        if self._is_monitoring:
            self.status_label.config(text='预约等待中...', foreground='orange')
            print('[多账号] 本轮制造完成，等待下次执行')
        else:
            self.status_label.config(text='已停止', foreground='gray')
            print('=== 多账号调度已停止 ===')
        self.main_window._refresh_recipe_display()


# ── 账号添加/编辑对话框 ──────────────────────────────

class _AccountDialog(tk.Toplevel):
    """添加/编辑账号的模态对话框"""

    def __init__(self, parent, title='账号', name='', click_pos=None, scroll_before_click=0):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None

        self._click_pos = click_pos or [0, 0]
        self._scroll_before_click = scroll_before_click

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

        # 向下滚轮次数（第4个账号需要滚1次，第5个需要滚2次）
        ttk.Label(frame, text='向下滚轮次数:').grid(row=4, column=0, sticky=tk.W, pady=4)
        self.scroll_var = tk.StringVar(value=str(self._scroll_before_click))
        ttk.Spinbox(frame, from_=0, to=10, width=8, textvariable=self.scroll_var).grid(row=4, column=1, sticky=tk.W, pady=4)

        # 按钮
        btn_row = ttk.Frame(frame)
        btn_row.grid(row=5, column=0, columnspan=3, pady=(8, 0))
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
                jitter_sleep(1)
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
            scroll = int(self.scroll_var.get())
        except ValueError:
            messagebox.showerror('错误', '坐标和滚轮次数必须为数字', parent=self)
            return
        self.result = (name, [x, y], scroll)
        self.destroy()
