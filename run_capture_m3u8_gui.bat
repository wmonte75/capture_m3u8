@echo off
title Capture M3U8 GUI
cls

echo ==================================================
echo           Capture M3U8 GUI Launcher
echo ==================================================
echo.

:: 1. Check Python Installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your PATH.
    echo.
    echo Please download and install Python 3.8 or newer:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check Python Version (>= 3.8)
python -c "import sys; exit(0 if sys.version_info >= (3,8) else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Python version is too old.
    echo Detected:
    python --version
    echo.
    echo Please install Python 3.8 or newer.
    pause
    exit /b 1
)

:: 3. Install/Update Python Dependencies
if exist requirements.txt (
    echo Checking Python dependencies...
    pip install -r requirements.txt
    echo [OK] Python dependencies are ready.
)

:: 4. Install Playwright Browser Engines (first-run only)
echo.
echo Checking Playwright browser engines...
python -c "from playwright._impl._driver import compute_driver_executable; import os; path = os.path.join(os.environ.get('LOCALAPPDATA',''), 'ms-playwright'); exit(0 if os.path.exists(path) and os.listdir(path) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo First-run: Downloading Playwright browser engines ^(this only happens once^)...
    playwright install chromium
    echo [OK] Browser engines downloaded.
) else (
    echo [OK] Browser engines already installed.
)

:: 5. Download Toolchain Binaries (FFmpeg, N_m3u8DL-RE, mkvmerge)
echo.
echo Checking toolchain binaries...
if not exist "binaries\N_m3u8DL-RE.exe" (
    echo First-run: Downloading required binaries ^(FFmpeg, N_m3u8DL-RE, mkvmerge^)...
    python capture_m3u8.py -U
    echo [OK] Binaries downloaded.
) else (
    echo [OK] Binaries already present.
)

:: 6. Launch the GUI
echo.
echo Launching Capture M3U8 GUI...
start "" pythonw capture_m3u8_gui.py
