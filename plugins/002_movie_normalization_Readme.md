# Movie Normalization Plugin (002_movie_normalization.py)

This plugin specializes in enhancing the audio experience of movies by upmixing stereo tracks and normalizing volume levels. It creates a robust **Dual Audio** output, ensuring you have both a normalized track for consistent volume and a direct track for pure audio.

## ✨ Features

- **5.1 Audio Upmixing**: Converts stereo (2.0) audio into a simulated 5.1 surround sound experience using a custom FFmpeg pan filter.
- **Dynamic Normalization**: Applies the `dynaudnorm` filter to the first audio track to smooth out volume spikes and dips (perfect for night-time viewing).
- **Dual Audio Output**:
    - **Track 1**: Normalized 5.1 Surround
    - **Track 2**: Direct 5.1 Surround (Original dynamics)
- **Automatic TV Detection**: Identifies TV Show patterns (e.g., `S01E01`) in filenames and **skips them automatically** to preserve original broadcast audio.
- **Smart 5.1 Detection**: If a file already has 5.1 or 6-channel audio, it skips the upmix step and simply applies the normalization.
- **Cleanup**: Automatically deletes the original stereo file after a successful conversion to save space.

## 🚀 Setup & Requirements

### 1. FFmpeg
This plugin relies heavily on **FFmpeg**. 
- Priority: Config -> `binaries/` folder -> Program Root -> System PATH.
- Auto-Update: Running `python capture_m3u8.py -U` will automatically download the latest FFmpeg.

### 2. Output Format
The resulting file will have `_DualAudio` appended to the filename (e.g., `Movie_DualAudio.mkv`).

## 🛠️ Usage

### Automated (Plugin Mode)
Simply place `002_movie_normalization.py` in the `plugins/` folder. `capture_m3u8.py` will run it automatically before the TMDB organization plugin.

### Manual Usage
You can run the plugin manually on any video file:

**Linux:**
```bash
python3 plugins/002_movie_normalization.py "/path/to/movie.mkv"
```

**Windows:**
```powershell
python plugins/002_movie_normalization.py "C:\path\to\movie.mkv"
```

## 📋 Technical Details (FFmpeg)
The plugin uses the following complex filter chain:
- **Stereo**: `pan=5.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.5*c0+0.5*c1|BL=c0|BR=c1`
- **Normalization**: `dynaudnorm=f=200:g=7`
- **Encoder**: Native AAC using Variable Bitrate (VBR) at Quality Scale 2 (`-q:a 2`), 48000Hz.
