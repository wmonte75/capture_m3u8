# TV Normalization Plugin (002_norm_tv.py)

This plugin provides specialized audio processing for TV episodes, ensuring consistent volume levels and high-quality surround sound across entire series.

## ✨ Features
- **TV Detection**: Automatically triggers for files containing `SxxExx` patterns and skips movies.
- **5.1 Audio Upmixing**: Intelligently upmixes stereo sources to a 5.1 surround soundstage for the primary track.
- **Dual Audio Tracks**:
    - **Track 1 (Default)**: Normalized 5.1 Surround (optimized for clear dialogue).
    - **Track 2**: Direct Source Match (Original stereo or 5.1 track).
- **VBR Efficiency**: Uses Variable Bitrate encoding (`-q:a 2`) to maintain transparency while reducing file size for long-term archiving.

## 🚀 Setup & Requirements

### 1. Requirements
- **FFmpeg**: Required for audio processing and muxing.
- **Config**: Automatically discovers FFmpeg in the `binaries/` folder or via `config.json`.

### 2. Auto-Update
The required binaries can be updated automatically by running `python capture_m3u8.py -U`.

## 🛠️ Usage

### Automated
Place `002_norm_tv.py` in the `plugins/` folder. It will process all TV downloads before they are moved to your library by the TMDB plugin.

### Manual Usage
```powershell
python plugins/002_norm_tv.py "C:\path\to\Episode.S01E01.mkv"
```

## 📝 Notes
- Strips `_Sanitized` from filenames added by the cleanup plugin.
- Appends `_DualAudio` to indicate processing is complete.
- Normalization parameters: `dynaudnorm=f=200:g=7` (optimized for broadcast dynamics).