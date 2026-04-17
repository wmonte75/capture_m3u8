# M3U8 Hunter GUI

A modern, high-performance graphical interface for the `capture_m3u8` engine. Built with `CustomTkinter`, it provides a visual workflow for searching IMDB, managing download queues, and monitoring real-time progress.

## ✨ Features

- **Integrated IMDB Search**: Type a movie or show name directly into the URL box and press Enter to search.
- **Media Preview**: Displays posters and metadata (Rating/Year) before you start a download.
- **Smart Series Handling**: Detects TV series and offers to build full-season queue files (`.quu`) automatically.
- **Real-Time Logging**: Color-coded console output with native line-overwriting for `FFmpeg` and `N_m3u8DL-RE` progress updates.
- **Availability Checker**: Verify if a title is available on the embed servers before attempting a capture.
- **Dark/Light Mode**: Full theme support that persists across sessions.
- **Plugin Control**: On-the-fly "Reload Plugins" button to update your workflow without restarting the app.

## 🚀 Launching

### Windows
Run the Python script directly:
```powershell
python capture_m3u8_gui.py
```

### Linux (BigLinux/Arch/Ubuntu)
Use the provided launcher script to handle the virtual environment and dependencies:
```bash
chmod +x run_capture_m3u8_gui.sh
./run_capture_m3u8_gui.sh
```

## 🛠️ Usage

1.  **Analyze**: Paste a link or IMDB ID and click **Start / Analyze**.
2.  **Search**: Type a name (e.g., "The Matrix") and press **Enter**. Select your result from the popup dialog.
3.  **Queue**: Click **Load Queue** to import `.txt` or `.quu` files for batch processing.
4.  **Settings**: Update your library paths and speed limits directly in the UI; they save automatically.

## 📋 Interface Details

- **Activity Log**: Displays detailed handoffs between the capture engine and the plugins.
- **Progress Status**: The "Start" button dynamically changes to show current download percentages.
- **Stop Button**: Sends a safe termination signal to background processes and clean up the `browser_session`.

## 🛡️ Self-Cleaning Logic

- **Stale Sessions**: Automatically deletes the `browser_session` folder on startup if it is more than 30 minutes old.
- **Download Lock**: If you attempt multiple downloads, the GUI will report **"Waiting for [Title] to finish..."** and queue the task until the lock is released.

## 🔧 Requirements

- Requires Python 3.8+
- Dependencies: `customtkinter`, `Pillow`, `requests`, `playwright`, `beautifulsoup4`.
- System: `tkinter` (on Linux, usually `python3-tk`).