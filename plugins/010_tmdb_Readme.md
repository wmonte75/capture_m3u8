# TMDB Plugin (010_tmdb.py)

This plugin provides automated movie and TV show organization for `capture_m3u8`. It parses filenames, fetches high-quality metadata from TMDB, OMDB, and Fanart.tv, generates `.nfo` files, and organizes your media into structured libraries.

## 🚀 Setup & Requirements

The plugin acts autonomously. It requires valid API keys and access to media tools (FFmpeg, FFprobe, mkvpropedit).

### 1. Acquire API Keys

You will need to create free accounts on the following services to get your keys:

*   **TMDB (The Movie Database)**: 
    *   [https://www.themoviedb.org/documentation/api](https://www.themoviedb.org/documentation/api)
    *   Used for: Primary metadata, cast, and folder organization.
*   **Fanart.tv**:
    *   [https://fanart.tv/get-an-api-key/](https://fanart.tv/get-an-api-key/)
    *   Used for: High-quality posters and fanart backgrounds.
*   **OMDB (Open Movie Database)**:
    *   [http://www.omdbapi.com/apikey.aspx](http://www.omdbapi.com/apikey.aspx)
    *   Used for: Accurate IMDB ratings.

### 2. Configuration

Open `config.json` in the program root and fill in the following fields:

```json
{
    "tmdb_api_key": "YOUR_KEY_HERE",
    "fanart_api_key": "YOUR_KEY_HERE",
    "omdb_api_key": "YOUR_KEY_HERE",
    "movies_dir": "/path/to/your/Movies",
    "tv_dir": "/path/to/your/TV",
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "mkvpropedit_path": ""
}
```

### 3. Dependencies

*   **FFmpeg & FFprobe**: Required for thumbnail extraction.
*   **mkvpropedit**: Required for internal MKV title tagging.

**Priority Order for Tools**:
1.  Path specified in `config.json`
2.  `binaries/` subfolder
3.  Program root folder
4.  System `PATH`

## ⚙️ How it Works

1.  **Download**: The main script saves the file to `temp_downloads`.
2.  **Plugin Launch**: `010_tmdb.py` is called automatically upon download completion.
3.  **Parsing**: It parses the filename, intelligently stripping plugin suffixes like `_Sanitized` or `_DualAudio` to ensure better metadata matching.
4.  **Enrichment**: It fetches posters, ratings, and cast info from the APIs.
5.  **Final Move**: It creates the library folder (e.g., `TV/Title (Year)/Season 01/`) and moves the file there.
6.  **Cleanup**: It generates the `.nfo` and thumbnail alongside the final file.

## 🛠️ Manual Usage

You can run the plugin manually from the command line if you need to organize existing files.

**Linux:**
```bash
python3 plugins/010_tmdb.py "/absolute/path/to/media.mkv"
```

**Windows:**
```powershell
python plugins/010_tmdb.py "C:\path\to\media.mkv"
```

## ⚠️ Troubleshooting

If the plugin detects that your `tmdb_api_key` or required tools are missing, it will prompt you with an alert and log a warning pointing you back to this file for setup instructions.
