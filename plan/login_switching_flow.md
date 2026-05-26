# WeGame 登录切换账号操作流程

## 流程图

```
┌─────────────────────────────────────────────────────────────────┐
│  1. 点击"切换账号"按钮                                           │
│     → 固定位置点击 WeGame 窗口上的"切换账号"按钮                  │
├─────────────────────────────────────────────────────────────────┤
│  2. 点击账号                                                     │
│     → 固定位置点击目标账号的头像/名称                             │
├─────────────────────────────────────────────────────────────────┤
│  3. 点击"登录"按钮                                               │
│     → 固定位置点击登录按钮                                        │
│     → 等待游戏加载                                               │
├─────────────────────────────────────────────────────────────────┤
│  4. 等待 6 秒 → 点击"三角洲行动"应用                              │
│     → WeGame 游戏库中选中三角洲行动                               │
├─────────────────────────────────────────────────────────────────┤
│  5. 点击"启动"按钮                                               │
│     → 固定位置点击启动/开始游戏按钮                               │
├─────────────────────────────────────────────────────────────────┤
│  6. 等待 50 秒 → 点击"烽火地带"模式                              │
│     → 等待游戏加载到模式选择界面                                  │
│     → 固定位置点击烽火地带                                       │
├─────────────────────────────────────────────────────────────────┤
│  7. 等待 10 秒 → 按 3 次空格                                     │
│     → 连续按 3 次空格键（跳过开场动画/确认对话框）                │
├─────────────────────────────────────────────────────────────────┤
│  8. 按 Tab 键                                                    │
│     → 切换 UI 焦点                                               │
├─────────────────────────────────────────────────────────────────┤
│  9. 点击"特勤处"打开特勤处界面                                    │
│     → 固定位置点击特勤处入口                                     │
├─────────────────────────────────────────────────────────────────┤
│  10. 进行特勤处自动制造                                           │
│      → 调用 main.py 的主循环（复用现有制造逻辑）                  │
├─────────────────────────────────────────────────────────────────┤
│  11. 制造完成后退出 (ALT+F4)                                      │
│      → 发送 ALT+F4 关闭游戏窗口                                  │
├─────────────────────────────────────────────────────────────────┤
│  12. 点击当前账号头像                                           │
│      → 固定位置点击已登录账号的头像（打开切换用户菜单）          │
├─────────────────────────────────────────────────────────────────┤
│  13. 点击"切换用户"                                              │
│      → 回到步骤 2（选择下一个账号）或结束                         │
└─────────────────────────────────────────────────────────────────┘
```

## 详细步骤

### 步骤 1：点击切换账号按钮

- **操作位置**：WeGame 登录窗口右上角或账号区域
- **操作方式**：`click_position(switch_account_btn_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.switch_account_btn_pos`
- **备注**：仅当 WeGame 当前已登录了一个账号时需要先切换

### 步骤 2：点击账号

- **操作位置**：WeGame 登录窗口的账号列表中
- **操作方式**：`click_position(account.click_pos)`
- **坐标配置**：`accounts.yaml` → `accounts[].click_pos`
- **备注**：每个账号有独立的点击坐标

### 步骤 3：点击登录按钮

- **操作位置**：WeGame 登录窗口的登录按钮
- **操作方式**：`click_position(login_btn_pos)`，点击后等待 2-5 秒
- **坐标配置**：`accounts.yaml` → `wegame.login_btn_pos`
- **备注**：点击后 WeGame 会启动游戏并跳转到游戏库

### 步骤 4：等待 6 秒 → 点击三角洲行动应用

- **操作位置**：WeGame 游戏库中"三角洲行动"的图标区域
- **操作方式**：等待 6 秒 → `click_position(game_app_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.game_app_pos`
- **备注**：此步骤确保在 WeGame 游戏库中选中三角洲行动

### 步骤 5：点击启动按钮

- **操作位置**：WeGame 游戏详情页的"启动"按钮
- **操作方式**：`click_position(launch_btn_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.launch_btn_pos`
- **备注**：点击后游戏开始启动

### 步骤 6：等待 50 秒 → 点击烽火地带模式

- **操作位置**：游戏大厅的模式选择界面
- **操作方式**：等待 50 秒 → `click_position(mode_btn_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.mode_btn_pos`
- **等待时间**：50 秒（游戏加载 + 反作弊 + 登录验证）
- **备注**：50 秒为经验值，可根据实际游戏加载速度调整

### 步骤 7：等待 10 秒 → 按 3 次空格

- **操作位置**：游戏内（焦点在游戏窗口）
- **操作方式**：等待 10 秒 → `keyboard.send('space')` × 3（间隔 0.5 秒）
- **备注**：跳过开场动画、公告弹窗、确认对话框等

### 步骤 8：按 Tab 键

- **操作位置**：游戏内
- **操作方式**：`keyboard.send('tab')`
- **备注**：切换 UI 焦点，为下一步点击特勤处做准备

### 步骤 9：点击特勤处

- **操作位置**：游戏主界面的特勤处入口位置
- **操作方式**：`click_position(departments_coords['dash_entry'])`
- **坐标配置**：建议在 `config.yaml` 的 `departments_coords` 中新增 `dash_entry`
- **备注**：进入特勤处制造主界面

### 步骤 10：进行特勤处自动制造

- **操作方式**：复用 `main.py` 中的 `main(stop_event, status_callback)`
- **说明**：`main()` 函数内部包含 dash_page → list_page → craft 的完整制造流程
- **停止条件**：
  - 定时器超时（每账号配置的制造时长）
  - 用户点击"停止"按钮
  - 制造循环自然结束

### 步骤 11：制造完成后退出（ALT+F4）

- **操作位置**：游戏窗口（焦点在游戏）
- **操作方式**：`keyboard.send('alt+f4')`
- **备用方案**：`exit_game('taskkill')` 强制结束进程
- **备注**：退出后 WeGame 窗口会重新获得焦点

### 步骤 12：点击当前账号头像

- **操作位置**：WeGame 登录窗口中当前已登录账号的头像/名称区域
- **操作方式**：`click_position(account_avatar_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.account_avatar_pos`
- **备注**：点击当前账号头像弹出操作菜单，其中包含"切换用户"选项

### 步骤 13：点击切换用户

- **操作位置**：WeGame 登录窗口的"切换用户"按钮
- **操作方式**：`click_position(switch_user_btn_pos)`
- **坐标配置**：`accounts.yaml` → `wegame.switch_user_btn_pos`
- **备注**：在账号管理菜单中选择"切换用户"后回到账号列表

## 坐标配置汇总

建议在 `data/accounts.yaml` 中新增以下字段：

```yaml
accounts:
  - name: "大号"
    click_pos: [962, 628]      # 步骤 2：账号按钮位置

wegame:
  # 步骤 1（可选）
  switch_account_btn_pos: [1044, 580]  # 切换账号按钮
  # 步骤 3
  login_btn_pos: [960, 640]          # 登录按钮
  # 步骤 4
  game_app_pos: [150, 400]           # 三角洲行动应用图标
  # 步骤 5
  launch_btn_pos: [960, 800]         # 启动按钮
  # 步骤 6
  mode_btn_pos: [300, 500]           # 烽火地带模式
  # 步骤 9
  dash_entry_pos: [600, 350]         # 特勤处入口
  # 步骤 12（可选）
  account_avatar_pos: [1044, 580]    # 当前账号头像位置
  # 步骤 13（可选）
  switch_user_btn_pos: [1200, 100]   # 切换用户按钮
  exit_method: "alt_f4"
  account_timeout: 600
```

## 与代码的映射关系

| 步骤 | 函数 | 文件 |
|------|------|------|
| 1 | `click_account_switch()` | `wegame_switcher.py`（需新增） |
| 2 | `click_account(position)` | `wegame_switcher.py`（已有） |
| 3 | `click_login(login_btn_pos)` | `wegame_switcher.py`（已有） |
| 4 | `click_game_app()` | `wegame_switcher.py`（需新增） |
| 5 | `click_launch_btn()` | `wegame_switcher.py`（需新增） |
| 6 | `click_game_mode()` | `wegame_switcher.py`（需新增） |
| 7 | `press_space_x3()` | `wegame_switcher.py`（需新增） |
| 8 | `press_tab()` | `wegame_switcher.py`（需新增） |
| 9 | `click_dash_entry()` | `wegame_switcher.py`（需新增） |
| 10 | `main()` | `main.py`（已有） |
| 11 | `exit_game('alt_f4')` | `wegame_switcher.py`（已有） |
| 12 | `click_account_avatar()` | `wegame_switcher.py`（需新增） |
| 13 | `click_switch_user()` | `wegame_switcher.py`（需新增） |

## 单账号完整执行流程（伪代码）

```python
def login_and_craft(account, wegame_cfg):
    # 步骤 1-3：WeGame 登录
    activate_wegame()
    click_account_switch(wegame_cfg['switch_account_btn_pos'])  # 如需要
    click_account(account['click_pos'])
    click_login(wegame_cfg['login_btn_pos'])

    # 步骤 4：选中游戏
    time.sleep(6)
    click_game_app(wegame_cfg['game_app_pos'])

    # 步骤 5：启动游戏
    click_launch_btn(wegame_cfg['launch_btn_pos'])

    # 步骤 6：选择模式
    time.sleep(50)
    click_game_mode(wegame_cfg['mode_btn_pos'])

    # 步骤 7-8：跳过开场
    time.sleep(10)
    for _ in range(3):
        keyboard.send('space')
        time.sleep(0.5)
    keyboard.send('tab')
    time.sleep(1)

    # 步骤 9：打开特勤处
    click_dash_entry(wegame_cfg['dash_entry_pos'])
    time.sleep(3)

    # 步骤 10：自动制造
    main(stop_event=stop_event, status_callback=callback)

    # 步骤 11：退出游戏
    exit_game('alt_f4')
    wait_game_exit(30)
```
