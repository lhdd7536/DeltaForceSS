# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Delta Force 三角洲行动 自动化制造脚本。通过截图 → OCR 文字识别 → 模拟鼠标键盘操作，自动完成游戏内制造流程。

## Environment

- **Python**: 3.11 (conda env: `deltaforce`)
- **OS**: Windows only (uses pywin32, keyboard, dxcam)
- **Tesseract-OCR**: bundled at `dist/Tesseract-OCR/`
- **Setup**: `conda activate deltaforce && pip install -r requirements.txt`

## Running

```bash
set PYTHONIOENCODING=utf-8
python main.py
```

## Architecture

Single-file application (`main.py`) with this pipeline:

1. **Main loop** (`main()`) — infinite loop: beep → restore game window → check resolution → update config → `dash_page()` → sleep(remain_time) → repeat
2. **Dashboard** (`dash_page()`) — OCR each dept status (free/in_progress/done) → collect completed → trigger `list_page()` for free depts with pending items
3. **List navigation** (`list_page_operation()`) — scroll through craftable items list, OCR item names, fuzzy-match against config, click to craft
4. **Auto-buy materials** (`initalize_preparation()`) — detect missing materials, open trade, OCR price, buy if affordable

### Config files

- `config.yaml` — item database (`departments`), screen coordinates (`departments_coords`), OCR configs per dept, match thresholds (`OCR_factors`)
- `user_config.yaml` — user's craft queue (`tech/work/medical/armor`), Tesseract path, debug/background mode toggles

### Screen capture

Uses PIL `ImageGrab.grab()` for screenshots. Processed via OpenCV (grayscale, Otsu thresholding). Tesseract OCR for text recognition, `rapidfuzz` for string matching.

### Coordinate system

All coordinates in `departments_coords` are defined for 1920x1080 baseline, scaled at runtime via `scale_factor = width / 1920`. Only 16:9 resolutions supported (1080p, 1440p, 4K).

## Testing

- `list_OCR_test(department, categories)` — validates OCR recognition for a dept's item categories
- `test1()` — enumerates all visible Windows
- `test2()` — validates config loading and user_config updates
- Enable `debug_mode: true` in user_config.yaml to save screenshots to `./log/`
