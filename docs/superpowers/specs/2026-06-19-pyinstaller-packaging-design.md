# PyInstaller 打包方案

将 Delta Force 自动制造程序打包为独立的 Windows 可执行文件，无需 Python 环境和 IDE 即可运行。

## 输出格式

- **类型**: 文件夹模式（`--onedir`），非单文件
- **控制台**: 隐藏（`--noconsole`），不显示黑色控制台窗口
- **输出路径**: `dist/DeltaForceSS/`

## 输出目录结构

```
dist\DeltaForceSS\
├── DeltaForceSS.exe           # 主程序
├── _internal\                 # Python 运行时 + 依赖库（PyInstaller 自动管理）
│   ├── python311.dll
│   └── ...
├── config.yaml                # 物品/坐标配置（外部可编辑）
├── user_config.yaml           # 用户制造队列配置（外部可编辑）
├── data\
│   └── accounts.yaml          # 多账号配置
└── Tesseract-OCR\             # OCR 引擎
    ├── tesseract.exe
    └── tessdata\chi_sim.traineddata
```

配置文件和数据文件放在 exe 外部，用户可直接修改。更新程序时只需替换 `DeltaForceSS.exe`。

## 构建工具

PyInstaller，通过 `.spec` 文件管理构建配置。

### 关键 PyInstaller 参数

| 参数 | 说明 |
|------|------|
| `--onedir` | 文件夹模式输出 |
| `--noconsole` | 隐藏控制台窗口 |
| `--name DeltaForceSS` | 输出 exe 名称 |
| `--add-data "config.yaml;."` | 打包配置文件到 exe 同级 |
| `--add-data "user_config.yaml;."` | 同上 |
| `--add-data "data;data"` | 打包 data 目录 |
| `--add-data "dist/Tesseract-OCR;Tesseract-OCR"` | 打包 Tesseract OCR |
| `--hidden-import win32com` | 确保 pywin32 完整 |
| 入口: `gui/app.py` | 主程序入口 |

## 代码调整

隐藏控制台后 `sys.stdout` 为 `None`，`print()` 会引发 `ValueError`。在 `gui/app.py` 入口处添加重定向：

```python
if not sys.stdout:
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
    os.makedirs(log_dir, exist_ok=True)
    sys.stdout = open(os.path.join(log_dir, 'app.log'), 'w', encoding='utf-8')
    sys.stderr = sys.stdout
```

所有 `print` 输出写入 `log/app.log`，不干扰 GUI。

## 构建脚本

项目根目录新建 `build.bat`：

```batch
@echo off
chcp 65001 >nul
call conda run -n deltaforce pyinstaller build.spec
echo 打包完成，输出在 dist/DeltaForceSS/
pause
```

以及 `build.spec` 文件以精确控制打包行为。

## 使用方式

1. 双击 `DeltaForceSS.exe`
2. 程序启动 GUI 界面，行为与 `python gui/app.py` 完全一致
3. 如需修改配置，编辑同目录下的 YAML 文件
4. 日志输出到 `log/app.log`

## 注意事项

- **keyboard 库**: 需要管理员权限才能注册全局热键（F8）。如果 F8 不生效，以管理员身份运行 exe
- **Tesseract 路径**: `user_config.yaml` 中 `TESSERACT_PATH` 需设为 `Tesseract-OCR\tesseract.exe`（相对于 exe 的相对路径）
- **杀软误报**: PyInstaller 打包的程序可能被部分杀软误报，添加信任即可
- **分发**: 整个 `dist/DeltaForceSS/` 文件夹可压缩为 zip 分发，接收方解压即用
