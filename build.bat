@echo off
rem Delta Force Auto-Craft - packaging script (ASCII only for codepage safety)
setlocal

set PYTHON=D:\Anaconda3\envs\deltaforce\python.exe
if exist "%PYTHON%" goto :env_ok
echo [ERROR] deltaforce env not found: %PYTHON%
pause
exit /b 1

:env_ok
rem clean old output (keep dist/Tesseract-OCR source)
if exist build rmdir /s /q build
if exist dist\DeltaForceSS rmdir /s /q dist\DeltaForceSS

echo === Packaging with PyInstaller ===
"%PYTHON%" -m PyInstaller build.spec
if %errorlevel% neq 0 goto :fail

rem PyInstaller 5+ puts datas into _internal/, move them next to the EXE
set OUTDIR=dist\DeltaForceSS
if exist %OUTDIR%\_internal\Tesseract-OCR move /y %OUTDIR%\_internal\Tesseract-OCR %OUTDIR%\Tesseract-OCR >nul
if exist %OUTDIR%\_internal\data move /y %OUTDIR%\_internal\data %OUTDIR%\data >nul
if exist %OUTDIR%\_internal\config.yaml move /y %OUTDIR%\_internal\config.yaml %OUTDIR%\config.yaml >nul
if exist %OUTDIR%\_internal\user_config.yaml move /y %OUTDIR%\_internal\user_config.yaml %OUTDIR%\user_config.yaml >nul

echo.
echo === Packaging done ===
echo Output: %cd%\%OUTDIR%\
dir /b %OUTDIR%\
echo.
pause
exit /b 0

:fail
echo [ERROR] PyInstaller failed
pause
exit /b 1
