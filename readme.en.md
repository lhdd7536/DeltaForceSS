[中文 README](readme.md)

> This project is an enhanced fork of [yi-zelin/DeltaForceSS](https://github.com/yi-zelin/DeltaForceSS) (GPL v3).
> Original author: yi-zelin. Thanks for the excellent work.

## Disclaimer
This project is developed solely for **technical learning and communication** purposes. It is **not a game plugin or cheating tool**. Any commercial use or violations of the game's terms of service are strictly prohibited.

## Overview
Please star the project, thank you!

An automated manufacturing program for Delta Force operations using screenshot capture, OCR text recognition, and simulated mouse/keyboard input. It does **not** read or modify any game data, so there is no risk of being banned.

Supports **single-account** and **multi-account batch** manufacturing modes. In single mode, the program cycles through departments to collect completed items and start new ones. In multi mode, it switches between WeGame accounts and runs manufacturing for each account sequentially.

Workflow: Screenshot → OCR text recognition → Simulate mouse/keyboard input

## Enhancements

This fork adds the following features on top of the original single-account manufacturing:

### Multi-Account Batch Manufacturing
Automates manufacturing across multiple accounts via WeGame account switching:
- Account list management (enable/disable, completion time tracking)
- Configurable WeGame click coordinates and per-step wait times
- Three game exit methods: alt_f4 / wm_close / taskkill
- Auto-handling of GameInputSvc foreground interference
- Failure retry and timeout protection

### GUI Interface
Tkinter-based graphical interface with:
- **Manufacturing tab**: start/stop/pause controls, real-time department status cards, run logs, today's recommended recipes
- **Multi-account tab**: account list management, WeGame coordinate configuration, scheduling controls
- F8 global hotkey

### EXE Packaging
PyInstaller build config (`build.spec`) included. All resource files are placed alongside the EXE after packaging, convenient for non-Python users.

## User Guide

### 1. Download
Go to [Releases](https://github.com/lhdd7536/DeltaForceSS/releases) and download the latest zip file.
**Extract to a path with ONLY English characters (Tesseract OCR only supports ASCII paths).**

Contents after extraction:
- **`DeltaForceSS.exe`** — Main program, run as Administrator
- **`config.yaml`** — Item database
- **`user_config.yaml`** — User configuration (manufacturing queue)
- **`data/`** — Multi-account configuration
- **`Tesseract-OCR/`** — OCR program

### 2. Configure Manufacturing Queue (`user_config.yaml`)
```yaml
tech:                            # Tech Center
  - 高级攻势护甲片              # Item name, must match config.yaml
work:                            # Workshop
  - 5.45x39mm BS
medical:                         # Medical Center
  - 高级手术包
armor:                           # Armor Center
  - 突击装甲板
```

Advanced settings (keep defaults recommended):
- `TESSERACT_PATH` — OCR path (usually no change needed)
- `background_mode` — Default `false`; minimizes game after each cycle
- `debug_mode` — Default `false`; saves screenshots to `./log/`

### 3. Run

**Single-account mode:**
1. Open the game and navigate to the manufacturing screen
2. Prepare non-purchasable items in advance (e.g., titanium alloy)
3. **Run `DeltaForceSS.exe` as Administrator**
4. The program will auto-switch to the game and start the cycle

**Multi-account mode (requires `data/accounts.yaml`):**
1. Open WeGame and log in with your main account
2. Switch to the "Multi-Account" tab in the GUI
3. **Configure WeGame coordinates** — click coordinates, per-step wait times, and exit method for each account must be adjusted based on your screen resolution and WeGame layout. See comments in `data/accounts.yaml` for details.
4. Click "Start Multi-Account" to begin the rotation

### 4. Notes
- Pin target items in-game for better recognition
- 16:9 resolution only (1080p / 1440p / 4K)
- Program auto-stops if not on the manufacturing screen
- `.300 BLK` must be pinned manually (three ammo types share the same name)
- Auto-restarts after 1 minute on OCR failure

## Project Info

### Completed Features
- Full item auto-manufacturing and collection
- Auto material purchasing (exchange items not supported)
- Full automation for Tech Center, Workshop, Medical Center, Armor Center
- dxcam screenshot capture (direct GPU memory access)
- 16:9 1K / 2K / 4K screen support
- Multi-account batch manufacturing (WeGame switching)
- GUI interface (real-time status monitoring)
- PyInstaller EXE packaging
- Auto-focus and minimize

### Known Issues
- `.300 BLK` has three identical ammo names, needs manual pinning
- Long background time may require network reconnection
