# 方案二实施文档：WeGame 多账号自动制造

## 概述

在现有单账号制造系统基础上，增加多账号支持。通过**固定位置点击**实现 WeGame 账号切换，无需密码管理、无需 OCR 识别登录界面。

**核心思路**：用户先在 WeGame 中保存多个 QQ 账号，脚本只需在 WeGame 登录窗口的固定坐标上点击即可切换账号登录。

## 一、架构变更

```
DeltaForceSS/
├── main.py                         # 不变
├── wegame_switcher.py              # [新] WeGame 账号切换 + 游戏退出工具
├── gui/
│   ├── __init__.py
│   ├── app.py                      # 不变
│   ├── main_window.py              # [改] 增加 Notebook 标签页
│   └── account_panel.py            # [新] 多账号管理面板
├── data/
│   ├── accounts.yaml               # [新] 账号配置（名称+点击坐标）
│   └── last_update_date.txt        # 不变
├── config.yaml                     # 不变
└── user_config.yaml                # 不变
```

`main.py` **不需要修改**——`main()` 函数已通过 `stop_event` 和 `status_callback` 参数支持外部调度。

## 二、数据格式：`data/accounts.yaml`

```yaml
accounts:
  - name: "大号"
    click_pos: [962, 628]      # 步骤 2：WeGame 登录窗口中此账号按钮的点击位置
    enabled: true
  - name: "小号"
    click_pos: [938, 665]
    enabled: false

wegame:
  # 登录链路（步骤 1/3/4/5/6/9/12/13）
  switch_account_btn_pos: [60, 60]    # 步骤 1：切换账号按钮（可选）
  login_btn_pos: [960, 640]           # 步骤 3：登录按钮
  game_app_pos: [150, 400]            # 步骤 4：三角洲行动应用图标
  launch_btn_pos: [960, 800]          # 步骤 5：启动按钮
  mode_btn_pos: [300, 500]            # 步骤 6：烽火地带模式
  dash_entry_pos: [600, 350]          # 步骤 9：特勤处入口
  account_avatar_pos: [800, 400]      # 步骤 12：当前账号头像（可选）
  switch_user_btn_pos: [1200, 100]    # 步骤 13：切换用户按钮（可选）

  # 其他配置
  exit_method: "alt_f4"               # 退出游戏方式: alt_f4 / wm_close / taskkill
  account_timeout: 600                 # 每个账号制造时长（秒），默认 10 分钟
```

坐标基准为 1920×1080，运行时通过 `scale_factor = 当前宽度 / 1920` 缩放（与 main.py 一致）。

## 三、模块详细设计

### 3.1 `wegame_switcher.py`

纯工具模块，约 150 行。负责 WeGame 窗口管理、游戏内导航和游戏退出，覆盖完整 13 步流程。

**函数列表：**

| 步骤 | 函数 | 功能 | 关键逻辑 |
|------|------|------|----------|
| - | `activate_wegame(wegame_path)` | 激活 WeGame 窗口 | FindWindow 查找 → ShowWindow 恢复 → 未找到则 os.startfile 启动 |
| 1 | `click_account_switch(pos)` | 点击切换账号按钮 | 固定位置点击，仅首次需要 |
| 2 | `click_account(position)` | 点击指定位置的账号 | pyautogui.moveTo + click（坐标已缩放） |
| 3 | `click_login(login_btn_pos)` | 点击登录按钮 | 点击后 sleep(2) 等待登录完成 |
| 4 | `click_game_app(pos)` | 点击三角洲行动应用图标 | 在 WeGame 游戏库中选中三角洲行动 |
| 5 | `click_launch_btn(pos)` | 点击启动按钮 | 启动游戏，之后等待 50 秒加载 |
| 6 | `click_game_mode(pos)` | 点击烽火地带模式 | 在游戏大厅中选择模式 |
| 7 | `press_space_x3()` | 按 3 次空格跳过动画 | 间隔 0.5 秒，跳过开场/弹窗 |
| 8 | `press_tab()` | 按 Tab 键切换焦点 | 为下一步点击特勤处做准备 |
| 9 | `click_dash_entry(pos)` | 点击特勤处入口 | 打开特勤处制造界面 |
| - | `wait_game_window(timeout)` | 等待游戏窗口出现 | 轮询 FindWindow，超时返回 False |
| 11 | `exit_game(exit_method)` | 退出游戏 | alt_f4 / wm_close / taskkill |
| - | `wait_game_exit(timeout)` | 等待游戏关闭 | 轮询 FindWindow，超时强制结束 |
| 12 | `click_account(position)` | 点击账号（复用步骤 2） | 退出后 WeGame 回到账号选择界面 |
| 13 | `click_switch_user(pos)` | 点击切换用户按钮 | 回到账号列表选择其他 WeGame 账号 |

**坐标缩放机制：** 独立于 main.py，使用 `pyautogui.size()` 检测分辨率后计算 `scale_factor`。

### 3.2 `gui/account_panel.py`

Tkinter 子框架类 `AccountPanel(ttk.Frame)`，约 250 行。嵌入 MainWindow 的"多账号"标签页。

#### UI 结构

```
┌─────────────────────────────────────────────────────────┐
│ ┌───────────────────────┬─────────────────────────────┐ │
│ │ 账号列表 (Treeview)    │ 控制区                      │ │
│ │ ┌──┬──────┬──────────┐ │ [▶ 启动全部]  [⏹ 停止]    │ │
│ │ │# │ 名称 │ 坐标     │ │ ☐ 循环执行 时长:[600]秒   │ │
│ │ │1 │ 大号 │400, 300  │ │                            │ │
│ │ │2 │ 小号 │400, 380  │ │ [+添加]  [编辑]  [删除]    │ │
│ │ └──┴──────┴──────────┘ │                            │ │
│ │                        │ WeGame 配置:                │ │
│ │ 当前: 大号 (制造中)     │ 登录按钮: [960, 640]       │ │
│ │                        │ [获取位置] 退出: [alt_f4▼] │ │
│ ├───────────────────────┴─────────────────────────────┤ │
│ │ 运行日志（复用）                                      │ │
│ │ [10:00] 大号: 正在登录 WeGame...                      │ │
│ │ [10:02] 大号: 游戏已启动，开始制造                    │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### 组件说明

**账号列表 (Treeview)**
- 列：`#`、`名称`、`坐标`、`启用`、`状态`
- 状态列显示: 待机 / 登录中 / 制造中 / 已完成 / 失败跳过
- 双击编辑，勾选控制启用/禁用

**操作按钮**
- `[+添加]`：弹出对话框输入名称，支持"获取鼠标位置"按钮实时采集坐标
- `[编辑]`：修改已有账号的名称和坐标
- `[删除]`：确认后移除账号

**启动/停止控制**
- `[▶ 启动全部]`：对已启用账号按顺序执行调度
- `[⏹ 停止]`：设置 stop_event，当前账号制造完成后停止
- `☐ 循环执行`：勾选后所有账号执行完毕再从第一个开始
- `时长: [600] 秒`：每个账号的制造时长

**WeGame 配置**
- 完整 13 步坐标配置（每个按钮都有独立的 `[获取位置]` 按钮）：
  - 切换账号按钮坐标（步骤 1，可选）
  - 登录按钮坐标（步骤 3）
  - 三角洲应用图标坐标（步骤 4）
  - 启动按钮坐标（步骤 5）
  - 烽火地带模式坐标（步骤 6）
  - 特勤处入口坐标（步骤 9）
  - 当前账号头像坐标（步骤 12，可选）
  - 切换用户按钮坐标（步骤 13，可选）
- 退出方式下拉选择: alt_f4 / wm_close / taskkill

#### 调度逻辑（13 步完整流程）

```python
class AccountPanel(ttk.Frame):
    def __init__(self, parent, main_window):
        """main_window 提供: stop_event, log_queue, status_callback 等共享资源"""
    
    def _login_and_navigate(self, account, wg_cfg):
        """完整登录导航流程（步骤 1-9）"""
        name = account['name']
        
        # 步骤 1：点击切换账号按钮（如需）
        if wg_cfg.get('switch_account_btn_pos'):
            wegame_switcher.click_account_switch(wg_cfg['switch_account_btn_pos'])
            time.sleep(1)
        
        # 步骤 2：点击账号
        wegame_switcher.click_account(account['click_pos'])
        time.sleep(0.5)
        
        # 步骤 3：点击登录按钮
        wegame_switcher.click_login(wg_cfg['login_btn_pos'])
        
        # 步骤 4：等待 6 秒 → 点击三角洲行动应用
        time.sleep(6)
        wegame_switcher.click_game_app(wg_cfg['game_app_pos'])
        time.sleep(1)
        
        # 步骤 5：点击启动按钮
        wegame_switcher.click_launch_btn(wg_cfg['launch_btn_pos'])
        
        # 步骤 6：等待 50 秒 → 点击烽火地带模式
        if not wegame_switcher.wait_game_window(50):
            return False
        wegame_switcher.click_game_mode(wg_cfg['mode_btn_pos'])
        
        # 步骤 7：等待 10 秒 → 按 3 次空格
        time.sleep(10)
        wegame_switcher.press_space_x3()
        
        # 步骤 8：按 Tab 键
        wegame_switcher.press_tab()
        time.sleep(1)
        
        # 步骤 9：点击特勤处
        wegame_switcher.click_dash_entry(wg_cfg['dash_entry_pos'])
        time.sleep(3)
        return True
    
    def _run_scheduler(self):
        """在工作线程中运行多账号调度"""
        cfg = load_accounts_config()
        enabled = [a for a in cfg.get('accounts', []) if a.get('enabled', True)]
        wg_cfg = cfg.get('wegame', {})
        timeout = int(self.timeout_var.get())
        loop_mode = self.loop_var.get()
        
        if not enabled:
            print('[多账号] 没有已启用的账号')
            return
        
        while True:
            for account in enabled:
                if self.main_stop_event.is_set():
                    return
                
                name = account['name']
                print(f'=== {name}: 开始 ===')
                
                # 步骤 1-9：登录 + 导航到特勤处
                success = self._login_and_navigate(account, wg_cfg)
                if not success:
                    print(f'{name}: 导航失败，跳过')
                    self._update_status(name, '失败')
                    continue
                
                # 步骤 10：自动制造
                print(f'{name}: 开始制造（{timeout} 秒）')
                self._update_status(name, '制造中')
                
                timer = threading.Timer(timeout, self._on_account_timeout)
                timer.daemon = True
                timer.start()
                self.main_stop_event.clear()
                
                import main as auto_module
                try:
                    auto_module.main(
                        stop_event=self.main_stop_event,
                        status_callback=self.main_window.status_queue.put
                    )
                except Exception as e:
                    print(f'{name}: 制造异常: {e}')
                finally:
                    timer.cancel()
                
                if self.main_stop_event.is_set() and self._user_stop:
                    self._exit_and_switch(exit_method)
                    return
                
                # 步骤 11：退出游戏
                print(f'{name}: 退出游戏')
                wegame_switcher.exit_game(wg_cfg.get('exit_method', 'alt_f4'))
                wegame_switcher.wait_game_exit(30)
                
                # 步骤 12-13：准备下一个账号
                self._prepare_next_account(wg_cfg)
                print(f'{name}: 完成')
            
            if not loop_mode:
                break
        
        self._on_all_complete()
    
    def _prepare_next_account(self, wg_cfg):
        """步骤 12-13：切换到下一个账号"""
        # 步骤 12：点击当前账号头像，打开操作菜单
        wegame_switcher.click_account_avatar(wg_cfg.get('account_avatar_pos'))
        time.sleep(1)
        # 步骤 13：点击切换用户按钮回到账号列表
        if wg_cfg.get('switch_user_btn_pos'):
            wegame_switcher.click_switch_user(wg_cfg['switch_user_btn_pos'])
            time.sleep(2)
    
    def _on_account_timeout(self):
        """账号超时回调"""
        self._timer_fired = True
        self.main_stop_event.set()
        print('[多账号] 当前账号制造时间到，准备切换')
```

### 3.3 `gui/main_window.py` 修改方案

**修改点**：将原有控件包裹进 Notebook 标签页

```python
class MainWindow(tk.Tk):
    def _build_ui(self):
        # ── 标签页：单账号 | 多账号 ──
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.X, side=tk.TOP)
        
        # Tab 1 - 单账号（原有控件）
        self.single_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.single_tab, text='  单账号  ')
        self._build_single_account_ui(self.single_tab)
        
        # Tab 2 - 多账号（新面板）
        self.multi_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.multi_tab, text='  多账号  ')
        self.account_panel = AccountPanel(self.multi_tab, main_window=self)
        self.account_panel.pack(fill=tk.BOTH, expand=True)
        
        # ── 以下保持共享 ──
        # 部门状态（status_frame）
        # 运行日志（log_frame） 
        # 状态栏（status_bar）
```

`_build_single_account_ui(self, parent)` 将原有 `_build_ui` 中控制面板+推荐配方的逻辑提取到单独方法。

## 四、依赖变更

| 变更 | 说明 |
|------|------|
| 移除 `PyQt6` | 沿用现有 tkinter |
| 移除 `cryptography` | 不保存密码 |
| 移除 `psutil` | win32gui 替代 |
| **零新增依赖** | 全部用现有包 |

## 五、执行流程

### 首次使用配置流程

```
1. 用户手动打开 WeGame → 停在账号选择界面
2. 打开脚本 GUI → 切换到"多账号"标签页
3. 点击 [+添加] → 输入名称"大号"
4. 点击"获取位置" → 鼠标移到 WeGame 上对应账号按钮位置 → 确定
5. 重复步骤 3-4 添加其他账号
6. 配置 WeGame 各步骤坐标（用"获取位置"依次采集）：
   a. 登录按钮位置（步骤 3）
   b. 三角洲应用图标位置（步骤 4）
   c. 启动按钮位置（步骤 5）
   d. 烽火地带模式位置（步骤 6）
   e. 特勤处入口位置（步骤 9）
7. 点 [▶ 启动全部] 开始自动运行
```

### 运行时执行流程（13 步）

```
启动全部
  │
  ├─ 大号
  │   ├─ 1. 点击切换账号按钮（可选）
  │   ├─ 2. 点击账号 (962, 628)
  │   ├─ 3. 点击登录按钮 (960, 640)
  │   ├─ 4. 等待 6s → 点击三角洲应用 (150, 400)
  │   ├─ 5. 点击启动按钮 (960, 800)
  │   ├─ 6. 等待 50s → 点击烽火地带模式 (300, 500)
  │   ├─ 7. 等待 10s → 按 3 次空格
  │   ├─ 8. 按 Tab 键
  │   ├─ 9. 点击特勤处 (600, 350)
  │   ├─ 10. 自动制造（定时 timeout 秒）
  │   │    ├─ 迭代1: beep → dash_page() → OCR → craft → sleep
  │   │    ├─ 迭代2: ...
  │   │    └─ 定时器触发 → stop_event.set() → main() 退出
  │   ├─ 11. ALT+F4 退出游戏 → 等待关闭（超时 30s → taskkill）
  │   ├─ 12. 点击当前账号头像
  │   └─ 13. 点击切换用户（可选）
  │
  ├─ 小号
  │   └─ ...（同上 13 步）
  │
  └─ [循环模式] → 回到大号重新开始
      [单次模式] → 全部完成，停止
```

### 异常处理

| 场景 | 处理方式 |
|------|----------|
| WeGame 未安装 | 打印日志，跳过所有账号 |
| 游戏启动超时 | 跳过当前账号，继续下一个 |
| 制造中异常 | 记录错误，退出游戏，继续下一个 |
| 用户点击停止 | 当前迭代完成后退出循环 |
| 所有账号完成 | 日志提示，状态恢复为就绪 |

## 六、验证方法

### 阶段一：配置验证

1. 手动创建 `data/accounts.yaml` 或通过 GUI 添加测试账号
2. 检查文件格式是否正确，坐标是否合理

### 阶段二：WeGame 切换测试

1. 在 WeGame 中保存至少 2 个 QQ 账号
2. 单独测试 `wegame_switcher.activate_wegame()` → `click_account()` → `click_login()` 链路
3. 单独测试游戏内导航：`click_game_app()` → `click_launch_btn()` → 等待 50s → `click_game_mode()` → `press_space_x3()` → `press_tab()` → `click_dash_entry()`
4. 确保控制台日志正确输出每一步状态

### 阶段三：完整多账号流程

1. 启动 GUI → 切换到"多账号"标签页
2. 逐个用"获取位置"采集所有坐标点
3. 添加 2 个账号 → 点"启动全部"
4. 观察是否按完整 13 步流程执行：
   - 登录阶段（步骤 1-3）：切换账号 → 点击账号 → 登录
   - 导航阶段（步骤 4-9）：选游戏 → 启动 → 选模式 → 空格 → Tab → 特勤处
   - 制造阶段（步骤 10）：自动制造循环
   - 切换阶段（步骤 11-13）：退出 → 点击头像 → 切换用户
5. 中间点击"停止"验证能否中断

### 阶段四：回归测试

1. 切换到"单账号"标签页 → 点"启动"
2. 确认原有单账号功能不受影响
