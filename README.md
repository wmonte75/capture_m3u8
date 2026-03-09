# Stream Capture & Downloader

A powerful Python tool to automatically detect, capture, and download M3U8 video streams from various streaming websites. It utilizes **Playwright** for browser automation to handle dynamic content and **yt-dlp** for robust downloading.

## 🚀 Features

- **Auto-Detection**: Sniffs network traffic to find `master.m3u8` streams.
- **Browser Automation**: Uses a real browser (Chromium) to bypass simple anti-bot protections and render JavaScript.
- **IMDB Support**: Automatically converts IMDB URLs (e.g., `imdb.com/title/tt1234567`) to streaming sources.
- **TV Series Support**: Detects TV shows from IMDB links, allowing selection of specific seasons and episodes (ranges, individual, or all).
- **Robust Downloading**: Integrates with `yt-dlp` to download streams with resume capability and error handling.
- **Smart Resume**: Checks both `completed.log` and the filesystem for existing files to prevent re-downloads. Automatically "self-heals" the log if files are found on disk.
- **Modes**:
  - **Headless**: Runs in the background.
  - **Visible**: Shows the browser window for debugging or manual interaction.
  - **Queue System**: Process multiple URLs sequentially from a text file with resume capability.
- **Auto-Start**: Can be run with a URL argument for automated batch processing.
- **Configurable**: Set custom download folders and speed limits via `config.json`.
- **Plugin System**: Extend functionality with custom Python scripts (e.g., audio upmixing, normalization) that run automatically after downloading.
- **Smart Cleanup**: Automatically removes debug files and completed queue lists to keep your folders clean.

## 🛠️ Prerequisites

- **Python 3.8+**
- **yt-dlp**: The tool looks for `yt-dlp.exe` or `yt-dlp` in the script directory or system PATH.

## 📦 Installation

1. Clone or download this repository.
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
3. Install the Playwright browsers:
   ```bash
   playwright install chromium
   ```
4. Download yt-dlp.exe and place it in this folder.

## ⚙️ Configuration

You can create a `config.json` file in the script directory to set default paths and options:
```json
{
  "movies_dir": "D:/Media/Movies",
  "tv_dir": "D:/Media/TV Shows",
  "download_speed": "10M",
  "min_cooldown": 10,
  "max_cooldown": 25,
  "subtitle_langs": "en,eng,en-forced",
  "session_reset_count": 5
}
```

## 🎮 Usage

### Interactive Mode
Simply run the script and follow the prompts:
```bash
python capture_m3u8.py
```

### Command Line / Auto Mode
Pass a URL directly to skip prompts:
```bash
python capture_m3u8.py "https://example.com/video"
```
Or with an IMDB link:
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0133093/"
```

### TV Series Mode
Run with an IMDB TV series URL: 
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0944947/"
```
The script will display the Total Seasons and Total Episodes, then ask you to select:
- Season: Specific season (e.g., 1) or all.
- Episodes: all, specific range (e.g., 1-5), specific start/end, or single episode.
The script will generate a queue file and organize downloads into Series Name/Season XX/ folders.

### Batch / Queue Mode 
Create a text file (e.g., queue.txt) with one URL per line. Lines starting with # are ignored. 
```bash
python capture_m3u8.py queue.txt
```
The script will: 
1. Process URLs one by one. 
2. Skip URLs if they are found in `completed.log` or if the video file already exists on disk.
3. Wait a random interval (10-25s) between downloads to avoid rate limits and appear human.

## 🖥️ GUI Application

For users who prefer a visual interface, run:
```bash
python capture_m3u8_gui.py
```

### Running in Background (No Terminal)

**Windows:**
Use `pythonw` instead of `python` to launch without a console window:
```powershell
pythonw capture_m3u8_gui.py
```

**Linux:**
Use `nohup` to detach the process from the terminal:
```bash
nohup python3 capture_m3u8_gui.py > /dev/null 2>&1 &
```

### Interface Guide

1.  **Input Section**
    -   **URL Field**: Paste a video URL or an IMDB link. You can also type a movie/series name and press **Enter** to search IMDB directly. Results include full metadata and movie posters. Supports a right-click context menu (Cut/Copy/Paste).
    -   **Start / Analyze**: Begins the detection and download process.
    -   **Stop**: Immediately halts the active download or search.
    -   **Check Availability**: Paste an IMDB link and click this button to quickly check if the title is available on the streaming source. Detects movie vs. TV automatically and shows a result popup. No download is started.
    -   **Load Queue**: Load a `.txt` file with one URL per line to batch-process multiple titles sequentially.
    -   **Top 250 Movies**: Scrape and download IMDB's Top 250 movie list.

2.  **Configuration Panel**
    -   **Movies / TV Folders**: Browse and select where to save your downloads.
    -   **Cooldown**: Set a random delay range (in seconds) between episodes. Settings are saved automatically.
    -   **Speed**: Limit download bandwidth (e.g., 6M, 10M, Unlimited) to prevent network congestion.
    -   **Processing Label**: Located next to the Speed dropdown. Displays `Processing file: X/Y` in real-time during batch or queue downloads, and resets to `Status: Idle` when finished.
    -   **Headless Mode**:
        -   ✅ **Checked**: Runs the browser in the background (invisible).
        -   ⬜ **Unchecked**: Shows the browser window. Use this if you need to manually solve a CAPTCHA.

3.  **TV Series Selection**
    -   When you paste an IMDB TV Series link and click **Start**, a popup will appear.
    -   **Season**: Enter a specific number (e.g., `1`) or type `all` to grab every season.
    -   **Episodes**: Optional. Enter start and end episode numbers. Leave the end blank to download to the last episode of the season.

##  Output

- **Movies**: Organized into folders (e.g., `Movie.Name/Movie.Name.mkv`).
- **TV Series**: Organized into structure `Series.Name/Season XX/Episode.Title.mkv`.
- A text file with stream details is also saved inside the folder.
- **Temp Downloads**: Files are downloaded to a `temp_downloads` folder first, then moved to the final destination upon completion to prevent file locking issues with external tools (e.g., encoders).
- **Browser Session**: Cookies and cache are saved in the `browser_session` folder to improve reliability and bypass captchas on subsequent runs.

# 🔌 Plugin System Guide

The `capture_m3u8.py` script supports a plugin system. This allows you to run your own Python scripts on the video file **after** it downloads but **before** it moves to the final folder.

## 📂 Setup

1.  **Create Folder**: Make a new folder named `plugins` inside the script directory.
2.  **Add Script**: Create a Python file (e.g., `01_add_size.py`) inside that folder.

## 📝 Example: Upmix Audio to 5.1 Surround

Here is a complete, working example. This plugin uses **FFmpeg** to convert stereo (2-channel) audio into 5.1 surround sound (6-channel).

**File:** `plugins/01_audio_upmix.py`

```python
import os
import subprocess
import sys

# Configuration: Set path to your ffmpeg binary here
# If added to system PATH, just "ffmpeg" works.
# Otherwise, use full path: r"C:\Tools\ffmpeg\bin\ffmpeg.exe"
FFMPEG_BINARY = "ffmpeg"

def process(file_path):
    """
    Upmixes audio to 5.1 surround sound using FFmpeg.
    """
    print(f"🔌 [Plugin] Upmixing audio for: {os.path.basename(file_path)}")
    
    # 1. Check if file exists and if FFmpeg is available
    if not os.path.exists(file_path):
        return file_path

    # 2. Generate output filename
    # Example: "Movie.mkv" -> "Movie_5.1.mkv"
    base_name, extension = os.path.splitext(file_path)
    output_path = f"{base_name}_5.1{extension}"
    
    # 3. Construct FFmpeg command
    # -ac 6: Set audio channels to 6 (5.1)
    # -c:v copy: Copy video stream (fast, no quality loss)
    # -c:a ac3: Encode audio to AC3 (standard for 5.1)
    cmd = [
        FFMPEG_BINARY, "-y",
        "-i", file_path,
        "-c:v", "copy",
        "-c:a", "ac3",
        "-ac", "6",
        output_path
    ]
    
    # 4. Run FFmpeg
    try:
        creation_flags = 0
        if sys.platform == 'win32':
            # This flag hides the console window on Windows
            creation_flags = subprocess.CREATE_NO_WINDOW
            
        # Run silently (stdout/stderr to DEVNULL) to keep console clean
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
        
        if os.path.exists(output_path):
            print(f"   ✅ Upmix complete: {os.path.basename(output_path)}")
            os.remove(file_path) # Delete original stereo file
            return output_path   # Return NEW path
            
    except Exception as e:
        print(f"   ❌ Upmix failed: {e}")
        return file_path
```
## ❓ Troubleshooting

### Cloudflare / Captcha Loops
If you get stuck in a "Verify you are human" loop:
1. The script automatically saves your session to the `browser_session` folder.
2. If the session gets corrupted or flagged, delete the `browser_session` folder to start fresh.
3. The script will automatically retry in **Visible Mode** if headless mode fails. You can manually solve the captcha in the visible window if needed.

### 403 / 429 Errors
If you see "Too Many Requests" or "Forbidden":
- The script has a built-in random cooldown (10-25s) to prevent this.
- If it persists, try increasing the `COOLDOWN_RANGE` in the script or changing your IP (VPN).