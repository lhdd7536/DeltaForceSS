"""
Delta Force 自动制造 - GUI 主窗口

提供：
- 启动/停止自动化循环
- 显示今日推荐配方及更新时间
- 运行日志面板
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue
import sys
import os
import time
from datetime import datetime

import win32gui
import win32con

# 项目根目录（源码/EXE 模式统一由 utils 定位）
# 先确保 utils 所在目录可导入（直接以脚本方式运行时也成立）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.utils import project_root, load_yaml, load_ruamel, dump_yaml_rt

PROJECT_ROOT = project_root()


# ── 工具 ──────────────────────────────────────────────

def _load_yaml(path):
    """加载 YAML 文件（自动回退编码）"""
    return load_yaml(path)


def _load_user_config():
    """加载用户配置"""
    return _load_yaml(os.path.join(PROJECT_ROOT, 'user_config.yaml'))


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

        # ── 多标签页独立控件集合 ──
        self.log_texts = []               # 仅单账号 tab 有日志框

        # ── 构建界面 ──
        self._build_ui()

        # ── 加载配置 ──
        self._load_config()
        self._refresh_recipe_display()

        # ── 加载快捷键配置 ──
        self._load_hotkey()

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
        # ── 主窗口 grid（只有 notebook + 底部状态栏） ──
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky='nsew',
                           padx=self.PADDING, pady=(self.PADDING, 0))

        # ── Tab 1：单账号 ──
        single_tab = ttk.Frame(self.notebook)
        self.notebook.add(single_tab, text='  单账号  ')
        self._build_single_account_ui(single_tab)

        # ── Tab 2：多账号 ──
        multi_tab = ttk.Frame(self.notebook)
        self.notebook.add(multi_tab, text='  多账号  ')
        self._build_multi_account_ui(multi_tab)

        # ── 底部状态栏 ──
        self.status_bar = ttk.Label(self, text='就绪', relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, sticky='ew',
                             padx=self.PADDING, pady=(0, self.PADDING))

    # ── 共享控件工厂 ────────────────────────────────────

    def _build_log_section(self, parent):
        """创建日志面板，返回 (frame, text_widget)"""
        frame = ttk.LabelFrame(parent, text='运行日志', padding=self.PADDING)
        inner = ttk.Frame(frame)
        inner.pack(fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(inner)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        log_text = tk.Text(inner, height=6, wrap=tk.WORD, state=tk.DISABLED,
                           yscrollcommand=scrollbar.set, font=('Consolas', 9))
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=log_text.yview)
        ttk.Button(frame, text='清空日志', command=self._clear_log).pack(anchor=tk.E, pady=(2, 0))
        return frame, log_text

    # ── 单账号 UI ────────────────────────────────────────

    def _build_single_account_ui(self, parent):
        parent.grid_rowconfigure(0, weight=0)  # 顶部: 控制+配方
        parent.grid_rowconfigure(1, weight=1)  # 日志: 占满剩余
        parent.grid_columnconfigure(0, weight=1)

        # ── 顶部区域（控制面板 + 制造配方） ──
        top = ttk.Frame(parent, padding=self.PADDING)
        top.grid(row=0, column=0, sticky='ew')
        top.grid_columnconfigure(0, weight=0)  # 控制面板不扩展
        top.grid_columnconfigure(1, weight=1)  # 制造配方占满剩余空间

        # 控制面板
        ctrl = ttk.LabelFrame(top, text='控制面板', padding=self.PADDING)
        ctrl.grid(row=0, column=0, sticky='n', padx=(0, self.PADDING))

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

        self.debug_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text='调试模式', variable=self.debug_var, command=self._on_debug_toggle).pack(anchor=tk.W)

        ttk.Separator(ctrl, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        self.hotkey_hint = ttk.Label(ctrl, text='快捷键: F8', foreground='gray')
        self.hotkey_hint.pack(anchor=tk.W)

        # 制造配方（一行显示：四个部门并列；只读下拉框从 config.yaml 全部制造物品中选择）
        recipe = ttk.LabelFrame(top, text='制造配方', padding=self.PADDING)
        recipe.grid(row=0, column=1, sticky='nsew')

        recipe_grid = ttk.Frame(recipe)
        recipe_grid.pack(fill=tk.BOTH, expand=True)
        recipe_grid.columnconfigure((0, 1, 2, 3), weight=1)
        recipe_grid.rowconfigure(0, weight=1)

        # 从 config.yaml 加载各部门合法物品（下拉选项，去重保持顺序）
        recipe_items = {}
        try:
            _cfg = _load_yaml(os.path.join(PROJECT_ROOT, 'config.yaml'))
            for dep in ('tech', 'work', 'medical', 'armor'):
                items = []
                for cat_items in _cfg['departments'][dep].values():
                    items.extend(cat_items)
                seen = set()
                recipe_items[dep] = [x for x in items if not (x in seen or seen.add(x))]
        except Exception as e:
            print(f'[GUI] 加载制造物品列表失败: {e}')

        self.recipe_combos = {}
        for i, dep in enumerate(('tech', 'work', 'medical', 'armor')):
            frame = ttk.LabelFrame(recipe_grid, text=self.DEP_NAMES[dep])
            frame.grid(row=0, column=i, sticky='nsew', padx=2, pady=2)
            combo = ttk.Combobox(frame, values=recipe_items.get(dep, []),
                                 state='readonly', height=12)
            combo.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
            self.recipe_combos[dep] = combo

        # 保存配方（下拉框选项均来自 config.yaml，无需额外校验）
        ttk.Button(recipe, text='保存配方', command=self._save_recipes).pack(fill=tk.X, pady=(4, 0))

        # ── 运行日志 ──
        log_frame, log_text = self._build_log_section(parent)
        log_frame.grid(row=1, column=0, sticky='nsew', padx=self.PADDING, pady=(0, self.PADDING))
        self.log_texts.append(log_text)

    # ── 多账号 UI ────────────────────────────────────────

    def _build_multi_account_ui(self, parent):
        parent.grid_rowconfigure(0, weight=1)  # 账号管理面板占满
        parent.grid_columnconfigure(0, weight=1)

        # 账号管理面板
        from gui.account_panel import AccountPanel
        self.account_panel = AccountPanel(parent, main_window=self)
        self.account_panel.grid(row=0, column=0, sticky='nsew',
                                padx=self.PADDING, pady=(self.PADDING, 0))

    # ── 配置加载 ────────────────────────────────────────

    def _load_config(self):
        """加载 user_config 到 GUI 控件"""
        try:
            cfg = _load_user_config()
            self.debug_var.set(cfg.get('debug_mode', False))
        except Exception:
            pass

    def _save_config(self):
        """将 GUI 控件状态写回 user_config.yaml"""
        path = os.path.join(PROJECT_ROOT, 'user_config.yaml')
        try:
            cfg = load_ruamel(path)
            cfg['debug_mode'] = self.debug_var.get()
            dump_yaml_rt(path, cfg)
        except Exception as e:
            print(f'[GUI] 保存配置失败: {e}')

    def _on_debug_toggle(self):
        self._save_config()

    # ── 快捷键 ────────────────────────────────────────────

    def _load_hotkey(self):
        """从 user_config.yaml 读取快捷键并注册为全局热键（游戏前台也可用）"""
        try:
            cfg = _load_user_config()
            hotkey = cfg.get('hotkey', 'f8').strip().lower()
        except Exception:
            hotkey = 'f8'
        self._hotkey_key = hotkey
        self._global_hotkey = None
        self._last_toggle_ts = 0.0

        # 注册全局热键（keyboard 库，系统级钩子，不依赖窗口焦点）
        try:
            import keyboard
            self._global_hotkey = keyboard.add_hotkey(hotkey, self._on_global_hotkey)
            self.hotkey_hint.config(text=f'快捷键: {hotkey.upper()} (全局)')
            print(f'[GUI] 全局快捷键已注册: {hotkey.upper()}')
        except Exception as e:
            # 降级：窗口内 bind（仅窗口持有焦点时生效）
            self.hotkey_hint.config(text=f'快捷键: {hotkey.upper()}')
            print(f'[GUI] 全局快捷键注册失败，降级为窗口内快捷键: {e}')
            self.bind(f'<{hotkey.upper()}>', self._toggle_automation)

    def _on_global_hotkey(self):
        """全局热键回调（keyboard 监听线程）→ 调度到 tkinter 主线程执行"""
        try:
            self.after(0, self._toggle_automation)
        except Exception:
            pass

    def _unregister_global_hotkey(self):
        """注销全局热键（窗口关闭时调用）"""
        if getattr(self, '_global_hotkey', None):
            try:
                import keyboard
                keyboard.remove_hotkey(self._global_hotkey)
            except Exception:
                pass
            self._global_hotkey = None

    def _toggle_automation(self, event=None):
        """快捷键：切换启动/停止"""
        # 节流：防止全局热键连按/长按导致重复触发
        now = time.time()
        if now - self._last_toggle_ts < 1.0:
            return
        self._last_toggle_ts = now

        if self.worker_thread and self.worker_thread.is_alive():
            print('[GUI] 快捷键: 停止')
            self._stop_automation()
        elif self._is_multi_running():
            print('[GUI] 快捷键: 停止多账号')
            self.account_panel._stop_scheduler()
        else:
            print('[GUI] 快捷键: 启动')
            self._start_automation()

    # ── 制造配方显示 ────────────────────────────────────

    def _refresh_recipe_display(self):
        """读取 user_config.yaml 更新制造配方显示"""
        try:
            cfg = _load_user_config()
            for dep in ['tech', 'work', 'medical', 'armor']:
                items = cfg.get(dep)
                if items and len(items) > 0:
                    name = items[0][0]
                else:
                    name = ''
                self.recipe_combos[dep].set(name)
        except Exception as e:
            print(f'[GUI] 加载制造配方失败: {e}')

    def _save_recipes(self):
        """保存制造配方：将四个部门下拉框选定的物品写回 user_config.yaml

        下拉框选项直接来自 config.yaml 的 departments，均为该制造台合法物品，
        无需额外校验；未选择的部门保持原状（不制造）。
        """
        try:
            path = os.path.join(PROJECT_ROOT, 'user_config.yaml')
            ucfg = load_ruamel(path)
            for dep in ('tech', 'work', 'medical', 'armor'):
                name = self.recipe_combos[dep].get().strip()
                if not name:
                    # 未选择 → 保持该部门原状
                    continue
                current = ucfg.get(dep)
                if current and len(current) > 0:
                    current[0][0] = name
                else:
                    ucfg[dep] = [[name, -1]]
            dump_yaml_rt(path, ucfg)
            messagebox.showinfo('保存成功', '制造配方已更新')
            self._refresh_recipe_display()
        except Exception as e:
            messagebox.showerror('保存失败', f'发生错误: {e}')

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
            auto_module.main(stop_event=self.stop_event)
        except Exception as e:
            print(f'[ERROR] 自动化异常: {e}')
            import traceback
            traceback.print_exc()

        # 线程结束，通知 GUI
        self.status_queue.put(None)  # 哨兵

    def _append_log(self, text):
        """向日志框追加一行（主线程调用）"""
        for log_text in self.log_texts:
            try:
                log_text.config(state=tk.NORMAL)
                log_text.insert(tk.END, text + '\n')
                log_text.see(tk.END)
                log_text.config(state=tk.DISABLED)
            except Exception:
                pass

    def _clear_log(self):
        for log_text in self.log_texts:
            try:
                log_text.config(state=tk.NORMAL)
                log_text.delete(1.0, tk.END)
                log_text.config(state=tk.DISABLED)
            except Exception:
                pass

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

        # 检查线程是否结束（清空队列中残留的状态数据）
        try:
            while True:
                signal = self.status_queue.get_nowait()
                if signal is None:
                    self._on_automation_stopped()
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
        self._refresh_recipe_display()
        print('=== 自动制造循环已停止 ===')

    # ── 窗口管理 ───────────────────────────────────────

    def bring_to_front(self):
        """恢复窗口并置前闪烁"""
        try:
            hwnd = int(self.winfo_id())
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.FlashWindow(hwnd, True)
        except Exception:
            self.deiconify()
            self.lift()
            self.focus_force()

    # ── 窗口关闭 ────────────────────────────────────────

    def _on_close(self):
        """关闭窗口时清理"""
        # 先注销全局热键，避免关闭过程中误触
        self._unregister_global_hotkey()

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
