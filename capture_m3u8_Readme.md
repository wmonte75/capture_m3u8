# M3U8 Hunter & Downloader (CLI)

A professional-grade automated tool for capturing, downloading, and organizing HLS (M3U8) video streams. It uses Playwright to "hunt" for master manifest URLs across complex web embeds and orchestrates a specialized toolchain to deliver sanitized, normalized, and metadata-rich media files.

## Key Features

- **Intelligent Hunting**: Uses Playwright (Chromium on Windows/macOS, Firefox on Linux) to intercept network traffic and find hidden `.m3u8` master URLs, even inside nested iframes.
- **Primary Engine**: Leverages `N_m3u8DL-RE` for robust, multi-threaded HLS downloading and merging.
- **Self-Healing Toolchain**: The `-U` flag automatically downloads and updates required binaries (`FFmpeg`, `N_m3u8DL-RE`, `mkvpropedit`, `mkvmerge`) from official sources and GitHub releases. macOS `.tar.gz` and Linux binaries are fully supported.
- **IMDB Integration**: Supports direct IMDB URLs to detect media types (Movie/TV), fetch season/episode counts, and automate batch queue generation.
- **Plugin Architecture**: Modular post-processing system:
    - `001`: Container Sanitization (`mkvmerge`).
    - `002`: Audio Upmixing & Normalization (`dynaudnorm`).
    - `010`: TMDB/OMDB Metadata & Library Organization.
- **OS Aware**: Fully compatible with Windows, Linux (Arch/Debian/BigLinux), and macOS.

## Setup

1.  **Dependencies**:
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```
    (Linux users may also need: `playwright install-deps`)

2.  **Initialize Tools**:
    Run the update command to automatically populate the `binaries/` folder:
    ```bash
    python capture_m3u8.py -U
    ```

## Usage

### 1. Single Download
Pass a direct URL or an IMDB link:
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0090540/"
```

### 2. Batch Processing
Load a text file containing a list of URLs (one per line):
```bash
python capture_m3u8.py my_queue.txt
```

### 3. IMDB Scraper
Generate local queues from the IMDB Top 250 lists:
```bash
python capture_m3u8.py scrapemovie
python capture_m3u8.py scrapetv
```

### 4. Update Tools
Download/update N_m3u8DL-RE and MKVToolNix:
```bash
python capture_m3u8.py -U
```

## Configuration

Edit `config.json` to customize your environment. All keys can also be set via the GUI Settings window.

| Key | Default | Description |
|-----|---------|-------------|
| `movies_dir` | `""` | Final destination folder for movies. |
| `tv_dir` | `""` | Final destination folder for TV shows. |
| `download_speed` | `"6M"` | Global speed limit (e.g., `"2M"`, `"Unlimited"`). |
| `min_cooldown` | `10` | Minimum seconds between batch items. |
| `max_cooldown` | `25` | Maximum seconds between batch items. |
| `subtitle_langs` | `"all"` | Preferred subtitle languages. |
| `session_reset_count` | `5` | Browser session auto-clear interval. |
| `movie_template` | `"https://vsembed.ru/embed/movie?imdb={imdb}"` | Movie embed URL template. |
| `tv_template` | `"https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}"` | TV embed URL template. |
| `auto_speed_by_resolution` | `false` | Enable PRO tiered speed caps. |
| `speed_cap_1080` | `"2.5M"` | Speed cap for 1080p+ streams. |
| `speed_cap_720` | `"2M"` | Speed cap for 720p streams. |
| `speed_cap_480` | `"1.5M"` | Speed cap for 480p streams. |
| `speed_cap_360` | `"1M"` | Speed cap for 360p and below. |
| `preferred_resolution` | `"Auto"` | Force quality: `Auto`, `1080p`, `720p`, `480p`, `360p`. |
| `ffmpeg_path` | `""` | Override FFmpeg location. |
| `ffprobe_path` | `""` | Override FFprobe location. |
| `mkvpropedit_path` | `""` | Override mkvpropedit location. |
| `nm3u8dl_re_path` | `""` | Override N_m3u8DL-RE location. |
| `mkvmerge_path` | `""` | Override mkvmerge location. |

**API Keys (for TMDB plugin):**
- `tmdb_api_key`: Your TMDB API key.
- `fanart_api_key`: Your Fanart.tv API key.
- `omdb_api_key`: Your OMDB API key.

## Project Structure
- `/binaries`: Contains portable executables (`FFmpeg`, `mkvmerge`, etc.).
- `/binaries/Logs`: Centralized location for `completed.log`, `cookies.txt`, and plugin logs.
- `/plugins`: Sequence-based scripts for file processing.
- `/temp_downloads`: Workspace for active downloads and `.quu` queue files.
- `/browser_session`: Persistent Playwright user data.

## Notes
- All logs are stored in `binaries/Logs/` to keep the root directory clean.
- The program uses an OS-aware locking mechanism to ensure only one instance downloads at a time, placing subsequent calls into a queue.
- Browser stealth scripts are injected at the **context level** so all pages and iframes receive them, including `navigator.webdriver` removal, `chrome.runtime` mocking, and plugin spoofing.
