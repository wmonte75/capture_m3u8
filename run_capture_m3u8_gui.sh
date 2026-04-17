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

# 5. Activate and Install Dependencies
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

if [ -f "requirements.txt" ]; then
    echo "Updating dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "[OK] Dependencies are ready."
fi

# 6. Launch the GUI
echo ""
echo "Launching Capture M3U8 GUI..."
# Running with the venv's python explicitly
python3 capture_m3u8_gui.py & 

# Deactivate is not strictly necessary in a subshell but good practice
# however, since we are backgrounding the process, we just exit the script.
echo "Process started in background. You may close this terminal."

exit 0