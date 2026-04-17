# M3U8 Hunter & Downloader Suite

A world-class, automated toolchain designed for capturing, downloading, and organizing HLS (M3U8) video streams. This suite combines a Playwright-powered "Hunter" with a modular plugin architecture to deliver technically perfect, metadata-rich media for your library.

## 🌟 Overview

This project bridges the gap between complex web-embedded video players and a clean, organized media library. It handles everything from bypasssing bot detection to audio upmixing and TMDB-based folder organization.

### Key Features
- **Dual Interface**: Full-featured **CustomTkinter GUI** for interactive use and a robust **CLI** for automation.
- **Intelligent Capture**: Uses Playwright to hunt for master manifests within nested iframes and network traffic.
- **Self-Healing Toolchain**: Automatically downloads and updates required binaries (`N_m3u8DL-RE`, `FFmpeg`, `mkvmerge`) via the `-U` flag.
- **OS Aware**: Optimized performance and dependency handling for both **Windows** and **Linux** (BigLinux/Arch/Debian).
- **Advanced Queueing**: Integrated IMDB scraper to generate batch download queues for entire series or Top 250 lists.

## 🔌 Automated Plugin Pipeline

Once a download completes, the file is passed through a sequential plugin chain:

1.  **[001] Cleanup**: Uses `mkvmerge` to sanitize the container, fixing broken timestamps and seeking issues.
2.  **[002] Normalization**: Upmixes stereo to 5.1 and applies `dynaudnorm` for consistent, professional-grade audio.
3.  **[010] TMDB Enrichment**: Identifies the title, fetches posters/NFOs, tags the MKV header, and moves the file to your permanent library.

## 🚀 Prerequisites & Detailed Installation

This suite requires Python 3.8 or higher. Follow the specific instructions for your Operating System below to ensure Python and Pip are configured correctly.

### 1. Windows Installation
1.  **Download**: Visit python.org and download the latest "Windows installer (64-bit)".
2.  **Install**: Run the `.exe` installer.
    - **CRITICAL**: Check the box at the bottom that says **"Add Python to PATH"** before clicking "Install Now".
3.  **Verify**: Open Command Prompt (`cmd`) and type:
    ```cmd
    python --version
    pip --version
    ```
    *If either command is not recognized, you may need to restart your PC or manually add the Python Scripts folder to your Environment Variables.*

### 2. Linux Installation
Most Linux distributions come with Python pre-installed, but often lack `pip` and the `tk` (Tkinter) headers required for the GUI.

#### **Ubuntu / Debian / Linux Mint / Kali**
Open your terminal and run:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
```

#### **Arch Linux / Manjaro / BigLinux**
Open your terminal and run:
```bash
sudo pacman -Syu python python-pip tk
```

#### **Fedora / RHEL / CentOS**
Open your terminal and run:
```bash
sudo dnf install python3 python3-pip python3-tkinter
```

### 3. Setting Up the Project
Once Python and Pip are verified as working on your system, initialize the Hunter Suite environment:

1.  **Clone/Extract**: Navigate to the `capture_m3u8/` directory in your terminal.
2.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Install Playwright Drivers**:
    ```bash
    playwright install-deps
    ```

### 4. Initialize the Toolchain
Before your first run, you must populate the `binaries/` folder with the required engines (FFmpeg, N_m3u8DL-RE, etc.). The suite handles this automatically:
```bash
python capture_m3u8.py -U
```
This command is OS-aware; it will detect your platform and download the appropriate binaries for you.

## 🛠️ Usage

### Graphical Interface (Recommended)
To launch the modern Hunter GUI:
```bash
python capture_m3u8_gui.py
```

### Command Line Interface
To capture and download a single title via the terminal:
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0090540/"
```

**Launch the GUI:**
```bash
python capture_m3u8_gui.py
```

**Run the CLI (Single Title):**
```bash
python capture_m3u8.py "https://www.imdb.com/title/tt0090540/"
```

## ⚙️ Configuration

The suite is controlled via `config.json`. Key settings include:
- `movies_dir` / `tv_dir`: Your library destination paths.
- `movie_template` / `tv_template`: Customizable embed provider URLs.
- `download_speed`: Bandwidth throttling to prevent server-side 429 errors.

## 📂 Project Structure

*   `binaries/`: Portable executables and centralized logs.
*   `plugins/`: The post-processing engine.
*   `temp_downloads/`: Active workspace for downloads and `.quu` queue files.

## 🛡️ Stability & Safety
- **OS-Aware Locking**: Ensures only one instance of `N_m3u8DL-RE` runs at a time, queueing subsequent requests.
- **Stale Session Cleanup**: Automatically clears browser cache and temporary data older than 30 minutes.
- **User-Agent Matching**: Synchronizes fingerprints with your host OS to bypass advanced anti-bot measures.

---
*Developed with a focus on high code quality, portability, and user experience.*

---

**Related Documentation:**
- GUI Detailed Guide
- CLI Detailed Guide