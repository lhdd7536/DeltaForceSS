# 制造材料补货功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在多账号模式下实现每天 2-5 点自动补货钛合金和高级燃料

**Architecture:** 在 `config.yaml` 新增 `replenish_coords` 坐标段，新建 `replenishment.py` 模块处理军需处导航和数量 OCR 逻辑，在 `account_panel.py` 中新增 GUI 控件和 2 点调度看门狗

**Tech Stack:** Python 3.11, pytesseract, OpenCV, pyautogui, tkinter

---

### 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `config.yaml` | 修改 | 末尾追加 `replenish_coords` 坐标段 |
| `replenishment.py` | 新建 | OCR 数量识别 + 军需处导航 + 材料补货主流程 |
| `gui/account_panel.py` | 修改 | GUI 控件（勾选框 + Spinbox）+ 调度看门狗 + 补货循环 |

---

### Task 1: 在 `config.yaml` 中追加 `replenish_coords`

**Files:**
- Modify: `config.yaml:325`

- [ ] **Step 1: 在 config.yaml 末尾追加补货坐标**

在 `OCR_factors.armor` 行（第 324 行）后追加：

```yaml
replenish_coords:
  dep_tab: [580, 55]
  quartermaster: [464, 107]
  medical_dep: [555, 680]
  collectibles_tab: [327, 127]
  materials:
    titanium_alloy: [1173, 481]
    advanced_fuel: [305, 699]
  quantity_region: [1596, 775, 9, 17]
  increase_btn: [1762, 833]
  fill_btn: [1638, 935]
  buy_btn: [970, 754]
```

- [ ] **Step 2: 验证 YAML 解析正常**

```bash
conda run -n deltaforce python -c "
import yaml
cfg = yaml.safe_load(open('config.yaml', encoding='utf-8'))
rc = cfg['replenish_coords']
assert rc['dep_tab'] == [580, 55]
assert rc['materials']['titanium_alloy'] == [1173, 481]
assert len(rc['quantity_region']) == 4
print('OK: replenish_coords loaded')
"
```

- [ ] **Step 3: 提交**

```bash
git add config.yaml
git commit -m "config: 新增 replenish_coords 补货坐标配置"
```

---

### Task 2: 创建 `replenishment.py`

**Files:**
- Create: `replenishment.py`

- [ ] **Step 1: 编写 `replenishment.py`**

```python
"""
制造材料补货模块。

在多账号模式下，导航到军需处->收集品界面，检查钛合金和高级燃料库存，
低于阈值时自动补货。

坐标由调用方传入（从 config.yaml replenish_coords 加载并缩放后）。
"""

import cv2
import numpy as np
import pyautogui
import pytesseract
from PIL import ImageGrab
from wegame_switcher import click_position
from utils import jitter_sleep


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

    for name, mat_pos in materials:
        print(f'[补货] 检查 {name}...')
        click_position(mat_pos)
        jitter_sleep(1)

        # 步骤 14：OCR 当前数量（region 需先缩放）
        x, y, w, h = coords['quantity_region']
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
        jitter_sleep(2)
        print(f'[补货] {name} 已购买')

    print('[补货] 全部材料处理完毕')


def _navigate_to_collectibles(coords):
    """从主基地导航到军需处->医疗部门->收集品界面（步骤 9-12）"""
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
```

- [ ] **Step 2: 提交流程**

```bash
git add replenishment.py
git commit -m "feat: 新增 replenishment.py 制造材料补货模块"
```

---

### Task 3: GUI 控件 — 新增自动补货配置

**Files:**
- Modify: `gui/account_panel.py`

在控制面板区域新增自动补货勾选框、阈值和补货量 Spinbox，并持久化到 `user_config.yaml`。

- [ ] **Step 1: 在 `__init__` 中加载配置并新增成员变量**

找到 `__init__` 方法，在 `self._auto_run_hour = self._load_auto_hour()` 后追加：

```python
# 补货配置
self._auto_replenish = self._load_auto_replenish()
self._replenish_after_cycle = False
```

- [ ] **Step 2: 新增配置加载/保存方法**

在 `_load_auto_hour()` 方法后新增：

```python
def _load_auto_replenish(self):
    """从 user_config.yaml 加载自动补货配置"""
    try:
        cfg = _load_yaml(USER_CONFIG_FILE)
        return cfg.get('auto_replenish', {'enabled': False, 'threshold': 3, 'quantity': 3})
    except Exception:
        return {'enabled': False, 'threshold': 3, 'quantity': 3}
```

在 `_save_user_config()` 方法末尾追加：

```python
cfg['auto_replenish'] = {
    'enabled': self._replenish_var.get(),
    'threshold': int(self._replenish_threshold_var.get()),
    'quantity': int(self._replenish_qty_var.get()),
}
```

- [ ] **Step 3: 在控制面板新增补货控件**

在 `_build_ui()` 中，`ctrl_row` 创建完毕后，找到 `auto_hour_var` 的 Spinbox 代码块（第 186-191 行），在其后追加：

```python
# ── 自动补货配置 ──
ttk.Separator(ctrl_row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(8, 4))
self._replenish_var = tk.BooleanVar(value=self._auto_replenish.get('enabled', False))
ttk.Checkbutton(ctrl_row, text='每日2-5点自动补货',
                variable=self._replenish_var).pack(side=tk.LEFT, padx=(0, 4))

ttk.Label(ctrl_row, text='阈值:').pack(side=tk.LEFT, padx=(4, 2))
self._replenish_threshold_var = tk.StringVar(
    value=str(self._auto_replenish.get('threshold', 3)))
ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
            textvariable=self._replenish_threshold_var).pack(side=tk.LEFT)

ttk.Label(ctrl_row, text='补货量:').pack(side=tk.LEFT, padx=(4, 2))
self._replenish_qty_var = tk.StringVar(
    value=str(self._auto_replenish.get('quantity', 3)))
ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
            textvariable=self._replenish_qty_var).pack(side=tk.LEFT)
```

- [ ] **Step 4: 提交流程**

```bash
git add gui/account_panel.py
git commit -m "feat: GUI 新增每日自动补货配置控件"
```

---

### Task 4: 调度集成 — 看门狗 + 补货循环

**Files:**
- Modify: `gui/account_panel.py`

在 AccountPanel 中新增 2 点调度看门狗、补货循环方法，以及在制造循环末尾检查补货标志。

- [ ] **Step 1: 在文件顶部添加 `import replenishment`**

- [ ] **Step 2: 在 `_build_ui` 中将之前的 `_replenish_var` 勾选框绑定保存回调**

将 Checkbutton 的 `variable=self._replenish_var` 后面添加 `command=self._save_user_config`：

```python
ttk.Checkbutton(ctrl_row, text='每日2-5点自动补货',
                variable=self._replenish_var,
                command=self._save_user_config).pack(side=tk.LEFT, padx=(0, 4))
```

阈值和补货量的 Spinbox 也要绑定保存：

```python
ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
            textvariable=self._replenish_threshold_var,
            command=self._save_user_config).pack(side=tk.LEFT)

ttk.Spinbox(ctrl_row, from_=1, to=99, width=3,
            textvariable=self._replenish_qty_var,
            command=self._save_user_config).pack(side=tk.LEFT)
```

- [ ] **Step 3: 新增 `_replenish_watchdog()` 方法**

```python
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
            next_mfg = self._calc_next_cycle_time(enabled) if enabled else None
            if next_mfg is None:
                # 没有启用账号或没有预约 → 直接补货
                print('[补货] 无制造预约，直接开始补货')
                self._start_replenish_cycle()
            else:
                next_mfg_dt = datetime.fromtimestamp(next_mfg)
                if next_mfg_dt.hour >= 3:
                    # 情况②：3 点后才预约 → 直接补货
                    print(f'[补货] 下次制造预约在 {next_mfg_dt.hour}:{next_mfg_dt.minute:02d}（3 点后），直接补货')
                    self._start_replenish_cycle()
                else:
                    # 情况③：3 点前有预约 → 等制造完再补
                    print(f'[补货] 下次制造预约在 {next_mfg_dt.hour}:{next_mfg_dt.minute:02d}（3 点前），等制造完补货')
                    self._replenish_after_cycle = True
```

- [ ] **Step 4: 新增 `_start_replenish_cycle()` 和 `_run_replenish_cycle()`**

```python
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
    """补货循环：遍历所有启用账号，登录->补货->退出"""
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

        # 从 config.yaml 加载补货坐标（原始 1920x1080 基准，
        # replenishment.py 内部自动缩放）
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
```

- [ ] **Step 5: 在 `_run_one_cycle()` 的 finally 块中追加补货检测**

在 `_run_one_cycle()` 方法中，找到 `finally` 块（第 901 行左右），在 `self.after(0, self._on_scheduler_stopped)` 调用前追加：

```python
# 制造完成后检查是否有补货待执行
if self._replenish_after_cycle:
    self._replenish_after_cycle = False
    print('[补货] 制造循环结束，开始执行补货循环')
    self._run_replenish_cycle()
```

- [ ] **Step 6: 在调度器启动时控制看门狗**

在 `_start_scheduler()` 中，`self.scheduler_thread.start()` 后追加：

```python
# 启动补货看门狗（守护线程）
self._replenish_watchdog_thread = threading.Thread(
    target=self._replenish_watchdog, daemon=True)
self._replenish_watchdog_thread.start()
```

同样在 `_start_schedule_monitor()` 中，`self._schedule_thread.start()` 后追加相同代码：

```python
if not hasattr(self, '_replenish_watchdog_thread') or not self._replenish_watchdog_thread.is_alive():
    self._replenish_watchdog_thread = threading.Thread(
        target=self._replenish_watchdog, daemon=True)
    self._replenish_watchdog_thread.start()
```

看门狗共享 `_user_stop` 和 `stop_event`，停止调度器时自动退出。

- [ ] **Step 7: 提交**

```bash
git add gui/account_panel.py
git commit -m "feat: 新增补货调度看门狗和补货循环"
```

---

### Task 5: 最终验证

- [ ] **Step 1: 检查无语法错误**

```bash
conda run -n deltaforce python -c "import py_compile; py_compile.compile('replenishment.py', doraise=True)"
conda run -n deltaforce python -c "import py_compile; py_compile.compile('gui/account_panel.py', doraise=True)"
```

- [ ] **Step 2: 确认 config.yaml 可正常加载**

```bash
conda run -n deltaforce python -c "
import yaml
c = yaml.safe_load(open('config.yaml', encoding='utf-8'))
assert 'replenish_coords' in c
assert all(k in c['replenish_coords'] for k in ['dep_tab','quartermaster','medical_dep','collectibles_tab','materials','quantity_region','increase_btn','fill_btn','buy_btn'])
assert all(k in c['replenish_coords']['materials'] for k in ['titanium_alloy','advanced_fuel'])
print('All checks passed')
"
```

- [ ] **Step 3: 提交最终整合**

```bash
git add -A
git commit -m "feat: 实现每日自动补货功能（config + replenishment.py + GUI + 调度）"
```
