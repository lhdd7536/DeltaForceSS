# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller 构建配置：Delta Force 自动制造
用法：conda run -n deltaforce pyinstaller build.spec
"""

import os
import sys

PROJECT_ROOT = os.getcwd()  # 构建时 CWD 为项目根目录
CONDA_ENV = r'D:\Anaconda3\envs\deltaforce'

# 将 conda env 的 Library/bin 加入 PATH，确保 PyInstaller 找到正确版本的 Tcl/Tk DLL
os.environ['PATH'] = os.path.join(CONDA_ENV, 'Library', 'bin') + os.pathsep + os.environ['PATH']

# Tcl/Tk 脚本库路径（覆盖 PyInstaller tkinter hook 的旧版本 _tcl_data）
TCL_LIB = os.path.join(CONDA_ENV, 'Library', 'lib', 'tcl8.6')
TK_LIB = os.path.join(CONDA_ENV, 'Library', 'lib', 'tk8.6')

a = Analysis(
    ['gui/app.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'config.yaml'), '.'),
        (os.path.join(PROJECT_ROOT, 'user_config.yaml'), '.'),
        (os.path.join(PROJECT_ROOT, 'data'), 'data'),
        (os.path.join(PROJECT_ROOT, 'dist', 'Tesseract-OCR'), 'Tesseract-OCR'),
        (TCL_LIB, '_tcl_data'),
        (TK_LIB, '_tk_data'),
    ],
    hiddenimports=[
        'win32com',
        'win32api',
        'win32gui',
        'win32process',
        'win32con',
        'keyboard',
    ],
    hookspath=[],
    runtime_hooks=[os.path.join(PROJECT_ROOT, 'runtime_hook.py')],
    excludes=[
        'tkinter.test',
        'PIL.ImageShow',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DeltaForceSS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='DeltaForceSS',
)
# 注意：构建后数据文件从 _internal/ 移动到 exe 同级的操作在 build.bat 中完成
