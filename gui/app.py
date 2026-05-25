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


if __name__ == '__main__':
    main()
