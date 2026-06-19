"""PyInstaller 运行时钩子：修复 Tcl/Tk 库路径"""
import os
import sys

# 确定临时解压目录
base = sys._MEIPASS

# Tcl/Tk 库脚本目录（来自 conda 环境）
tcl_dir = os.path.join(base, '_tcl_data')
tk_dir = os.path.join(base, '_tk_data')

if os.path.isdir(tcl_dir):
    os.environ['TCL_LIBRARY'] = tcl_dir
if os.path.isdir(tk_dir):
    os.environ['TK_LIBRARY'] = tk_dir

# 如果有 tcl8.6 目录结构，尝试作为备选
alt_tcl = os.path.join(base, 'tcl8.6')
alt_tk = os.path.join(base, 'tk8.6')
if os.path.isdir(alt_tcl) and 'TCL_LIBRARY' not in os.environ:
    os.environ['TCL_LIBRARY'] = alt_tcl
if os.path.isdir(alt_tk) and 'TK_LIBRARY' not in os.environ:
    os.environ['TK_LIBRARY'] = alt_tk
