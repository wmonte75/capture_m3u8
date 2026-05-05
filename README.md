# M3U8 Hunter & Downloader Suite

A world-class, automated toolchain designed for capturing, downloading, and organizing HLS (M3U8) video streams. This suite combines a Playwright-powered "Hunter" with a modular plugin architecture to deliver technically perfect, metadata-rich media for your library.

## Overview

This project bridges the gap between complex web-embedded video players and a clean, organized media library. It handles everything from bypassing bot detection to audio upmixing and TMDB-based folder organization.

### Key Features
- **Dual Interface**: Full-featured **CustomTkinter GUI** with tabbed settings and a robust **CLI** for automation.
- **Intelligent Capture**: Uses Playwright to hunt for master manifests within nested iframes and network traffic.
- **Self-Healing Toolchain**: Automatically downloads and updates required binaries (`N_m3u8DL-RE`, `FFmpeg`, `mkvmerge`) via the `-U` flag or the built-in dependency installer.
- **OS Aware**: Optimized for **Windows**, **Linux** (Arch/Debian/BigLinux), and **macOS**.
- **Advanced Queueing**: Integrated IMDB scraper to generate batch download queues for entire series or Top 250 lists.
- **PRO Speed Control**: Auto-detects stream resolution and applies tiered speed caps to prevent 429 rate-limiting.
- **Preferred Resolution**: Choose exact quality (1080p/720p/480p/360p) instead of auto-select.

## Automated Plugin Pipeline

Once a download completes, the file is passed through a sequential plugin chain:

1.  **[001] Cleanup**: Uses `mkvmerge` to sanitize the container, fixing broken timestamps and seeking issues.
2.  **[002] Normalization**: Upmixes stereo to 5.1 and applies `dynaudnorm` for consistent, professional-grade audio.
3.  **[010] TMDB Enrichment**: Identifies the title, fetches posters/NFOs, tags the MKV header, and moves the file to your permanent library.

## Prerequisites & Detailed Installation

This suite requires Python 3.8 or higher. Follow the specific instructions for your Operating System below.

### 1. Windows Installation
1.  **Download**: Visit python.org and download the latest "Windows installer (64-bit)".
2.  **Install**: Run the `.exe` installer.
    - **CRITICAL**: Check the box at the bottom that says **"Add Python to PATH"** before clicking "Install Now".
3.  **Verify**: Open Command Prompt (`cmd`) and type:
    ```cmd
    python --version
    pip --version
    ```

### 2. Linux Installation
Most Linux distributions come with Python pre-installed, but often lack `pip` and the `tk` (Tkinter) headers required for the GUI.

#### Ubuntu / Debian / Linux Mint / Kali
```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
```

#### Arch Linux / Manjaro / BigLinux
```bash
sudo pacman -Syu python python-pip tk
```

#### Fedora / RHEL / CentOS
```bash
sudo dnf install python3 python3-pip python3-tkinter
```

### 3. Setting Up the Project
1.  **Clone/Extract**: Navigate to the `capture_m3u8/` directory in your terminal.
2.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Install Playwright Browsers**:
    ```bash
    playwright install chromium
    ```
    (Linux users may also need: `playwright install-deps`)

### 4. Initialize the Toolchain
Before your first run, you must populate the `binaries/` folder with the required engines. The suite handles this automatically:
```bash
python capture_m3u8.py -U
```

On first GUI launch, a **Dependency Installer** dialog will appear if tools are missing, offering one-click downloads (where supported) or package manager instructions.

## Usage

### Graphical Interface (Recommended)
To launch the modern Hunter GUI:
```bash
# Windows
run_capture_m3u8_gui.bat

# Linux
chmod +x run_capture_m3u8_gui.sh
./run_capture_m3u8_gui.sh
```

### Command Line Interface
To capture and download a single title via the terminal:
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0090540/"
```

To process a batch list:
```bash
python capture_m3u8.py my_queue.txt
```

To update tools:
```bash
python capture_m3u8.py -U
```

## Configuration

The suite is controlled via `config.json`. All settings can also be edited in the GUI's **Settings** window (4 tabs: General, Download, Providers, Tools).

### General Tab
| Key | Default | Description |
|-----|---------|-------------|
| `movies_dir` | `""` | Final destination folder for movies. |
| `tv_dir` | `""` | Final destination folder for TV shows. |
| `theme` | `"dark"` | Interface theme: `"dark"` or `"light"`. |
| `headless` | `false` | Run browser in hidden mode by default. |
| `subtitle_langs` | `"all"` | Preferred subtitle languages. |
| `session_reset_count` | `5` | Browser session auto-clear interval. |

### Download Tab
| Key | Default | Description |
|-----|---------|-------------|
| `download_speed` | `"6M"` | Global download speed limit (e.g., `"2M"`, `"Unlimited"`). |
| `min_cooldown` | `10` | Minimum seconds between queue items. |
| `max_cooldown` | `25` | Maximum seconds between queue items. |
| `auto_speed_by_resolution` | `false` | **PRO**: Auto-cap speed based on detected resolution. |
| `speed_cap_1080` | `"2.5M"` | Speed cap when 1080p+ is detected. |
| `speed_cap_720` | `"2M"` | Speed cap when 720p is detected. |
| `speed_cap_480` | `"1.5M"` | Speed cap when 480p is detected. |
| `speed_cap_360` | `"1M"` | Speed cap when 360p or lower is detected. |
| `preferred_resolution` | `"Auto"` | Force a specific quality: `Auto`, `1080p`, `720p`, `480p`, `360p`. |

### Providers Tab
| Key | Default | Description |
|-----|---------|-------------|
| `movie_template` | `"https://vsembed.ru/embed/movie?imdb={imdb}"` | Embed URL template for movies. Use `{imdb}` placeholder. |
| `tv_template` | `"https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}"` | Embed URL template for TV. Use `{imdb}`, `{s}`, `{e}`. |

### Tools Tab
| Key | Default | Description |
|-----|---------|-------------|
| `ffmpeg_path` | `""` | Override FFmpeg location. Leave blank for auto-detect. |
| `ffprobe_path` | `""` | Override FFprobe location. |
| `mkvpropedit_path` | `""` | Override mkvpropedit location. |
| `nm3u8dl_re_path` | `""` | Override N_m3u8DL-RE location. |
| `mkvmerge_path` | `""` | Override mkvmerge location. |

## Project Structure

*   `binaries/`: Portable executables and centralized logs.
*   `plugins/`: The post-processing engine.
*   `temp_downloads/`: Active workspace for downloads and `.quu` queue files.
*   `browser_session/`: Persistent Playwright user data (cookies, localStorage).

## Stability & Safety
- **OS-Aware Locking**: Ensures only one instance of `N_m3u8DL-RE` runs at a time, queueing subsequent requests.
- **Stale Session Cleanup**: Automatically clears browser cache and temporary data older than 30 minutes.
- **Stealth Injection**: Mocks `navigator.webdriver`, `chrome.runtime`, plugins, and other bot-detection signals at the context level so all pages and iframes receive them.

---

**Related Documentation:**
- [GUI Detailed Guide](capture_m3u8_gui_Readme.md)
- [CLI Detailed Guide](capture_m3u8_Readme.md)
