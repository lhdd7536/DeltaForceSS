# GUI 可视化界面实施文档

## 实施步骤总览

1. 修改 `main.py` — 增加 `stop_event` 和 `status_callback` 支持
2. 创建 `gui/__init__.py` — 包初始化
3. 创建 `gui/app.py` — GUI 入口
4. 创建 `gui/main_window.py` — 主窗口
5. 测试验证

---

## 步骤 1：修改 main.py

### 1.1 变更函数签名

```python
def main(stop_event=None, status_callback=None):
```

### 1.2 可中断休眠

将 `main()` 中的 `time.sleep(remain_time)` 替换为：

```python
# 可中断的休眠
if stop_event is not None:
    if stop_event.wait(timeout=remain_time):
        print("用户手动停止")
        return  # stop_event 被设置，退出循环
else:
    time.sleep(remain_time)
```

### 1.3 状态回调

在 `dash_page()` 调用之后，添加状态回调：

```python
# 在 main() 中，获取 remain_times 后
if status_callback:
    status_callback(remain_times, wait_list)
```

### 1.4 异常处理

将 `input()` 阻塞调用改为非阻塞通知：

```python
except IncorrectPageError as e:
    low_beep()
    print(f'界面异常: {e}')
    if stop_event is not None:
        print('请回到特勤处制造界面后等待自动重试...')
        stop_event.wait(timeout=30)  # 等待 30 秒后自动重试
    else:
        input('回到特勤处制造界面后, 按 *回车* 键重试...')
```

### 1.5 批量修改对照

| 行号范围（原） | 修改内容 |
|---------------|---------|
| 函数定义行 | `def main():` → `def main(stop_event=None, status_callback=None):` |
| `while True:` | 改为 `while stop_event is None or not stop_event.is_set():` |
| `time.sleep(remain_time)` 处 | 改为可中断休眠 |
| `dash_page()` 调用后 | 新增状态回调 |
| `input()` 阻塞 | 改为 `stop_event.wait(timeout)` 模式 |
| 全局异常处理 | 异常时通知 GUI 而不是直接退出 |

---

## 步骤 2：创建 gui/__init__.py

空文件，仅用于包初始化。

```python
# gui/__init__.py
```

---

## 步骤 3：创建 gui/main_window.py

### 3.1 类设计

```python
class MainWindow(tk.Tk):
```

### 3.2 布局框架

采用 `ttk.Frame` 进行区域划分：

```
root (tk.Tk)
├── control_frame (ttk.LabelFrame)    # 控制面板
├── recipe_frame (ttk.LabelFrame)     # 推荐配方
├── status_frame (ttk.LabelFrame)     # 部门状态
├── log_frame (ttk.LabelFrame)        # 运行日志
└── status_bar (ttk.Label)           # 状态栏
```

### 3.3 核心功能

| 功能 | 方法 | 说明 |
|------|------|------|
| 启动 | `start_automation()` | 创建工作线程，传入 stop_event，启动 main() |
| 停止 | `stop_automation()` | 设置 stop_event，等待线程结束 |
| 更新配方 | `update_recipe_display()` | 读取 user_config.yaml 显示推荐内容 |
| 更新状态 | `update_status(status_data)` | 通过 status_queue 接收并更新部门状态 |
| 追加日志 | `append_log(message)` | 向日志文本框追加带时间戳的行 |
| 更新进度条 | `update_progress()` | 每个部门的计时器进度 |

### 3.4 线程管理

```python
def __init__(self):
    self.stop_event = threading.Event()
    self.worker_thread = None
    self.status_queue = queue.Queue()

def start_automation(self):
    self.stop_event.clear()
    self.worker_thread = threading.Thread(
        target=self._run_automation,
        daemon=True
    )
    self.worker_thread.start()
    self._poll_status_queue()  # 启动轮询

def _run_automation(self):
    """在工作线程中运行的自动化函数"""
    import main
    main.main(
        stop_event=self.stop_event,
        status_callback=lambda s: self.status_queue.put(s)
    )

def _poll_status_queue(self):
    """每 100ms 检查一次状态队列"""
    try:
        while True:
            status = self.status_queue.get_nowait()
            self.update_status(status)
    except queue.Empty:
        pass
    self.after(100, self._poll_status_queue)
```

### 3.5 print 重定向

在 GUI 启动时重定向 stdout，使 `main()` 中的 `print()` 输出同时显示到控制台和日志面板：

```python
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
    
    def write(self, text):
        if text.strip():
            self.text_widget.insert(tk.END, text)
            self.text_widget.see(tk.END)
    
    def flush(self):
        pass
```

---

## 步骤 4：创建 gui/app.py

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Delta Force 自动制造 - GUI 启动入口

用法:
    python gui/app.py
"""

import sys
import os

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gui.main_window import MainWindow

def main():
    import tkinter as tk
    root = MainWindow()
    root.mainloop()

if __name__ == "__main__":
    main()
```

---

## 步骤 5：测试验证

### 5.1 测试用例

| 测试 | 步骤 | 预期结果 |
|------|------|---------|
| GUI 启动 | `python gui/app.py` | 窗口正常显示，状态灯为红色"已停止" |
| 加载推荐 | 启动时自动加载 | 四个部门显示推荐物品名和更新时间 |
| 启动循环 | 点击 [▶ 启动] | 状态灯变绿，日志开始输出，部门状态更新 |
| 停止循环 | 点击 [■ 停止] | 状态灯变红，日志显示"已停止" |
| 后台模式切换 | 勾选/取消复选框 | `user_config.yaml` 对应字段更新 |
| 日志显示 | 启动后观察 | 日志自动滚动，时间戳正确 |
| 异常处理 | 游戏窗口未找到 | 日志显示错误，状态灯保持红色 |
| CLI 兼容 | `python main.py` | 与原行为完全一致 |

### 5.2 回退方案

如 GUI 出现问题，可随时通过 `python main.py` 使用原 CLI 模式，`main.py` 的修改保证向下兼容。
