# M3U8 Hunter & Downloader (GUI + CLI)

A premium, all-in-one media automation tool for discovering and downloading M3U8 video streams. Featuring a sophisticated GUI, IMDB integration, and smart queue management.

## 🚀 Key Features

- **Unified Media Dialog**: One gorgeous popup for both Movies and TV.
  - **Movies**: Choose to "Download Now" or **"Add to Queue"**.
  - **TV Series**: Automated **"Full Series Queue"** creation or manual **"Download Now"** selection.
  - **Enhanced Meta**: See total seasons and total episodes at a glance.
- **CPU & Resource Optimization**: 
  - **Browser Re-use**: TV series analysis uses a single browser instance for all seasons, preventing CPU spikes.
  - **Resource Blocking**: Aggressively blocks images, fonts, and trackers during scraping to save bandwidth.
- **Advanced Stealth & Bypass**:
  - **Anti-Bot Countermeasures**: Mocks hardware properties and browser signatures to bypass protections.
  - **Integrated Blocking**: Automatically blocks libraries like `disable-devtool` via `unpkg.com` interception.
- **Automated Queue Management**: 
  - **Silent Saving**: Automatically generates and saves `.quu` queue files silently.
  - **Infinite Scroll Support**: Full support for IMDB Top 250 lists with real-time feedback.
- **Robust Downloader**: 
  - **Fragment Retries**: Automatically retries missing stream fragments up to 10 times.
  - **Auto-Detection**: Sniffs network traffic to find `master.m3u8` streams early.
  - **Smart Resume**: Self-healing `completed.log` that checks the filesystem to avoid re-downloads.
- **Cross-Platform Perfected**: 
  - **Windows**: Uses Chromium for optimal performance.
  - **Linux**: Automatically uses Firefox to bypass Cloudflare/anti-bot walls.
- **Modernized GUI Log**: 
  - **Real-Time Feedback**: Logs batch-by-batch progress during large scrapes.
  - **Color-Coded**: Visual cues for success ✅, errors ❌, and scanning updates 🕵️.
- **Default Paths**: Automatically creates `TV/` and `Movie/` subfolders if no paths are configured.

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
  "theme": "dark",
  "ffmpeg_path": "C:/tools/ffmpeg_libfdk.exe",
  "ytdlp_path": "C:/tools/yt-dlp.exe"
}
```

*   **ffmpeg_path**: Full path to a specific `ffmpeg` executable (optional).
*   **ytdlp_path**: Full path to a specific `yt-dlp` executable (optional).

### 🚫 Iframe Ignore List (`ignore_iframes.txt`)

You can manually skip specific domains during the iframe scanning process. Create a file named `ignore_iframes.txt` in the script directory and add one domain per line:
```text
example.com
ads.service.net
```
The script re-scans this file for every attempt, allowing you to update it on the fly.

---

## ❓ Troubleshooting

### High CPU Usage
The application is optimized to reuse browser instances and block non-essential resources (images/fonts) during metadata scraping. If you still encounter high CPU usage:
1. Ensure you are running in **Headless Mode** unless you need to solve a captcha.
2. Check that your `completed.log` isn't massive (thousands of entries), as larger logs take slightly more time to cross-reference (though the impact is minimal).

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