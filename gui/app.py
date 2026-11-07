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
    # 隐藏控制台（EXE）时 stdout 为 None，先重定向到 log/app.log 避免 print 抛错。
    # 注意：MainWindow 构造后会把 stdout/stderr 换成内存队列（GUI 日志面板），
    # 此后输出不再写入 app.log。
    if not sys.stdout:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log')
        log_dir = os.path.normpath(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        sys.stdout = open(os.path.join(log_dir, 'app.log'), 'w', encoding='utf-8')
        sys.stderr = sys.stdout

    import tkinter as tk
    root = MainWindow()
    root.mainloop()


if __name__ == '__main__':
    main()
