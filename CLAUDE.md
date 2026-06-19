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

- `config.yaml` — 物品数据库 (`departments`)、屏幕坐标 (`departments_coords`)、各部门 OCR 配置、匹配阈值 (`OCR_factors`)
- `user_config.yaml` — 用户制造队列 (`tech/work/medical/armor`)、Tesseract 路径、调试/后台模式开关
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
