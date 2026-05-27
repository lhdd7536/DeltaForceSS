"""
Delta Force 自动制造 - GUI 主窗口

提供：
- 启动/停止自动化循环
- 显示今日推荐配方及更新时间
- 实时显示四个制造台运行状态
- 运行日志面板
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import sys
import os
import time as time_module
from datetime import datetime

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import yaml
from ruamel.yaml import YAML


# ── 工具 ──────────────────────────────────────────────

def _load_yaml(path):
    """加载 YAML 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def _load_user_config():
    """加载用户配置"""
    return _load_yaml(os.path.join(PROJECT_ROOT, 'user_config.yaml'))


# ── 日期格式化 ────────────────────────────────────────

def _read_cache_date():
    """读取 data/last_update_date.txt"""
    cache = os.path.join(PROJECT_ROOT, 'data', 'last_update_date.txt')
    if os.path.exists(cache):
        with open(cache, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None


# ── MainWindow ────────────────────────────────────────

class MainWindow(tk.Tk):
    """GUI 主窗口"""

    PADDING = 8

    # 部门显示名
    DEP_NAMES = {
        'tech': '技术中心',
        'work': '工作台',
        'medical': '制药台',
        'armor': '防具台',
    }

    STATUS_TEXTS = {
        -2: '○ 空闲中',
        -1: '✓ 已完成',
    }

    def __init__(self):
        super().__init__()

        self.title('🔺 Force 自动制造  v1.0')
        self.geometry('880x780')
        self.minsize(700, 650)
        self.resizable(True, True)

        # ── 线程控制 ──
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.status_queue = queue.Queue()

        # ── 打印重定向缓冲区 ──
        self.log_queue = queue.Queue()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        # ── 构建界面 ──
        self._build_ui()

        # ── 加载配置 ──
        self._load_config()
        self._refresh_recipe_display()

        # ── 启动轮询 ──
        self._poll_loop()

        # ── 窗口关闭处理 ──
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        # ── 启动打印重定向 ──
        sys.stdout = self._StdoutRedirector(self.log_queue)
        sys.stderr = self._StdoutRedirector(self.log_queue)

        print('[GUI] 日志系统就绪')

    # ── 内部类：打印重定向 ──────────────────────────────

    class _StdoutRedirector:
        """将 print 捕获到队列中，由主线程轮询刷新到日志框"""

        def __init__(self, log_queue):
            self.queue = log_queue
            self.encoding = 'utf-8'
            self.errors = 'replace'
            self.newlines = None

        def write(self, text):
            if not text:
                return
            stripped = text.strip()
            if stripped:
                timestamp = datetime.now().strftime('%H:%M:%S')
                self.queue.put(f'[{timestamp}] {stripped}')

        def flush(self):
            pass

        def isatty(self):
            return False

    # ── 构建界面 ────────────────────────────────────────

    def _build_ui(self):
        dept_list = ['tech', 'work', 'medical', 'armor']
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

        # ── 主窗口 grid 布局（确保日志区域始终有空间） ──
        self.grid_rowconfigure(0, weight=1)  # notebook: 与日志平分
        self.grid_rowconfigure(1, weight=0)  # 状态面板: 固定高度
        self.grid_rowconfigure(2, weight=1)  # 日志: 与 notebook 平分
        self.grid_columnconfigure(0, weight=1)

        # ── Notebook 标签页 ──
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky='ew', padx=self.PADDING, pady=(self.PADDING, 0))

        # ── Tab 1：单账号（原有控制面板 + 推荐配方） ──
        single_tab = ttk.Frame(self.notebook)
        self.notebook.add(single_tab, text='  单账号  ')
        self._build_single_account_ui(single_tab)

        # ── Tab 2：多账号 ──
        multi_tab = ttk.Frame(self.notebook)
        self.notebook.add(multi_tab, text='  多账号  ')
        from gui.account_panel import AccountPanel
        self.account_panel = AccountPanel(multi_tab, main_window=self)
        self.account_panel.pack(fill=tk.BOTH, expand=True)

        # ── 部门状态（共享） ──
        status_frame = ttk.LabelFrame(self, text='部门状态', padding=self.PADDING)
        status_frame.grid(row=1, column=0, sticky='ew', padx=self.PADDING, pady=(self.PADDING, 0))

        self.dep_status_labels = {}
        for dep in dept_list:
            row = ttk.Frame(status_frame)
            row.pack(fill=tk.X, pady=1)
            name_label = ttk.Label(row, text=f'{self.DEP_NAMES.get(dep, dep)}: ', width=8)
            name_label.pack(side=tk.LEFT)
            bar = ttk.Progressbar(row, length=200, mode='determinate')
            bar.pack(side=tk.LEFT, padx=4)
            info = ttk.Label(row, text='--', width=28)
            info.pack(side=tk.LEFT)
            self.dep_status_labels[dep] = {'bar': bar, 'info': info}

        # ── 运行日志（共享） ──
        log_frame = ttk.LabelFrame(self, text='运行日志', padding=self.PADDING)
        log_frame.grid(row=2, column=0, sticky='nsew', padx=self.PADDING, pady=(self.PADDING, 0))

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_inner)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text = tk.Text(log_inner, height=10, wrap=tk.WORD, state=tk.DISABLED,
                                 yscrollcommand=scrollbar.set, font=('Consolas', 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        clear_btn = ttk.Button(log_frame, text='清空日志', command=self._clear_log)
        clear_btn.pack(anchor=tk.E, pady=(2, 0))

        # ── 状态栏 ──
        self.status_bar = ttk.Label(self, text='就绪', relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=3, column=0, sticky='ew', padx=self.PADDING, pady=(0, self.PADDING))

    # ── 单账号 UI ────────────────────────────────────────

    def _build_single_account_ui(self, parent):
        """单账号标签页：控制面板 + 推荐配方"""
        top_frame = ttk.Frame(parent, padding=self.PADDING)
        top_frame.pack(fill=tk.X, side=tk.TOP)

        # ── 控制面板 ──
        ctrl = ttk.LabelFrame(top_frame, text='控制面板', padding=self.PADDING)
        ctrl.pack(side=tk.LEFT, fill=tk.Y, padx=(0, self.PADDING))

        btn_frame = ttk.Frame(ctrl)
        btn_frame.pack(fill=tk.X, pady=(0, 4))
        self.btn_start = ttk.Button(btn_frame, text='▶ 启动', command=self._start_automation)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_stop = ttk.Button(btn_frame, text='■ 停止', command=self._stop_automation, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        self.status_indicator = tk.Canvas(ctrl, width=16, height=16, highlightthickness=0)
        self.status_indicator.pack(pady=(4, 0))
        self._status_dot = self.status_indicator.create_oval(2, 2, 14, 14, fill='red', outline='')

        self.status_label = ttk.Label(ctrl, text='已停止')
        self.status_label.pack()

        ttk.Separator(ctrl, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        self.bg_var = tk.BooleanVar(value=False)
        self.debug_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text='后台模式', variable=self.bg_var, command=self._on_bg_toggle).pack(anchor=tk.W)
        ttk.Checkbutton(ctrl, text='调试模式', variable=self.debug_var, command=self._on_debug_toggle).pack(anchor=tk.W)

        # ── 推荐配方 ──
        recipe = ttk.LabelFrame(top_frame, text='今日推荐配方', padding=self.PADDING)
        recipe.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.update_time_label = ttk.Label(recipe, text='更新于: --')
        self.update_time_label.pack(anchor=tk.E)

        recipe_grid = ttk.Frame(recipe)
        recipe_grid.pack(fill=tk.BOTH, expand=True)
        recipe_grid.columnconfigure((0, 1), weight=1)
        recipe_grid.rowconfigure((0, 1), weight=1)

        self.recipe_labels = {}
        dept_list = ['tech', 'work', 'medical', 'armor']
        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        for dep, pos in zip(dept_list, positions):
            frame = ttk.LabelFrame(recipe_grid, text=self.DEP_NAMES.get(dep, dep))
            frame.grid(row=pos[0], column=pos[1], sticky='nsew', padx=2, pady=2)
            label = ttk.Label(frame, text='--', anchor=tk.CENTER, font=('', 10, 'bold'))
            label.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.recipe_labels[dep] = label

    # ── 配置加载 ────────────────────────────────────────

    def _load_config(self):
        """加载 user_config 到 GUI 控件"""
        try:
            cfg = _load_user_config()
            self.bg_var.set(cfg.get('background_mode', False))
            self.debug_var.set(cfg.get('debug_mode', False))
        except Exception:
            pass

    def _save_config(self):
        """将 GUI 控件状态写回 user_config.yaml"""
        path = os.path.join(PROJECT_ROOT, 'user_config.yaml')
        try:
            yaml_loader = YAML()
            yaml_loader.indent(mapping=2, sequence=4, offset=2)
            yaml_loader.preserve_quotes = True
            with open(path, 'r', encoding='utf-8') as f:
                cfg = yaml_loader.load(f)
            cfg['background_mode'] = self.bg_var.get()
            cfg['debug_mode'] = self.debug_var.get()
            with open(path, 'w', encoding='utf-8') as f:
                yaml_loader.dump(cfg, f)
        except Exception as e:
            print(f'[GUI] 保存配置失败: {e}')

    def _on_bg_toggle(self):
        self._save_config()

    def _on_debug_toggle(self):
        self._save_config()

    # ── 推荐配方显示 ────────────────────────────────────

    def _refresh_recipe_display(self):
        """读取 user_config.yaml 更新推荐配方显示"""
        try:
            cfg = _load_user_config()
            for dep in ['tech', 'work', 'medical', 'armor']:
                items = cfg.get(dep)
                if items and len(items) > 0:
                    name = items[0][0]
                else:
                    name = '(空)'
                self.recipe_labels[dep].config(text=name)

            cache_date = _read_cache_date()
            if cache_date:
                self.update_time_label.config(text=f'更新于: {cache_date}')
            else:
                self.update_time_label.config(text='今天尚未更新')
        except Exception as e:
            print(f'[GUI] 加载推荐配方失败: {e}')

    # ── 线程控制 ────────────────────────────────────────

    def _start_automation(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        # 检查多账号是否在运行
        if self._is_multi_running():
            print('[单账号] 多账号模式正在运行，请先停止')
            return

        self.stop_event.clear()
        self.status_indicator.itemconfig(self._status_dot, fill='green')
        self.status_label.config(text='运行中')
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.status_bar.config(text='正在启动...')

        self.worker_thread = threading.Thread(target=self._run_automation, daemon=True)
        self.worker_thread.start()
        print('=== 自动制造循环已启动 ===')

    def _is_multi_running(self):
        """检查多账号调度是否正在运行"""
        return (hasattr(self, 'account_panel') and self.account_panel is not None
                and self.account_panel._is_running)

    def _stop_automation(self):
        print('正在停止自动制造...')
        self.stop_event.set()
        # 线程会在下次循环迭代时退出
        self.status_indicator.itemconfig(self._status_dot, fill='orange')
        self.status_label.config(text='正在停止...')

    def _run_automation(self):
        """在工作线程中运行 main()"""
        try:
            import main as auto_module
            auto_module.main(
                stop_event=self.stop_event,
                status_callback=lambda s, w: self.status_queue.put((s, w))
            )
        except Exception as e:
            print(f'[ERROR] 自动化异常: {e}')
            import traceback
            traceback.print_exc()

        # 线程结束，通知 GUI
        self.status_queue.put(None)  # 哨兵

    # ── 状态更新 ────────────────────────────────────────

    def _update_status_display(self, status_data):
        """更新部门状态面板"""
        remain_times, wait_list_dict = status_data

        dept_list = ['tech', 'work', 'medical', 'armor']
        for dep, remain in zip(dept_list, remain_times):
            labels = self.dep_status_labels[dep]
            bar = labels['bar']
            info = labels['info']

            if remain == -2:
                # 空闲
                bar['value'] = 0
                info.config(text='○ 空闲中')
            elif remain == -1:
                # 已完成
                bar['value'] = 100
                info.config(text='✓ 已完成')
            else:
                # 制造中
                max_val = 3600  # 假设最长 1 小时
                pct = min(100, int((1 - remain / max_val) * 100))
                bar['value'] = pct
                h, m = divmod(int(remain), 3600)
                m, s = divmod(m, 60)
                if h > 0:
                    info.config(text=f'● 制造中 剩余 {h}:{m:02d}:{s:02d}')
                else:
                    info.config(text=f'● 制造中 剩余 {m:02d}:{s:02d}')

            # 更新状态栏
            status_parts = []
            for dep2, remain2 in zip(dept_list, remain_times):
                name2 = self.DEP_NAMES.get(dep2, dep2)
                if remain2 == -2:
                    status_parts.append(f'{name2}:空闲')
                elif remain2 == -1:
                    status_parts.append(f'{name2}:完成')
                else:
                    m, s = divmod(int(remain2), 60)
                    h, m = divmod(m, 60)
                    if h > 0:
                        status_parts.append(f'{name2}:{h}h{m:02d}m')
                    else:
                        status_parts.append(f'{name2}:{m:02d}m{s:02d}s')
            self.status_bar.config(text=' | '.join(status_parts))

    def _append_log(self, text):
        """向日志框追加一行（主线程调用）"""
        try:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, text + '\n')
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        except Exception:
            pass  # 若控件已销毁则静默忽略

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ── 轮询循环（主线程） ──────────────────────────────

    def _poll_loop(self):
        """每 100ms 检查队列，刷新 GUI"""
        # 处理日志
        try:
            while True:
                text = self.log_queue.get_nowait()
                self._append_log(text)
        except queue.Empty:
            pass

        # 处理状态更新
        try:
            while True:
                status = self.status_queue.get_nowait()
                if status is None:
                    # 哨兵：线程已结束
                    self._on_automation_stopped()
                else:
                    self._update_status_display(status)
        except queue.Empty:
            pass

        self.after(100, self._poll_loop)

    def _on_automation_stopped(self):
        """自动化线程结束"""
        self.status_indicator.itemconfig(self._status_dot, fill='red')
        self.status_label.config(text='已停止')
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_bar.config(text='已停止')
        for dep in ['tech', 'work', 'medical', 'armor']:
            self.dep_status_labels[dep]['bar']['value'] = 0
            self.dep_status_labels[dep]['info'].config(text='--')
        self._refresh_recipe_display()
        print('=== 自动制造循环已停止 ===')

    # ── 窗口关闭 ────────────────────────────────────────

    def _on_close(self):
        """关闭窗口时清理"""
        if self.worker_thread and self.worker_thread.is_alive():
            self.stop_event.set()
            self.worker_thread.join(timeout=3)
        # 停止多账号调度
        if hasattr(self, 'account_panel') and self.account_panel is not None:
            if self.account_panel._is_running:
                self.account_panel._stop_scheduler()
                # 等待线程退出
                if self.account_panel.scheduler_thread:
                    self.account_panel.scheduler_thread.join(timeout=3)
        # 恢复标准输出
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self.destroy()
