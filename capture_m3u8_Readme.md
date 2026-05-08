# M3U8 Hunter & Downloader (CLI)

A professional-grade automated tool for capturing, downloading, and organizing HLS (M3U8) video streams. It uses Playwright to "hunt" for master manifest URLs across complex web embeds and orchestrates a specialized toolchain to deliver sanitized, normalized, and metadata-rich media files.

## ✨ Key Features

- **Intelligent Hunting**: Uses Playwright (Chromium/Firefox) to intercept network traffic and find hidden `.m3u8` master URLs, even inside nested iframes.
- **Primary Engine**: Leverages `N_m3u8DL-RE` for robust, multi-threaded HLS downloading and merging.
- **Self-Healing Toolchain**: The `-U` flag automatically downloads and updates required binaries (`FFmpeg`, `N_m3u8DL-RE`, `mkvpropedit`) from official sources and GitHub releases.
- **IMDB Integration**: Supports direct IMDB URLs to detect media types (Movie/TV), fetch season/episode counts, and automate batch queue generation.
- **Plugin Architecture**: Modular post-processing system:
    - `001`: Container Sanitization (`mkvmerge`).
    - `002`: Audio Upmixing & Normalization (`dynaudnorm`).
    - `010`: TMDB/OMDB Metadata & Library Organization.
- **OS Aware**: Fully compatible with Windows and Linux (Arch/Debian/BigLinux).

## 🚀 Setup

1.  **Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Initialize Tools**:
    Run the update command to automatically populate the `binaries/` folder with the required engines:
    ```bash
    python capture_m3u8.py -U
    ```

## 🛠️ Usage

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

## ⚙️ Configuration
Edit `config.json` to customize your environment:
- `movies_dir` / `tv_dir`: Final library destinations.
- `download_speed`: Limit bandwidth to avoid 429 errors (e.g., "6M").
- `min_cooldown` / `max_cooldown`: Random delay between batch items.
- **Remote Transfer (SFTP)**: Set `scp_enabled` to `true` and provide `scp_host`, `scp_username`, and either `scp_key_path` (SSH key) or `scp_password`. Use `scp_remote_movies_dir` and `scp_remote_tv_dir` to map local folders to remote paths. Enable `scp_delete_local` to remove the local copy after a successful upload.

## 📂 Project Structure
- `/binaries`: Contains portable executables (`FFmpeg`, `mkvmerge`, etc.).
- `/binaries/Logs`: Centralized location for `completed.log`, `cookies.txt`, and plugin logs.
- `/plugins`: Sequence-based scripts for file processing.
- `/temp_downloads`: Workspace for active downloads and `.quu` queue files.

## 📝 Notes
- All logs are stored in `binaries/Logs/` to keep the root directory clean.
- The program uses an OS-aware locking mechanism to ensure only one instance downloads at a time, placing subsequent calls into a queue.