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
    # 隐藏控制台时重定向 print 到日志文件
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
