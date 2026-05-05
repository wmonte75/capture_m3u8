# M3U8 Hunter GUI

A modern, high-performance graphical interface for the `capture_m3u8` engine. Built with `CustomTkinter`, it provides a visual workflow for searching IMDB, managing download queues, monitoring real-time progress, and configuring every aspect of the suite through an organized tabbed settings window.

## Features

- **Integrated IMDB Search**: Type a movie or show name directly into the URL box and press Enter to search.
- **Media Preview**: Displays posters and metadata (Rating/Year) before you start a download.
- **Smart Series Handling**: Detects TV series and offers to build full-season queue files (`.quu`) automatically.
- **Real-Time Logging**: Color-coded console output with native line-overwriting for `FFmpeg` and `N_m3u8DL-RE` progress updates.
- **Professional Status Bar**: Dedicated bottom bar with colored status label, progress bar, episode counter, and title display synced from log output.
- **Availability Checker**: Verify if a title is available on the embed servers before attempting a capture.
- **Dark/Light Mode**: Full theme support that persists across sessions.
- **Plugin Control**: On-the-fly "Reload Plugins" button to update your workflow without restarting the app.
- **Dependency Installer**: Startup dialog detects missing binaries and offers auto-install or package-manager instructions.

## Launching

### Windows
Run the provided launcher (recommended):
```powershell
run_capture_m3u8_gui.bat
```
Or run the Python script directly:
```powershell
python capture_m3u8_gui.py
```

### Linux / macOS
Use the provided launcher script:
```bash
chmod +x run_capture_m3u8_gui.sh
./run_capture_m3u8_gui.sh
```

## Usage

1.  **Analyze**: Paste a link or IMDB ID and click **Start / Analyze**.
2.  **Search**: Type a name (e.g., "The Matrix") and press **Enter**. Select your result from the popup dialog.
3.  **Queue**: Click **Load Queue** to import `.txt` or `.quu` files for batch processing.
4.  **Settings**: Update your library paths, speed limits, provider URLs, and binary locations via the tabbed Settings window. Changes save automatically.

## Settings Window (4 Tabs)

### General Tab
- **Movies Folder**: Destination path for finished movies.
- **TV Shows Folder**: Destination path for finished TV series.
- **Theme**: Toggle between Dark and Light mode.
- **Headless Mode**: Run the browser invisibly (default off for troubleshooting).
- **Subtitle Languages**: Preferred subtitle track languages.
- **Session Reset Count**: How often to auto-clear the browser cache.

### Download Tab
- **Download Speed**: Global fallback speed limit (e.g., `6M`, `Unlimited`).
- **Cooldown Range**: Random delay between queue items (`min` and `max` seconds).
- **Preferred Resolution**: Force a specific quality instead of auto-select:
  - `Auto` — Lets N_m3u8DL-RE pick the best available stream.
  - `1080p`, `720p`, `480p`, `360p` — Picks the exact variant from the master manifest.
- **PRO Adaptive Speed Control**: Toggle + 4 editable tier dropdowns that parse the master manifest and automatically cap download speed based on detected resolution:
  - **1080p and above**: Default `2.5M`
  - **720p**: Default `2M`
  - **480p**: Default `1.5M`
  - **360p and below**: Default `1M`

### Providers Tab
- **Movie Template**: Embed URL template for movies. Use `{imdb}` placeholder.
- **TV Template**: Embed URL template for TV series. Use `{imdb}`, `{s}` (season), and `{e}` (episode) placeholders.

### Tools Tab
- **Binary Browse Rows**: Entry fields + Browse buttons for each tool:
  - FFmpeg, FFprobe, N_m3u8DL-RE, MKVPropEdit, MKVMerge
  - Leave blank for auto-detection (searches Config -> `binaries/` -> root -> system PATH).
- **Reload Plugins**: Instantly rescans the `plugins/` folder.
- **Check & Update Tools**: Runs the `-U` updater to fetch latest binaries.
- **Clear Browser Session**: Deletes `browser_session/` to fix stale cookie/cache issues.

## Interface Details

- **Activity Log**: Displays detailed handoffs between the capture engine and the plugins.
- **Status Bar**: Bottom panel containing:
  - **Status Label**: Color-coded state (`Hunting...`, `Downloading`, `Success`, `Error`).
  - **Progress Bar**: Visual progress during downloads.
  - **Counter**: Shows current episode / total in a batch queue.
  - **Title Label**: Syncs from `"🎬 Title:"` log lines to show the active download name.
- **Stop Button**: Sends a safe termination signal to background processes and cleans up.

## Self-Cleaning Logic

- **Stale Sessions**: Automatically deletes the `browser_session` folder on startup if it is more than 30 minutes old.
- **Download Lock**: If you attempt multiple downloads, the GUI will report **"Waiting for [Title] to finish..."** and queue the task until the lock is released.

## Requirements

- Requires Python 3.8+
- Dependencies: `customtkinter`, `Pillow`, `requests`, `playwright`, `beautifulsoup4`.
- System: `tkinter` (on Linux, usually `python3-tk`).
