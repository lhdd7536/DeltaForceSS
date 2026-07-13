# 制造材料补货功能设计

## 背景

新增自动补货功能，在多账号模式下，每天 2:00-5:00 窗口自动对每个已启用账号的制造材料（钛合金、高级燃料）进行库存检查，低于阈值时自动补货。

## 配置文件

### `user_config.yaml`

新增 `auto_replenish` 段：

```yaml
auto_replenish:
  enabled: false    # 全局开关，GUI 勾选框控制
  threshold: 3      # 低于此值触发补货
  quantity: 3       # "增加购买数量"按钮点击次数
```

补货材料固定为钛合金和高级燃料，不进入配置。补货坐标写入 `config.yaml` 的 `replenish_coords` 段。

## 新增文件：`replenishment.py`

### 坐标来源

坐标在 `config.yaml` 的 `replenish_coords` 段中定义（基于 1920×1080 基准），运行时通过 `scale_coords()` 缩放到当前分辨率：

```yaml
replenish_coords:
  dep_tab: [580, 55]          # 步骤9 点击部门标签
  quartermaster: [464, 107]   # 步骤10 点击军需处
  medical_dep: [555, 680]     # 步骤11 点击医疗部门
  collectibles_tab: [327, 127] # 步骤12 点击收集品界面
  materials:
    titanium_alloy: [1173, 481]  # 钛合金
    advanced_fuel: [305, 699]    # 高级燃料
  quantity_region: [1596, 775, 9, 17]  # 步骤14 x,y,w,h
  increase_btn: [1762, 833]     # 步骤15 增加购买数量
  fill_btn: [1638, 935]         # 步骤16 一键补齐
  buy_btn: [970, 754]           # 步骤17 购买
```

| 步骤 | 描述 | 坐标 |
|------|------|------|
| 9 | 点击部门标签 | (580, 55) |
| 10 | 点击军需处 | (464, 107) |
| 11 | 点击医疗部门 | (555, 680) |
| 12 | 点击收集品界面 | (327, 127) |
| 13a | 点击钛合金 | (1173, 481) |
| 13b | 点击高级燃料 | (305, 699) |
| 14 | 数量识别区域 | (1596, 775) - (1605, 792) |
| 15 | 增加购买数量 | (1762, 833) |
| 16 | 一键补齐 | (1638, 935) |
| 17 | 购买 | (970, 754) |

### 核心函数：`do_replenish_materials(threshold, quantity)`

调用前游戏角色已在主基地（步骤 1-8 完成）。

```
步骤 9: click_position(部门坐标), jitter_sleep(1)
步骤 10: click_position(军需处坐标), jitter_sleep(1)
步骤 11: click_position(医疗部门坐标), jitter_sleep(1)
步骤 12: click_position(收集品坐标), jitter_sleep(1)

for each 材料 in [钛合金, 高级燃料]:
    click_position(材料坐标), jitter_sleep(1)
    qty = OCR_quantity(数量区域)       # 9×17 px
    if qty >= threshold:
        continue                       # 无需补货
    for _ in range(quantity):
        click_position(增加购买数量坐标)  # 步骤15
        jitter_sleep(0.3)
    click_position(一键补齐坐标)          # 步骤16
    jitter_sleep(1)
    click_position(购买坐标)             # 步骤17
    jitter_sleep(2)
    # 购买完成后仍在收集品界面，直接处理下一材料

# 两材料都处理完毕
# 由调用方退出游戏
```

### OCR 数量识别

```python
def OCR_quantity(image) -> int:
    t_config = r'--psm 7 -c tessedit_char_whitelist=0123456789'
    text = pytesseract.image_to_string(image, config=t_config)
    text = text.strip()
    return int(text) if text else 0
```

- 区域 9×17 px，仅显示 1-2 位数字
- `--psm 7` 单行模式 + 数字白名单

### 点击行为

- 复用 `wegame_switcher.click_position()`：±3px 随机偏移 + 0.2-0.5s 随机移动时长
- 所有休眠使用 `jitter_sleep()`（±20% 随机波动）

## GUI 改动：`gui/account_panel.py`

### 控制面板新增控件

在"控制面板" LabelFrame 中，"自动执行至时" Spinbox 右侧新增：

- **勾选框：** `[x] 每日2-5点自动补货`（绑定 `auto_replenish.enabled`）
- **阈值 Spinbox：** `阈值:` 范围 1-99，默认 3
- **补货数量 Spinbox：** `补货量:` 范围 1-99，默认 3

### 配置持久化

- 补货配置保存在 `user_config.yaml` 的 `auto_replenish` 段
- 保存配置时一并写入，加载配置时读取
- `_save_wg_config()` / `_load_accounts()` 中处理

## 调度改动：`gui/account_panel.py`

### 新增成员

```python
self._replenish_after_cycle = False  # 制造结束后追加补货
```

### 2 点定时器：`_replenish_watchdog()`

独立守护线程，休眠到每天 2:00 自动醒来：

```
每次醒来:
  if not auto_replenish.enabled:
      继续睡到下次 2:00
      return

  if 制造循环正在运行 (_is_running):
      # 情况①：等本轮制造完再补
      _replenish_after_cycle = True
  else:
      next_mfg = 下次制造预约时间
      if next_mfg < 3:00 (当前小时):
          # 情况③：3 点前有预约，等制造完再补
          _replenish_after_cycle = True
      else:
          # 情况②：3 点后才预约，直接补货
          _run_replenish_cycle()
```

### 制造循环末尾追加

在 `_run_one_cycle()` 的 `finally` 块（现有 `_on_scheduler_stopped` 被调用前）检查：

```python
if self._replenish_after_cycle:
    self._replenish_after_cycle = False
    self._run_replenish_cycle()
```

### 补货循环：`_run_replenish_cycle()`

与 `_run_one_cycle()` 结构一致，遍历所有已启用账号：

```
for each 账号:
    if _user_stop: return
    wegame_switcher.activate_wegame()
    _login_and_navigate(账号, wegame_cfg)   # 复用现有步骤 1-8
    replenishment.do_replenish_materials(threshold, quantity)
    _exit_game(exit_method)
    wegame_switcher.exit_wegame()
```

### 线程管理

- `_replenish_watchdog()` 为独立守护线程，启动调度器时一并启动
- 停止调度器时一并停止（共享 `_user_stop` / `stop_event`）
- 使用 `_wait_check()` 可中断休眠

## 现有代码无侵入原则

- 制造循环 `_run_one_cycle()` 只加 3 行（finally 块中检查标志）
- `main.py` / `dash_page()` 完全不改动
- 补货流程完全独立，不依赖制造模块的状态

## 错误处理

- 补货过程中账号登录失败 → 跳过（与制造循环一致）
- OCR 数量失败（返回 0）→ 视为低于阈值，执行补货
- 购买界面未弹出 → 跳过该材料，处理下一个
- 补货循环整体异常 → 打印日志，不影响后续调度
