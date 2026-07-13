# CLAUDE.md

本文件为 Claude Code 在此仓库中工作时提供指导和上下文。

## 项目概述

Delta Force 三角洲行动 自动化制造脚本。支持两种工作模式：

1. **单账号制造** — 截图 → OCR 文字识别 → 模拟鼠标键盘操作，自动完成游戏内制造流程
2. **多账号批量制造** — 通过 WeGame 账号切换，按顺序登录多个账号分别执行制造流程

## 运行环境

- **Python**: 3.11 (conda env: `deltaforce`)
- **OS**: Windows only (uses pywin32, keyboard, dxcam, pyautogui)
- **Tesseract-OCR**: bundled at `dist/Tesseract-OCR/`
- **Setup**: `conda run -n deltaforce pip install -r requirements.txt`

## 运行方式

### 默认启动：GUI 模式

```bash
set PYTHONIOENCODING=utf-8
D:/Anaconda3/envs/deltaforce/python.exe gui/app.py
```

GUI 基于 tkinter，包含"制造"标签页（启动/停止控制、实时部门状态、运行日志、今日推荐配方）和"多账号"标签页（账号列表管理、WeGame 配置、调度控制）。**默认启动方式，直接运行即可。**

### 后台 CLI 模式（仅调试用）

```bash
set PYTHONIOENCODING=utf-8
D:/Anaconda3/envs/deltaforce/python.exe main.py
```

### 打包为 EXE

```bash
cd H:\GithubProjects\DeltaForceSS
# 清理旧输出
rm -rf dist/DeltaForceSS build
# 打包
conda run -n deltaforce pyinstaller build.spec
# 将配置和资源文件移出 _internal/ 到 EXE 同级
cd dist/DeltaForceSS
mv _internal/config.yaml .
mv _internal/user_config.yaml .
mv _internal/data .
mv _internal/Tesseract-OCR .
```

> **注意**：EXE 模式下使用 `sys.executable` 定位资源文件（`config.yaml`、`user_config.yaml`、`data/accounts.yaml` 等），因此启动时 CWD 无关紧要。打包前修改了源码后必须重新打包才会生效。

### 关闭程序

```bash
# 查看 Python 进程
tasklist //fi "IMAGENAME eq python.exe"

# 强制关闭所有 Python 进程（GUI 和后台任务）
taskkill //f //im python.exe

# 或按 PID 单独关闭
taskkill //f //pid <进程ID>
```

> 注意：在 git-bash 中使用 `taskkill` 时，参数前需加双斜杠 `//` 避免路径转换。`pkill` 在 Windows git-bash 中可能无效。

## 架构说明

### 单账号模式 (`main.py`)

核心流程如下：

1. **主循环** (`main()`) — 无限循环：蜂鸣 → 恢复游戏窗口 → 检查分辨率 → 更新配置 → `dash_page()` → sleep(剩余时间) → 重复
2. **仪表盘** (`dash_page()`) — OCR 识别各部门状态（空闲/进行中/已完成）→ 收集已完成项 → 对有挂起项目的空闲部门触发 `list_page()`
3. **列表导航** (`list_page_operation()`) — 滚动可制造物品列表，OCR 识别物品名称，与配置模糊匹配，点击制造
4. **自动购买材料** (`initalize_preparation()`) — 检测缺少的材料，打开交易行，OCR 价格，在可承受范围内购买

### 多账号模式 (`gui/account_panel.py` + `wegame_switcher.py`)

以 `AccountPanel` (`gui/account_panel.py`) 为入口，按顺序遍历 `data/accounts.yaml` 中启用的账号，每个账号自动执行登录 → 等待 → 制造 → 退出的完整流程：

1. **登录阶段（步骤 1-3）** — 激活 WeGame → 点击账号管理 → 选择账号 → 点击登录
2. **启动游戏（步骤 4-5）** — 等 WeGame 主窗口加载 → 点击三角洲行动应用 → 点击启动按钮
3. **导航到制造（步骤 6-9）** — 等游戏启动 → 选择烽火地带模式 → 跳过开场动画 → 进入特勤处
4. **执行制造** — 由 `main.py:dash_page()` 完成一轮制造操作
5. **退出** — 按配置的 `exit_method` (alt_f4/wm_close/taskkill) 退出游戏
6. **循环**— 退出 WeGame → 切换到下一账号 → 重复

### 自动补货模式

每日 2:00 定时触发，或通过手动补货按钮启动。按顺序遍历启用账号，登录游戏后导航到军需处 → 收集品界面，检查钛合金和高级燃料库存，低于阈值时自动购买补货。两种材料使用独立的 OCR 坐标：

- 钛合金 `quantity_region: [1668, 774, 12, 19]`
- 高级燃料 `quantity_region: [1593, 774, 12, 19]`

补货登录跳过"点击特勤处"步骤（由补货流程自行导航），其他登录步骤与制造一致。

## 核心模块

### `wegame_switcher.py` — WeGame 窗口管理

窗口操作工具模块，负责：

- **窗口查找** — 按类名/标题查找窗口，支持超时轮询和模糊匹配降级
- **前台置前** (`bring_to_foreground`) — 使用 `SwitchToThisWindow` 绕过 Windows 前台权限限制；如果 `GameInputSvc.exe` 抢前台，自动 kill 后重试
- **坐标缩放** — 所有坐标基于 1920×1080 基准，运行时自动缩放到当前分辨率
- **鼠标点击** (`click_position`) — 缩放坐标后加入 ±3px 随机偏移和随机移动时长，模拟真人操作
- **账号点击** (`scroll_then_click`) — 滚动后点击，用于第 4-5 个账号（超出可视范围需先滚动）
- **游戏退出** (`exit_game`) — 支持 alt_f4 / wm_close / taskkill 三种退出方式
- **进程管理** — `exit_wegame()` 强杀 WeGame 进程，`wait_game_exit()` 轮询等待游戏窗口关闭

### `replenishment.py` — 制造材料补货模块

自动导航到军需处 → 收集品界面，OCR 识别钛合金/高级燃料库存数量，低于阈值时自动完成购买流程。坐标从 `config.yaml` 的 `replenish_coords` 加载，每个材料独立的 `quantity_region`。

### `gui/account_panel.py` — 多账号管理面板

`AccountPanel` 类（ttk.Frame），嵌入 GUI 的"多账号"标签页：

- **账号列表** — Treeview 表格显示账号名/启用状态/完成时间，支持添加/删除/编辑/排序
- **WeGame 配置** — 各步骤点击坐标、等待时长、退出方式等可配置项
- **调度控制** — 启动/停止多账号循环，按完成时间排序自动调度
- **状态反馈** — 实时日志输出、当前账号/步骤显示

### `gui/main_window.py` — 主窗口

`MainWindow` 类（tk.Tk），应用主入口：

- **制造标签页** — 启动/停止/暂停按钮、部门状态卡片、运行日志、推荐配方
- **多账号标签页** — AccountPanel 实例
- **F8 快捷键** — 全局热键，效果等同点击"启动"按钮

## 配置文件

- `config.yaml` — 物品数据库 (`departments`)、屏幕坐标 (`departments_coords`)、各部门 OCR 配置、匹配阈值 (`OCR_factors`)、补货坐标 (`replenish_coords` 含各材料 click/quantity_region)
- `user_config.yaml` — 用户制造队列 (`tech/work/medical/armor`)、自动执行时段 (`auto_run_until_hour`)、Tesseract 路径、调试/后台模式开关、自动补货配置 (`auto_replenish` 含 enabled/threshold/quantity)
- `data/accounts.yaml` — 多账号配置：
  - `accounts` — 账号列表（名称、点击坐标、是否启用、预计完成时间、滚动次数）
  - `wegame` — WeGame 操作坐标（账号管理按钮、登录按钮、游戏应用等）和各步骤等待时长

## 关键机制

### GameInputSvc.exe 抢前台处理

WeGame 启动后，Microsoft Game Input Service 可能抢前台导致 WeGame 窗口无法激活。处理策略：

- `bring_to_foreground()` 中：先尝试 SwitchToThisWindow → 检测前台是否为目标窗口/进程 → 若发现 GameInputSvc 抢前台，自动 taskkill 后重试
- 步骤 4 点击三角洲应用前：再次检测前台进程，若为 GameInputSvc 则自动清理

### 坐标系统

所有坐标基于 1920×1080 基准定义，运行时通过 `scale_factor = width / 1920` 缩放。仅支持 16:9 分辨率（1080p、1440p、4K）。

### 点击偏移

`click_position()` 自动在目标坐标上加入 ±3px 随机偏移，移动时长在 0.2-0.5s 范围随机，模拟真人点击行为。

### 截屏与识别 (单账号模式)

使用 PIL `ImageGrab.grab()` 截取屏幕，经 OpenCV 处理（灰度化、Otsu 二值化），Tesseract OCR 识别文字，`rapidfuzz` 进行字符串匹配。

- **空闲检测** (`OCR_is_free`) 使用 `fuzz.ratio`（完整匹配），阈值 > 60，避免单字子串误匹配为"空闲中"
- **物品名称匹配** (`best_match_item`) 使用 `fuzz.ratio`，配合各部门独立的 `OCR_factors` 阈值
- **计时器 OCR** — OCR 识别制造剩余时间（格式 `MM:SS`），用于判断部门状态是"进行中"还是"已完成"。需注意 OCR 误读（如 `O` → `0`、`l` → `1`）可能导致完成状态被误判为进行中，影响成品领取

### UTF-8 编码兼容

`utils.py` 中的文件读取操作使用编码自动检测回退机制：
1. 优先尝试 UTF-8 编码读取
2. 若失败则使用 `chardet` 自动检测编码后重试
3. 避免 GBK 编码文件在 UTF-8 模式下直接崩溃

## 测试

- `list_OCR_test(department, categories)` — 验证指定部门物品类别的 OCR 识别效果
- `test1()` — 枚举所有可见 Windows 窗口
- `test2()` — 验证配置加载和 user_config 更新
- 在 `user_config.yaml` 中启用 `debug_mode: true` 可将截图保存到 `./log/`

## 版本历史

| 版本 | 提交 | 说明 |
|------|------|------|
| v3.2 | `890c7cd` | 原仓库最新版本 (S9 赛季) |
| v3.3 | `f6e1b03` | 多账号制造流程重构：启动即走、阶段分组GUI、F8快捷键、可配置等待时长 |
| v3.4 | `ee842b4` | 修复空闲检测误判：partial_ratio → ratio；auto_run_until_hour 可配置 |
| v3.5 | `fa5b808` | 修复计时器OCR误读导致部门状态误判；UTF-8编码兼容回退机制；GUI多账号面板新增自动执行时段控件；手动更新配方按钮 |
| v3.6 | `22c7aa0` | 新增每日自动补货功能：看门狗定时2点触发、独立补货循环、GUI配置阈值/补货量/手动补货按钮；钛合金和高级燃料使用独立quantity_region坐标 |
