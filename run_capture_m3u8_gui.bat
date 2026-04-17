@echo off
title Capture M3U8 GUI
cls

echo ==================================================
echo            Capture M3U8 GUI Launcher
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

:: 3. Install/Update Dependencies
if exist requirements.txt (
    echo Checking dependencies...
    pip install -r requirements.txt
    echo [OK] Dependencies are ready.
)

:: 4. Launch the Builder
echo.
echo Launching Capture M3U8 GUI...
start "" pythonw capture_m3u8_gui.py