#!/usr/bin/env bash

# Set the title for the terminal window
echo -ne "\033]0;Capture M3U8 GUI\007"
clear

echo "=================================================="
echo "           Capture M3U8 GUI Launcher"
echo "=================================================="
echo ""

# 1. Check Python 3 Installation
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    echo "Please install Python 3.8 or newer using your package manager."
    echo "Example (Ubuntu/Debian): sudo apt update && sudo apt install python3"
    exit 1
fi

# 2. Check Python Version (>= 3.8)
python3 -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"
if [ $? -ne 0 ]; then
    echo "[ERROR] Python version is too old."
    echo "Detected: $(python3 --version)"
    echo "Please install Python 3.8 or newer."
    exit 1
fi

# 3. Check for tkinter (Required for GUI on Linux)
python3 -c "import tkinter" &> /dev/null
if [ $? -ne 0 ]; then
    echo "[ERROR] python3-tk is not installed."
    echo "On Linux, tkinter must be installed via the system package manager."
    echo "Example (Ubuntu/Debian): sudo apt install python3-tk"
    exit 1
fi

# 4. Handle Virtual Environment (Modern Linux Standard PEP 668)
VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        echo "You may need to install the venv module."
        echo "Example (Ubuntu/Debian): sudo apt install python3-venv"
        exit 1
    fi
fi

# 5. Activate and Install Python Dependencies
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [ -f "requirements.txt" ]; then
    echo "Updating Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "[OK] Python dependencies are ready."
fi

# 6. Install Playwright Browser Engines and System Dependencies (first-run only)
echo ""
echo "Checking Playwright browser engines..."
if [ ! -d "$HOME/.cache/ms-playwright" ]; then
    echo "First-run: Installing Playwright system dependencies..."
    playwright install-deps 2>/dev/null
    echo "First-run: Downloading Playwright browser engines (this only happens once)..."
    playwright install firefox
    echo "[OK] Browser engines downloaded."
else
    echo "[OK] Browser engines already installed."
fi

# 7. Download Toolchain Binaries (FFmpeg, N_m3u8DL-RE, mkvmerge)
echo ""
echo "Checking toolchain binaries..."
if [ ! -f "binaries/N_m3u8DL-RE" ] && [ ! -f "binaries/N_m3u8DL-RE.exe" ]; then
    echo "First-run: Downloading required binaries (FFmpeg, N_m3u8DL-RE, mkvmerge)..."
    python3 capture_m3u8.py -U
    echo "[OK] Binaries downloaded."
else
    echo "[OK] Binaries already present."
fi

# 8. Launch the GUI
echo ""
echo "Launching Capture M3U8 GUI..."
python3 capture_m3u8_gui.py &

echo "Process started in background. You may close this terminal."

exit 0
