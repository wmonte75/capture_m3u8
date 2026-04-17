# MKV Container Sanitizer (001_mkvmerge_cleanup.py)

This plugin is a high-priority "Polishing" tool designed to run **early** in your plugin chain. Its job is to verify and rebuild the Matroska container to ensure technical perfection before other tools (like normalization or tagging) touch the file.

## ❓ The Problem
Downloads from HLS (M3U8) streams are inherently "messy." Because they are assembled from hundreds of small fragments, they often suffer from:
- **Broken Timestamps**: Causing audio-sync drift or playback stutters.
- **Missing Durations**: Files showing "Duration: N/A" in media players.
- **Junk Headers**: Lingering MPEG-TS artifacts that confuse players.
- **Seeking Issues**: The inability to jump to a specific time in the video.

## ✨ Solution
This plugin uses `mkvmerge` (the gold standard for Matroska manipulation) to perform a non-destructive remux. Instead of just copying streams, it rebuilds the entire container structure from the ground up. 

This process:
1. **Sanitizes** the file by fixing all timestamp and header irregularities.
2. **Ensures** a valid Matroska container, even if the source was `.ts` or `.mp4`.
3. **Validates** integrity, ensuring the file is ready for your permanent collection.

## 🚀 Setup & Requirements

### 1. Requirements
- **MKVToolNix (mkvmerge)**: Required for the sanitization process.
- **Config**: Automatically uses `mkvmerge_path` from `config.json`.

### 2. Auto-Logic
- **Priority**: Config -> `binaries/` folder -> Program Root -> System PATH.
- **Auto-Update**: Running `python capture_m3u8.py -U` will automatically download the latest `mkvmerge` into your `binaries` folder.

## 🛠️ Usage

### Automated
Place `001_mkvmerge_cleanup.py` in the `plugins/` folder. Its `001_` prefix ensures it runs immediately after a download finishes. This provides a "clean" file for normalization (`002`) and TMDB enrichment (`010`) to work with.

### Manual Usage
You can run it manually to repair or sanitize a specific file:

**Windows:**
```powershell
python plugins/001_mkvmerge_cleanup.py "C:\path\to\video.mkv"
```

**Linux:**
```bash
python3 plugins/001_mkvmerge_cleanup.py "/path/to/video.mkv"
```

## 📝 Notes
- This plugin is non-destructive; it creates a temporary sanitized file and replaces the original only upon a successful exit code (0 or 1) from `mkvmerge`.
- It ignores files that already contain the `_Sanitized` suffix to prevent accidental loops.