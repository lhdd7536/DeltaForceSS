@echo off
chcp 65001 >nul

echo === Delta Force 自动制造 - 打包脚本 ===
echo.

:: 激活 conda 环境
call D:\Anaconda3\envs\deltaforce\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [错误] 无法激活 conda 环境 deltaforce
    pause
    exit /b 1
)

:: 清理旧输出目录（保留 dist/Tesseract-OCR 源文件）
if exist build (
    echo 清理 build 目录...
    rmdir /s /q build
)
if exist dist\DeltaForceSS (
    echo 清理旧的打包输出...
    rmdir /s /q dist\DeltaForceSS
)

:: 执行 PyInstaller
echo 开始打包...
pyinstaller build.spec
if %errorlevel% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

:: PyInstaller 5+ 将 datas 放入 _internal/，需复制到 exe 同级
echo 整理输出文件...
set OUTDIR=dist\DeltaForceSS

:: Tesseract-OCR
if exist %OUTDIR%\_internal\Tesseract-OCR (
    move /y %OUTDIR%\_internal\Tesseract-OCR %OUTDIR%\Tesseract-OCR >nul
)

:: data/
if exist %OUTDIR%\_internal\data (
    move /y %OUTDIR%\_internal\data %OUTDIR%\data >nul
)

:: 配置文件
if exist %OUTDIR%\_internal\config.yaml (
    move /y %OUTDIR%\_internal\config.yaml %OUTDIR%\config.yaml >nul
)
if exist %OUTDIR%\_internal\user_config.yaml (
    move /y %OUTDIR%\_internal\user_config.yaml %OUTDIR%\user_config.yaml >nul
)

echo.
echo === 打包完成 ===
echo 输出路径: %cd%\%OUTDIR%\
echo.
echo 文件列表:
dir /b %OUTDIR%\
echo.
pause
