# CLAUDE.md

本文件为 Claude Code 在此仓库中工作时提供指导和上下文。

## 项目概述

Delta Force 三角洲行动 自动化制造脚本。通过截图 → OCR 文字识别 → 模拟鼠标键盘操作，自动完成游戏内制造流程。

## 运行环境

- **Python**: 3.11 (conda env: `deltaforce`)
- **OS**: Windows only (uses pywin32, keyboard, dxcam)
- **Tesseract-OCR**: bundled at `dist/Tesseract-OCR/`
- **Setup**: `conda run -n deltaforce pip install -r requirements.txt`

## 运行方式

### 默认启动：GUI 模式

```bash
set PYTHONIOENCODING=utf-8
D:/Anaconda3/envs/deltaforce/python.exe gui/app.py
```

GUI 基于 tkinter，提供启动/停止控制、实时部门状态、运行日志、今日推荐配方显示。**默认启动方式，直接运行即可。**

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

单文件应用 (`main.py`)，核心流程如下：

1. **主循环** (`main()`) — 无限循环：蜂鸣 → 恢复游戏窗口 → 检查分辨率 → 更新配置 → `dash_page()` → sleep(剩余时间) → 重复
2. **仪表盘** (`dash_page()`) — OCR 识别各部门状态（空闲/进行中/已完成）→ 收集已完成项 → 对有挂起项目的空闲部门触发 `list_page()`
3. **列表导航** (`list_page_operation()`) — 滚动可制造物品列表，OCR 识别物品名称，与配置模糊匹配，点击制造
4. **自动购买材料** (`initalize_preparation()`) — 检测缺少的材料，打开交易行，OCR 价格，在可承受范围内购买

### 配置文件

- `config.yaml` — 物品数据库 (`departments`)、屏幕坐标 (`departments_coords`)、各部门 OCR 配置、匹配阈值 (`OCR_factors`)
- `user_config.yaml` — 用户制造队列 (`tech/work/medical/armor`)、Tesseract 路径、调试/后台模式开关

### 截屏与识别

使用 PIL `ImageGrab.grab()` 截取屏幕，经 OpenCV 处理（灰度化、Otsu 二值化），Tesseract OCR 识别文字，`rapidfuzz` 进行字符串匹配。

### 坐标系统

`departments_coords` 中的所有坐标基于 1920x1080 基准定义，运行时通过 `scale_factor = width / 1920` 缩放。仅支持 16:9 分辨率（1080p、1440p、4K）。

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
