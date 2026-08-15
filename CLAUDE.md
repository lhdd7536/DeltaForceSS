# CLAUDE.md

本文件为 Claude Code 在此仓库中工作时提供指导和上下文。

## 项目概述

Delta Force 三角洲行动 自动化制造脚本。支持两种工作模式：

1. **单账号制造** — 截图 → OCR 文字识别 → 模拟鼠标键盘操作，自动完成游戏内制造流程
2. **多账号批量制造** — 通过 WeGame 账号切换，按顺序登录多个账号分别执行制造流程

辅助功能：**每日推荐配方自动抓取**（orzice.com）、**每日自动补货**（钛合金/高级燃料，2:00 定时）、**PyInstaller EXE 打包**。

## 运行环境

- **Python**: 3.11 (conda env: `deltaforce`，路径 `D:\Anaconda3\envs\deltaforce`)
- **OS**: Windows only (uses pywin32, keyboard, pyautogui, psutil)
- **Tesseract-OCR**: bundled at `dist/Tesseract-OCR/`；统一由 `utils.resolve_tesseract_path()` 定位（配置路径 → `dist/Tesseract-OCR` → 项目根 `Tesseract-OCR`）
- **Setup**: `conda run -n deltaforce pip install -r requirements.txt`
- **可选依赖**: `playwright`（每日推荐抓取用，未安装时自动跳过该功能）

## 运行方式

### 默认启动：GUI 模式

```bash
set PYTHONIOENCODING=utf-8
D:/Anaconda3/envs/deltaforce/python.exe gui/app.py
```

GUI 基于 tkinter，包含"单账号"标签页（启动/停止控制、后台/调试模式开关、今日推荐配方、运行日志）和"多账号"标签页（账号列表管理、循环调度、自动补货配置、WeGame 配置）。**默认启动方式，直接运行即可。**

### 后台 CLI 模式（仅调试用）

```bash
set PYTHONIOENCODING=utf-8
D:/Anaconda3/envs/deltaforce/python.exe main.py
```

### 打包为 EXE

```bash
cd H:\GithubProjects\DeltaForceSS
build.bat
```

`build.bat` 会自动：激活 conda 环境 → 清理旧输出 → `pyinstaller build.spec` → 将 `_internal/` 中的 `config.yaml`、`user_config.yaml`、`data`、`Tesseract-OCR` 移动到 EXE 同级。

> **注意**：EXE 模式下所有模块通过 `core.utils.project_root()`（基于 `sys.executable`）统一定位资源文件（`config.yaml`、`user_config.yaml`、`data/accounts.yaml` 等），因此启动时 CWD 无关紧要。打包前修改了源码后必须重新打包才会生效。
>
> 打包相关文件：`build.spec`（PyInstaller 配置，`runtime_hooks` 指向 `packaging/runtime_hook.py` 修复 Tcl/Tk 路径，datas 打包 `_tcl_data`/`_tk_data`）、`packaging/runtime_hook.py`（运行时设置 `TCL_LIBRARY`/`TK_LIBRARY` 环境变量）。GUI 隐藏控制台后 stdout 重定向到 `log/app.log`（见 `gui/app.py`）。

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

### 单账号模式（`core/automator.py` 业务流程 + `main.py` 薄壳入口）

代码已按职责拆分并收敛为 `core/` 包：`core/utils`（共享工具）、`core/config_store`（配置与全局状态）、`core/vision`（截图/图像）、`core/ocr`（识别/匹配）、`core/automator`（业务流程）、`core/wegame_switcher`（WeGame 窗口管理）、`core/replenishment`（补货）、`core/daily_fetcher`（每日配方）。`main.py` 为薄壳（主循环入口 + 调试函数），`gui/` 为界面，`tests/` 为 pytest 测试，`scripts/` 为调试脚本，`packaging/` 为打包钩子。

核心流程如下：

1. **主循环** (`main(stop_event=None, status_callback=None, single_cycle=False)`) — 无限循环：蜂鸣 → 恢复游戏窗口（`UnrealWindow` / `三角洲行动  `）→ 检查分辨率 → 更新配置 → `dash_page()` → 可中断休眠到最短剩余时间 → 重复
   - `stop_event`：threading.Event，设置后所有休眠立即中断（`_interruptible_sleep`，±20% 随机抖动最大 30s）
   - `status_callback(remain_times, wait_list)`：每轮报告状态（GUI 刷新用）
   - `single_cycle=True`：仅执行一轮 dash_page 后返回（多账号"启动即走"模式用）
2. **页面检测** (`is_main_page()`) — OCR 识别 `tech_dep_region` 区域是否含"技术中心"，失败 2 次后保存 `main_page_fail_full` / `main_page_fail_region` 截图到 `log/` 并抛出 `IncorrectPageError`
3. **仪表盘** (`dash_page()`) — OCR 识别各部门状态（空闲/进行中/已完成）→ 收集已完成项（点击 + 空格键）→ 对有挂起项目的空闲部门触发 `list_page()`；随后最多 3 轮重试（间隔 5s，带 `valid_timer_count` 截屏有效性检查）处理轮次间新完成/空闲的部门
4. **列表导航** (`list_page_operation()`) — 滚动可制造物品列表，OCR 识别物品名称，与配置模糊匹配（`fuzz.ratio` + 各部门 `OCR_factors` 阈值），滚动到底部判定"未找到"（含 `侧置` 特例），点击制造
5. **制造与消耗** (`craft()`) — 点击物品 → `initalize_preparation()` 自动购买材料 → 点击建造按钮**成功后才** `write_user_config()` 消耗队列（避免制造失败时丢失配置项）
6. **自动购买材料** (`initalize_preparation()` / `buy_material()`) — `find_buy_state()` 检测缺少材料（白像素占比判断 3/4 材料按钮状态）→ 打开交易行 → OCR 价格 → 点击购买，最多重试 11 次，无法购买的物品（高级燃料、钛合金）跳过
7. **部门状态判定** (`department_status()`) — 先 OCR "空闲中"（`fuzz.ratio` > 60，避免单字子串误判）；非空闲则 OCR 计时器（`MM:SS` 白名单，`--psm 7`）：计时器区域空白 → 已完成(-1)；有文本但无法解析为时间 → 视为已完成（防 OCR 噪声如 `7` 误判）；可解析 → 返回剩余秒数

### 多账号模式 (`gui/account_panel.py` + `wegame_switcher.py`)

以 `AccountPanel` (`gui/account_panel.py`) 为入口，按顺序遍历 `data/accounts.yaml` 中启用的账号，每个账号自动执行登录 → 制造 → 退出的完整流程：

1. **激活 WeGame** — `activate_wegame()`：先找现有窗口（快速路径）；无窗口但进程存在 → 杀残留进程重启；两者皆无 → 自动检测路径启动（`_find_wegame_path()`：运行中进程 → 常见安装路径 → 遍历盘符），最多等 24s
2. **登录阶段（步骤 1-3）** — 点击账号管理 → 点击账号（`scroll_before_click > 0` 时先在同一位置向下滚轮 N 次，用于第 4/5 个账号）→ 点击登录
3. **启动游戏（步骤 4-5）** — 等 `wait_before_app` 秒（点击前检测前台进程，若 GameInputSvc 抢前台则 taskkill）→ 点击三角洲行动应用 → 点击启动按钮
4. **导航到制造（步骤 6-9）** — 轮询等游戏窗口出现（最长 `wait_game_launch` 秒，出现后等满总时长加载到主菜单）→ 双击烽火地带模式 → 等待后按 3 次空格跳过开场动画 → 按 Tab → 点击特勤处入口
5. **执行制造（步骤 10）** — 以 `main()` + `single_cycle=True` 执行一轮完整 dash_page（启动即走，不等完成）；通过 `status_callback` 捕获各部门剩余时间，取最短者写入账号 `estimated_end`（预计完成时间，tech 部门排除）
6. **退出** — 按配置的 `exit_method` (alt_f4/wm_close/taskkill) 退出游戏（带 30s 超时强制 taskkill 轮询），随后 `exit_wegame()` 强杀 WeGame，为下个账号准备干净环境
7. **循环** — 所有账号处理完后，若账号间 `estimated_end` 相差超过 8h 判定有账号制造失败（`_cycle_has_failure`）；预约模式下失败自动重试，最多 3 轮

**循环执行（预约监控）** — GUI 勾选"循环执行"后启动监控线程：按所有账号 `estimated_end` 最晚时间 + 1 分钟计算下次执行；`auto_run_until_hour` 之前自动执行不弹窗，之后弹窗确认（`messagebox.askyesno`）；无完成时间记录时降级用 `loop_interval` 固定间隔（默认 28800s）。

### 每日推荐配方 (`daily_fetcher.py`)

- 数据源：orzice.com/v/rb（Playwright 加载 Vue SPA 渲染后的 HTML，`channel="chrome"` headless）
- 解析：BeautifulSoup 按 `.box` / `.orzice-list-title` / `.list-item-title` 提取四大台（技术中心/工作台/制药台/防具台）推荐物品
- 匹配：网站物品名与 `config.yaml` 已有物品 `fuzz.ratio` 匹配（阈值 60），取最高分者写入 `user_config.yaml`（**tech 始终跳过**，使用配置默认制造）
- 触发：`main()` 启动时若 `auto_update_recipes: true` 调用 `maybe_update_recipes()`（每天一次，日期缓存 `data/last_update_date.txt`）；GUI"手动更新"按钮调用 `force_update_recipes()`（忽略日期检查）

### 自动补货模式

每日 2:00 定时触发（`_replenish_watchdog` 看门狗线程，随多账号调度启动/预约监控启动时一并启动），或通过"手动补货"按钮启动。按顺序遍历启用账号，登录游戏后导航到军需处 → 收集品界面（`replenishment.py`），检查钛合金和高级燃料库存，低于阈值时自动购买补货，补货完成后自动整理仓库（ESC → 仓库 → 整理 → 确认，步骤 18-21）。两种材料使用独立的 OCR 坐标：

- 钛合金 `quantity_region: [1668, 774, 12, 19]`
- 高级燃料 `quantity_region: [1593, 774, 12, 19]`

补货登录跳过"点击特勤处"步骤（`_login_and_navigate(..., skip_step9=True)`，由补货流程自行导航）。2:00 触发时若制造循环正在运行，则标记 `_replenish_after_cycle`，等本轮制造结束后再执行补货。

## 核心模块

### `main.py` — 单账号模式入口（薄壳）

仅保留：主循环入口 `main()`（GUI / 多账号模块通过 `import main as auto_module; auto_module.main(...)` 调用）、调试测试函数（`list_OCR_test` / `test1` / `test2`）与命令行入口。业务逻辑已拆至以下模块：

### `core/automator.py` — 单账号制造业务流程

主循环 `main()`、仪表盘 `dash_page()`（含 3 轮重试）、列表导航 `list_page_operation()`、制造与消耗 `craft()`、自动购买材料（`initalize_preparation` / `buy_material` / `find_buy_state`）、部门状态判定 `department_status()`、页面检测 `is_main_page()`、可中断休眠 `_interruptible_sleep()`、蜂鸣与 `alt_tab`。状态经 `from core import config_store as cs` 实时访问。

### `core/config_store.py` — 配置与全局状态

集中管理 `config` / `user_config` / `OUTPUT_DIR` / `TESSERACT_PATH` / `scale_factor` / `departments_coords` / `debug_mode` / `wait_list` / `_global_stop_event` 的加载与读写（import 时加载，与原 main.py 行为一致），以及 `scale_coords()` / `update_wait_list()` / `write_user_config()`（ruamel 保留注释）/ `set_screen_resolution()` / `setup_output_directory()`。

### `core/vision.py` — 截图与图像处理

`cut_by_lines()`、`screenshot()`（PIL `ImageGrab.grab()` → OpenCV 灰度/Otsu 二值化，debug_mode 下保存 original/gray/binary/combinedBinary 到 `log/`）、`cropImage()`、`save_image()`、`debug_visualize_lines()`、`match_list_items()`（列表分割线检测 + 单元格切分）。

### `core/ocr.py` — OCR 识别与文本匹配

`OCR_is_free` / `OCR_item_name` / `OCR_remain_time` / `OCR_price`、`best_match_item`（rapidfuzz）、`time_to_seconds`（仅支持 `HH:MM:SS` 三段格式，`MM:SS` 解析失败返回 None 为既有行为）。

### `core/wegame_switcher.py` — WeGame 窗口管理

窗口操作工具模块，负责：

- **窗口查找** (`find_window`) — 按类名/标题查找窗口，支持超时轮询（0.5s 间隔）和 `EnumWindows` 标题模糊匹配降级
- **前台置前** (`bring_to_foreground`) — 使用 `SwitchToThisWindow` 绕过 Windows 前台权限限制；若 `GameInputSvc.exe` 抢前台，自动 taskkill 后重试
- **坐标缩放** — 所有坐标基于 1920×1080 基准，运行时自动缩放到当前分辨率
- **鼠标点击** (`click_position`) — 缩放坐标后加入 ±3px 随机偏移和随机移动时长（0.2-0.5s），模拟真人操作；`pyautogui.FAILSAFE = False`
- **账号点击** — `click_account`（直接点击）/ `scroll_then_click`（先向下滚轮 N 次再点击，用于超出可视范围的账号）
- **导航步骤函数** — `click_account_management` / `click_game_app` / `click_launch_btn` / `click_game_mode` / `press_space_x3` / `press_tab` / `click_dash_entry`
- **游戏退出** (`exit_game`) — 支持 alt_f4 / wm_close / taskkill 三种退出方式；`wait_game_exit()` 轮询等待窗口关闭，超时强制结束
- **进程管理** — `exit_wegame()` 强杀 WeGame 进程（`_hide_cmd` 用 `subprocess.CREATE_NO_WINDOW` 隐藏命令行窗口）

### `core/replenishment.py` — 制造材料补货模块

自动导航到军需处 → 收集品界面，OCR 识别钛合金/高级燃料库存数量（`OCR_quantity`，`--psm 7` 数字白名单），低于阈值时点击增加数量/一键补齐/购买完成补货。坐标从 `config.yaml` 的 `replenish_coords` 加载，每个材料独立的 `quantity_region`（`click_position` 内部缩放，region 在本模块内缩放）。

### `core/daily_fetcher.py` — 每日推荐配方抓取

见上文"每日推荐配方"小节。入口：`maybe_update_recipes()`（自动）/ `force_update_recipes()`（手动）。

### `core/utils.py` — 共享工具（全项目统一复用）

- `project_root()` — 项目根目录（源码模式为仓库根，EXE 模式为 EXE 所在目录），所有模块统一通过它定位资源
- `calc_jitter(seconds)` — ±20% 随机波动时长（最大抖动 30s）
- `jitter_sleep(seconds)` — 带随机波动的休眠
- `read_with_encoding_fallback(path, primary='utf-8', fallback='gbk')` — 读取文件，UTF-8 失败时回退 GBK（兼容中文 Windows 旧配置；写操作一律 UTF-8）
- `load_yaml(path)` — PyYAML safe_load + 编码回退（只读场景）
- `load_ruamel(path)` / `dump_yaml_rt(path, data)` — ruamel 读写（保留注释与 flow style），供需要写回配置的场景使用
- `resolve_tesseract_path(configured_path=None)` — 定位 tesseract.exe：配置路径 → `dist/Tesseract-OCR` → 项目根 `Tesseract-OCR`
- `click_at(x, y, jitter=3)` — 屏幕坐标点击原语（不做缩放）：±jitter 随机偏移 + 0.2-0.5s 随机移动时长；`main.py` 与 `wegame_switcher.py` 的 `click_position()` 均基于它实现

### `gui/app.py` — 启动入口

隐藏控制台时（EXE 模式）将 stdout 重定向到 `log/app.log`，创建 `MainWindow`。

### `gui/main_window.py` — 主窗口

`MainWindow` 类（tk.Tk），应用主入口：

- **单账号标签页** — 启动/停止按钮、状态指示灯（红/绿/橙）、后台模式/调试模式勾选（写回 `user_config.yaml`）、快捷键提示、今日推荐配方面板（更新时间、自动更新勾选、手动更新按钮，后台线程调 `force_update_recipes`）、运行日志（stdout 重定向到队列，主线程 100ms 轮询刷新）
- **多账号标签页** — AccountPanel 实例
- **快捷键** — 从 `user_config.yaml` 的 `hotkey` 字段读取（默认 `f8`），绑定切换启动/停止（单账号运行中→停止；多账号运行中→停止调度；否则启动单账号）

### `gui/account_panel.py` — 多账号管理面板

`AccountPanel` 类（ttk.Frame），嵌入 GUI 的"多账号"标签页：

- **账号列表** — Treeview 表格显示序号/名称/坐标/滚轮次数/启用/完成时间，支持添加/删除/编辑（双击）/上移/下移/启用禁用
- **控制面板** — 启动全部/停止按钮、循环执行勾选 + 循环间隔、自动执行至时 Spinbox（`auto_run_until_hour`）、自动补货配置（每日 2 点自动补货勾选、阈值、补货量、手动补货按钮）
- **WeGame 配置** — 按阶段分组（登录阶段 1-3 / 启动阶段 4-5 / 导航阶段 6-9 / 退出阶段 11），可滚动区域，坐标字段支持"获取"按钮 3 秒倒计时捕获鼠标位置；WeGame 路径、退出方式下拉框、保存配置
- **调度控制** — 单轮制造循环（`_run_one_cycle`）、预约监控（`_schedule_monitor_thread`）、补货循环（`_run_replenish_cycle`）、2 点看门狗（`_replenish_watchdog`）、失败自动重试（最多 3 轮）
- **状态反馈** — 实时日志（统一由单账号日志区域输出）、当前账号/步骤状态标签

## 配置文件

- `config.yaml` — 物品数据库 (`departments`，按部门/类别分级，S10 赛季物品)、屏幕坐标 (`departments_coords`：dash_page 各部门 free/timmer 区域、列表 list_point/list_size/item_size、交易行 price/buy、build_position、tech_dep_region)、各部门 OCR 配置 (`OCR_configs`) 与匹配阈值 (`OCR_factors`：tech 71 / work 96.5 / medical 80 / armor 80)、补货坐标 (`replenish_coords` 含各材料 click/quantity_region)
- `user_config.yaml` — 用户制造队列 (`tech/work/medical/armor`，`[物品名, 数量]`，-1 为无限)、自动执行时段 (`auto_run_until_hour`)、Tesseract 路径 (`TESSERACT_PATH`)、快捷键 (`hotkey`)、调试/后台模式开关 (`debug_mode` / `background_mode`)、自动更新配方 (`auto_update_recipes`)、自动补货配置 (`auto_replenish` 含 enabled/threshold/quantity)
- `data/accounts.yaml` — 多账号配置：
  - `accounts` — 账号列表（名称、点击坐标 `click_pos`、是否启用、预计完成时间 `estimated_end`、滚动次数 `scroll_before_click`）
  - `wegame` — WeGame 操作坐标（`switch_account_btn_pos`、`login_btn_pos`、`game_app_pos`、`launch_btn_pos`、`mode_btn_pos`、`dash_entry_pos`）和各步骤等待时长（`wait_before_app`、`wait_game_launch`、`wait_before_space`）、`exit_method`、`loop_interval`、`wegame_path`

## 关键机制

### GameInputSvc.exe 抢前台处理

WeGame 启动后，Microsoft Game Input Service 可能抢前台导致 WeGame 窗口无法激活。处理策略：

- `bring_to_foreground()` 中：先尝试 SwitchToThisWindow → 检测前台是否为目标窗口/进程 → 若发现 GameInputSvc 抢前台，自动 taskkill 后重试
- 步骤 4 点击三角洲应用前：读取前台进程名，若为 GameInputSvc 则自动清理

### 坐标系统

所有坐标基于 1920×1080 基准定义，运行时通过 `scale_factor = width / 1920` 缩放。仅支持 16:9 分辨率（1080p、1440p、4K），非法分辨率抛出 `IncorrectResolution`。

### 点击偏移与随机化

`click_position()` 自动在目标坐标上加入 ±3px 随机偏移，移动时长在 0.2-0.5s 范围随机；所有休眠使用 ±20% 随机波动（最大 30s），模拟真人行为。`pyautogui.FAILSAFE = False` 禁用角落保护。

### 截屏与识别 (单账号模式)

使用 PIL `ImageGrab.grab()` 截取屏幕（`screenshot()`，已从 dxcam 迁移），经 OpenCV 处理（灰度化、Otsu 二值化），Tesseract OCR 识别文字，`rapidfuzz` 进行字符串匹配。

- **空闲检测** (`OCR_is_free`) 使用 `fuzz.ratio`（完整匹配），阈值 > 60，避免单字子串误匹配为"空闲中"
- **物品名称匹配** (`best_match_item`) 使用 `fuzz.ratio`，配合各部门独立的 `OCR_factors` 阈值；`OCR_item_name` 有手动修正（"番"→"盔"）
- **计时器 OCR** — OCR 识别制造剩余时间（格式 `MM:SS`），用于判断部门状态是"进行中"还是"已完成"。需注意 OCR 误读（如 `O` → `0`、`l` → `1`）可能导致完成状态被误判为进行中；反过来计时器区域有噪声文本但无法解析为时间时按已完成处理

### UTF-8 编码兼容

`utils.py` 中的文件读取操作使用编码自动回退机制：
1. 优先尝试 UTF-8 编码读取
2. 若失败则回退 GBK 编码重试（无 chardet 依赖）
3. 避免 GBK 编码文件在 UTF-8 模式下直接崩溃；写操作一律 UTF-8

### 可中断休眠

所有长休眠通过 `_interruptible_sleep`（main.py）/ `_wait_check`（account_panel.py）/ `jitter_sleep`（utils.py）实现，停止信号（`stop_event` / `_user_stop`）触发时立即返回，实现 GUI 停止按钮与快捷键的即时响应。

## 测试

- **pytest 单元测试**（`tests/`，纯逻辑、不依赖游戏环境）— `tests/test_utils.py`（抖动/编码/YAML 往返/Tesseract 定位）、`tests/test_ocr.py`（best_match_item / time_to_seconds）、`tests/test_daily_fetcher.py`（parse_recipes / match_site_to_config / load_config_departments）。运行：`conda run -n deltaforce python -m pytest tests`（pytest 见 `requirements-dev.txt`）
- `list_OCR_test(department, categories)` — 验证指定部门物品类别的 OCR 识别效果
- `test1()` — 枚举所有可见 Windows 窗口
- `test2()` — 验证配置加载和 user_config 更新
- `test_ocr_qty*.py` / `test_scan_full.py` — 补货 OCR 数量识别调试脚本（扫描数字区域、投影分析，需 `.img/` 下截图，未纳入版本控制）
- 在 `user_config.yaml` 中启用 `debug_mode: true` 可将截图保存到 `./log/`
- 设计文档位于 `docs/superpowers/specs/`（PyInstaller 打包方案、补货功能设计）与 `docs/superpowers/plans/`

## 版本历史

| 版本 | 提交 | 说明 |
|------|------|------|
| v3.2 | `890c7cd` | 原仓库最新版本 (S9 赛季) |
| v3.3 | `f6e1b03` | 多账号制造流程重构：启动即走、阶段分组GUI、F8快捷键、可配置等待时长 |
| v3.4 | `ee842b4` | 修复空闲检测误判：partial_ratio → ratio；auto_run_until_hour 可配置 |
| v3.5 | `fa5b808` | 修复计时器OCR误读导致部门状态误判；UTF-8编码兼容回退机制；GUI多账号面板新增自动执行时段控件；手动更新配方按钮 |
| v3.6 | `22c7aa0` | 新增每日自动补货功能：看门狗定时2点触发、独立补货循环、GUI配置阈值/补货量/手动补货按钮；钛合金和高级燃料使用独立quantity_region坐标 |
| v3.7 | `753a69e` (HEAD) | 补货完成后自动整理仓库（步骤18-21 ESC→仓库→整理→确认）；推荐配方自动更新勾选（auto_update_recipes，默认开启可取消） |
