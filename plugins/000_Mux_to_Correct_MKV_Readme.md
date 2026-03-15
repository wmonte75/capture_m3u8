# MKV Container Fixer (000_Mux_to_Correct_MKV.py)

This plugin is a critical "Safety Wrapper" designed to run **first** in your plugin chain. Its job is to ensure that any video file (even if it already has a `.mkv` extension) is internally a proper Matroska container.

## ❓ The Problem
Many downloads (especially from M3U8 streams) are saved as **MPEG Transport Streams (MPEG-TS)**. Even if they are saved with a `.mkv` extension, tools like `mkvpropedit` will fail because they don't recognize the internal format.

## ✨ Solution
This plugin uses `ffprobe` to inspect the internal container format. If it detects a non-Matroska stream, it uses `ffmpeg -c copy` (instant, no quality loss) to remux the content into a proper Matroska container.

## 🚀 Setup & Requirements

### 1. Requirements
- **FFmpeg & FFprobe**: Required for inspection and remuxing.
- **Config**: Automatically uses `ffmpeg_path` and `ffprobe_path` from `config.json`.

### 2. Auto-Logic
- **Priority**: Config -> Program Root -> System PATH.
- **Auto-Update**: If configuration keys are missing, the plugin will automatically add them to `config.json` on the first run.

## 🛠️ Usage

### Automated
Place `000_Mux_to_Correct_MKV.py` in the `plugins/` folder. It should be named with `000_` to ensure it runs **before** any other plugins.

### Manual Usage
You can run it manually to fix a specific file:

**Linux:**
```bash
python3 plugins/000_Mux_to_Correct_MKV.py "/path/to/media.mkv"
```

**Windows:**
```powershell
python plugins/000_Mux_to_Correct_MKV.py "C:\path\to\media.mkv"
```
