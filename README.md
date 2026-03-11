# M3U8 Hunter & Downloader (GUI + CLI)

A premium, all-in-one media automation tool for discovering and downloading M3U8 video streams. Featuring a sophisticated GUI, IMDB integration, and smart queue management.

## 🚀 Key Features

- **Unified Media Dialog**: One gorgeous popup for both Movies and TV.
  - **Movies**: Choose to "Download Now" or **"Add to Queue"** (appends to your existing lists).
  - **TV Series**: Automated **"Full Series Queue"** creation or manual **"Download Now"** selection.
- **Smart IMDB Integration**: Type a name to search, pick a result, and see the full metadata and poster before you download.
- **Cross-Platform Perfected**: 
  - **Windows**: Uses Chromium for optimal performance.
  - **Linux**: Automatically uses Firefox to bypass Cloudflare/anti-bot walls.
- **Modernized GUI Log**: 
  - **Color-Coded**: Green ✅ (Success), Red ❌ (Error), Orange ⚠️ (Warning), Blue 🕵️ (Info).
  - **Native Emoji Support**: Optimized font rendering for all icons on Windows.
  - **Clear Management**: One-click "Clear" button to reset your activity view.
- **Queue Appending**: Easily build massive movie collections by appending new titles to existing `.quu` files.
- **Robust Downloader**: 
  - **Fragment Retries**: Automatically retries missing stream fragments up to 10 times.
  - **Auto-Detection**: Sniffs network traffic to find `master.m3u8` streams early.
  - **Smart Resume**: Self-healing `completed.log` that checks the filesystem to avoid re-downloads.
- **Default Paths**: Automatically creates `TV/` and `Movie/` subfolders in the script directory if no paths are configured.

---

## 🛠️ Prerequisites

- **Python 3.8 - 3.12**
- **FFmpeg**: Required for merging video fragments. Ensure it's in your system PATH.
- **yt-dlp**: Looks for `yt-dlp.exe` (Windows) or `yt-dlp` (Linux) in the script directory or PATH.

---

## 📦 Installation & Setup

### 1. Requirements
Install the necessary Python libraries:
```bash
pip install -r requirements.txt
```

### 2. Browser Setup (Critical)
The tool will attempt to install the correct browsers automatically, but you can do it manually to be safe:

**Windows:**
```bash
playwright install chromium
```

**Linux:**
```bash
playwright install firefox
```

---

## 🎮 Usage Guide

### 🖥️ GUI Version (Recommended)
Run the visual application for the best experience:
```bash
python capture_m3u8_gui.py
```
*   **Search**: Type a show/movie name in the URL box and press **Enter**.
*   **Pick & Choose**: Click a result to see the **Unified Media Dialog**.
*   **Manage Queues**: Use **"Load Queue"** to run a saved `.quu` or `.txt` file.

### ⌨️ CLI Version
For power users or remote servers:
```bash
python capture_m3u8.py "IMDB_URL_OR_QUERY"
```
*   **Batch Mode**: `python capture_m3u8.py my_queue.txt`

---

## ⚙️ Configuration (`config.json`)

The app saves your settings automatically, but you can edit `config.json` manually:
```json
{
  "movies_dir": "C:/Media/Movies",
  "tv_dir": "C:/Media/TV",
  "download_speed": "6M",
  "min_cooldown": 10,
  "max_cooldown": 25,
  "theme": "dark"
}
```

---

## ❓ Troubleshooting

### Linux "Executable Not Found"
If Playwright fails on Linux, ensure you've run `playwright install firefox`. The script is specifically tuned to use Firefox on Linux to bypass security filters that block Chromium.

### Cloudflare Loops
If you get stuck on a "Verifying you are human" screen:
1. Uncheck **"Headless Mode"** in the GUI.
2. Click **Start**.
3. Manually solve the checkbox/captcha in the window that appears.
4. The script will save your session cookies for next time.

### Broken Numbers/Emojis
If the logs look weird, ensure you have the **Segoe UI** font installed (Standard on Windows). The GUI is optimized for this font to keep numbers compact while showing colorful icons.