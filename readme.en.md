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
- Account list management (enable/disable, estimated completion time tracking)
- Configurable WeGame click coordinates (grouped by phase) and per-step wait times
- Three game exit methods: alt_f4 / wm_close / taskkill
- Auto-handling of GameInputSvc foreground interference, WeGame path auto-detection
- Failure auto-retry (up to 3 rounds) and timeout protection
- Scheduled loop: auto-arranges the next round based on estimated completion times; runs without popups before `auto_run_until_hour`
- Accounts beyond the visible list (4th/5th) log in via a "scroll before click" setting

### Daily Recommended Recipe Fetcher
Automatically fetches the daily recommended manufacturing recipes from orzice.com/v/rb:
- Renders the page with Playwright + parses with BeautifulSoup, fuzzy-matched against the `config.yaml` item database
- Writes to the `user_config.yaml` manufacturing queue (Tech Center always keeps its configured default)
- Toggleable auto-update in the GUI (default on), plus a "Manual Update" button

### Daily Auto-Replenishment
At a scheduled time (default 2:00 AM), logs into each account and navigates to Quartermaster → Collectibles to check titanium alloy and advanced fuel stock, auto-buying when below the threshold:
- **Scheduling watchdog** — triggers at 2:00 AM daily (waits for the current manufacturing cycle to finish if running)
- **Manual replenish button** — one-click trigger from the GUI
- **Independent coordinates** — titanium alloy and advanced fuel use separate `quantity_region` settings
- **Auto warehouse sorting** — ESC → Warehouse → Sort → Confirm after purchasing

### GUI Interface
Tkinter-based graphical interface with:
- **Single-Account tab**: start/stop controls, status indicator, background/debug mode toggles, today's recommended recipes (update time + auto/manual update), run logs
- **Multi-Account tab**: account list management, schedule controls, replenishment config (threshold/quantity/manual button), WeGame coordinates grouped by phase (with "capture mouse position" support)
- F8 global hotkey (configurable via `hotkey` in `user_config.yaml`), with instant stop response

### EXE Packaging
One-click packaging via `build.bat` + `build.spec` (including Tcl/Tk path fix). All resource files are placed alongside the EXE after packaging, convenient for non-Python users.

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
  - [骨架狙击枪托, -1]          # [Item name, quantity], -1 = unlimited
work:                            # Workshop
  - [5.45x39mm BS, -1]
medical:                         # Medical Center
  - [精密头盔维修包, -1]
armor:                           # Armor Center
  - [精英防弹背心, -1]
```

Advanced settings (keep defaults recommended):
- `auto_run_until_hour` — auto-run cutoff hour (default `11`, i.e. 0:00~11:00 runs without popups); set `23` for all-day auto, `0` to always ask
- `TESSERACT_PATH` — OCR path (usually no change needed; falls back to `dist/Tesseract-OCR` automatically)
- `background_mode` — Default `false`; minimizes game after each cycle
- `debug_mode` — Default `false`; saves screenshots to `./log/`
- `hotkey` — global hotkey (default `f8`)
- `auto_update_recipes` — daily recipe auto-update (default `true`)
- `auto_replenish` — replenishment config (`enabled` switch, `threshold`, `quantity`)

### 3. Run

**Single-account mode:**
1. Open the game and navigate to the manufacturing screen
2. Prepare non-purchasable items in advance (e.g., titanium alloy)
3. **Run `DeltaForceSS.exe` as Administrator**
4. The program will auto-switch to the game and start the cycle

**Multi-account mode (requires `data/accounts.yaml`):**
1. Configure the wegame.exe path
2. Switch to the "Multi-Account" tab in the GUI
3. **Configure WeGame coordinates** — click coordinates, per-step wait times, and exit method for each account must be adjusted based on your screen resolution and WeGame layout. See comments in `data/accounts.yaml` for details.
4. Click "▶ Start All" to begin the rotation
5. Currently stable with 5 configured accounts (4th/5th use the scroll-before-click login)

### 4. Notes
- Pin target items in-game for better recognition
- Only supports 16:9 resolution (1080p / 1440p / 4K)
- The program reports an abnormal screen and retries every 30 seconds if not on the manufacturing page
- `.300 BLK` must be pinned manually (three ammo types share the same name)
- Auto-retries after ~30 seconds on item matching failure
- **Auto-crafting period: 0:00 ~ auto_run_until_hour** (default 11) — outside this window, a popup requires manual confirmation. Adjustable in `user_config.yaml`

## Project Info

### Completed Features
- Full item auto-manufacturing and collection
- Auto material purchasing (exchange items not supported)
- Full automation for Tech Center, Workshop, Medical Center, Armor Center
- 16:9 1K / 2K / 4K screen support (PIL ImageGrab capture)
- Multi-account batch manufacturing (WeGame switching)
- GUI interface (real-time logs and status feedback)
- PyInstaller EXE packaging
- Auto-focus and minimize
- Daily recommended recipe fetching (manual update supported)
- Daily auto-replenishment (titanium alloy/advanced fuel, configurable threshold)
- Auto warehouse sorting after replenishment

### Known Issues
- `.300 BLK` has three identical ammo names, needs manual pinning
- Long background time may require network reconnection
