# Stream Capture & Downloader

A powerful Python tool to automatically detect, capture, and download M3U8 video streams from various streaming websites. It utilizes **Playwright** for browser automation to handle dynamic content and **yt-dlp** for robust downloading.

## 🚀 Features

- **Auto-Detection**: Sniffs network traffic to find `master.m3u8` streams.
- **Browser Automation**: Uses a real browser (Chromium) to bypass simple anti-bot protections and render JavaScript.
- **IMDB Support**: Automatically converts IMDB URLs (e.g., `imdb.com/title/tt1234567`) to streaming sources.
- **Robust Downloading**: Integrates with `yt-dlp` to download streams with resume capability and error handling.
- **Modes**:
  - **Headless**: Runs in the background.
  - **Visible**: Shows the browser window for debugging or manual interaction.
  - **Queue System**: Process multiple URLs sequentially from a text file with resume capability.
- **Auto-Start**: Can be run with a URL argument for automated batch processing.

## 🛠️ Prerequisites

- **Python 3.8+**
- **yt-dlp**: The tool looks for `yt-dlp.exe` in the script directory or system PATH.

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

### Batch / Queue Mode 
Create a text file (e.g., queue.txt) with one URL per line. Lines starting with # are ignored. 
```bash
python capture_m3u8.py queue.txt
```
The script will: 
1. Process URLs one by one. 
2. Skip URLs already listed in completed.log.
3. Wait 5 seconds between downloads to avoid rate limits.

## 📂 Output

- Downloads are saved as `.mp4` files in the script directory.
- A text file (e.g., `Movie.Name.txt`) is generated with the stream details and manual `yt-dlp` command for future reference.