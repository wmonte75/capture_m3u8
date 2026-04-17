import os
import sys
import re
import subprocess
import json
import requests
import time
import shutil
import datetime
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import tkinter as tk
from tkinter import messagebox
from contextlib import redirect_stdout
import io

# --- Parity Imports ---
if os.name == 'nt':
    import msvcrt
else:
    import select

# ==============================================================================
# ⚙️ CONFIGURATION & UTILITIES
# ==============================================================================

def get_base_dir():
    """Returns the base directory of the main application."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Global Config
CONFIG = {}
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"
MKVPROPEDIT_PATH = None
TMDB_IMAGE_BASE = None
POSTER_SIZE = 'w500'
BACKDROP_SIZE = 'w1280'

# Standalone Logging
class DualLogger:
    def __init__(self, filepath, original_stdout):
        self.terminal = original_stdout
        self.log = open(filepath, "a", encoding="utf-8")
    
    def write(self, message):
        try:
            self.terminal.write(message)
            self.log.write(message)
            self.log.flush() 
        except Exception:
            pass 

    def flush(self):
        try:
            self.terminal.flush()
            self.log.flush()
        except Exception:
            pass

def get_log_dir():
    """Returns the absolute path to the Logs directory, creating it if needed."""
    log_dir = os.path.join(get_base_dir(), "binaries", "Logs")
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    return log_dir

def setup_logging():
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, 'TMDB.log')
    if not isinstance(sys.stdout, DualLogger):
        sys.stdout = DualLogger(log_file, sys.stdout)
    print(f"\n\n{'='*60}")
    print(f"📄 PLUGIN LOG STARTED: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

def load_config():
    global CONFIG
    config_path = os.path.join(get_base_dir(), 'config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
        
        required = {
            "movies_dir": "Movie",
            "tv_dir": "TV",
            "unsorted_dir": "Unsorted",
            "ffmpeg_path": "",
            "ffprobe_path": "",
            "mkvpropedit_path": "",
            "tmdb_api_key": "",
            "fanart_api_key": "",
            "omdb_api_key": ""
        }
        
        updated = False
        for key, default in required.items():
            if key not in CONFIG:
                CONFIG[key] = default
                updated = True
                
        if updated:
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(CONFIG, f, indent=4)
                print(f"🔌 [010_tmdb] Updated config.json with missing fields.")
            except Exception as e:
                print(f"🔌 [010_tmdb] Error writing config.json: {e}")

        if not CONFIG.get('tmdb_api_key'):
            msg = "🔌 [010_tmdb] Critical: 'tmdb_api_key' is missing in config.json."
            print(msg)
            try:
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("TMDB Plugin Configuration", msg)
                root.destroy()
            except: pass
    except Exception as e:
        print(f"🔌 [010_tmdb] Warning: Could not load config.json: {e}")

def check_dependencies():
    """Verify presence of ffmpeg, ffprobe, and mkvpropedit."""
    global FFMPEG_PATH, FFPROBE_PATH, MKVPROPEDIT_PATH
    
    base_dir = get_base_dir()
    is_win = os.name == 'nt'
    
    def find_exe(name, config_key=None):
        if config_key and CONFIG.get(config_key):
            conf_path = CONFIG[config_key]
            if os.path.isabs(conf_path) and os.path.exists(conf_path):
                return conf_path
            abs_conf = os.path.join(base_dir, conf_path)
            if os.path.exists(abs_conf):
                return abs_conf

        exts = [".exe"] if is_win else [""]
        search_names = [name]
        if name == "ffmpeg" and is_win:
            search_names.append("ffmpeg_libfdk_aac_1")
            
        search_dirs = [os.path.join(base_dir, "binaries"), base_dir]
        for d in search_dirs:
            if not os.path.exists(d): continue
            for s_name in search_names:
                for ext in exts:
                    local_path = os.path.join(d, s_name + ext)
                    if os.path.exists(local_path):
                        return local_path
        
        system_path = shutil.which(name)
        if system_path:
            return system_path
            
        return None

    FFMPEG_PATH = find_exe("ffmpeg", "ffmpeg_path") or "ffmpeg"
    FFPROBE_PATH = find_exe("ffprobe", "ffprobe_path") or "ffprobe"
    
    found_mkv = find_exe("mkvpropedit", "mkvpropedit_path")
    if found_mkv:
        MKVPROPEDIT_PATH = found_mkv
        return True
    
    print(f"\n🔌 [010_tmdb] mkvpropedit is missing but required for MKV tagging.")
    if os.name == 'nt':
        print("   👉 Extract 'mkvpropedit.exe' from MKVToolNix into the program root.")
        print("   🔗 https://mkvtoolnix.download/downloads.html#windows")
    else:
        print("   👉 Run: sudo apt update && sudo apt install -y mkvtoolnix")
    
    MKVPROPEDIT_PATH = None
    return False

# ==============================================================================
# 🔍 FILENAME PARSING LOGIC (FIXED)
# ==============================================================================

# FIXED: Properly handles years between title and season, and multi-word titles
FILENAME_REGEX = re.compile(
    r"""
    ^
    (?P<title>.+?)                  
    [.\s_-]*                          # Flexible separators
    (?:\((?P<year>(?:19|20)\d{2})\))? # Optional year in parentheses (2022)
    [.\s_-]*                          # More flexible spacing
    [Ss](?:eason)?\s*(?P<season>\d+)  # Season
    [.\s_-]*                          # Flexible separators
    [Ee](?:pisode)?\s*(?P<episode>\d+) # Episode
    .*$ 
    | 
    ^
    (?P<movie_title>.+?) 
    [.\s_\(-]+ 
    (?P<movie_year>(?:19|20)\d{2}) 
    (?:[.\s_\)-]|$).* """,
    re.VERBOSE | re.IGNORECASE
)

def parse_filename(filename):
    """Parse filename to extract media info. FIXED to handle years and multi-word titles."""
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]
    
    # FIXED: Also strip parentheses so regex can match them as separate tokens if needed,
    # but we keep them for year extraction via regex groups
    name_cleaned = re.sub(r'[._\[\]]', ' ', name_no_ext).strip()

    # Clean standard plugin suffixes to improve TMDB search accuracy
    for suffix in ["Sanitized", "DualAudio", "Normalized"]:
        name_cleaned = re.sub(rf'\b{suffix}\b', '', name_cleaned, flags=re.IGNORECASE)
    name_cleaned = re.sub(r'\s+', ' ', name_cleaned).strip()
    
    match = FILENAME_REGEX.search(name_cleaned)
    if not match: 
        return None

    data = match.groupdict()
    
    # TV SHOW PARSING
    if data.get('season') and data.get('episode'):
        raw_title = data['title'].strip()
        
        # FIXED: Use year captured between title and season (e.g., "Show (2022) S01E01")
        year = int(data['year']) if data.get('year') else None
        
        # Clean title (removes trailing years, country codes)
        search_title, extracted_year = _clean_title_and_year_smart(raw_title)
        
        # If we didn't get year from middle, use the one from end of title
        if not year and extracted_year:
            year = extracted_year
            
        return {
            'type': 'tv', 
            'search_title': search_title, 
            'season_num': int(data['season']), 
            'episode_num': int(data['episode']),
            'year': year
        }

    # MOVIE PARSING
    elif data.get('movie_title'):
        raw_title = data['movie_title'].strip()
        year = int(data.get('movie_year') or 0)
        search_title = re.sub(r'[\s._\(]+$', '', raw_title).strip()
        return {
            'type': 'movie', 
            'search_title': search_title, 
            'year': year
        }
    return None

def _clean_title_and_year_smart(title_str):
    """Extract year from title and clean it."""
    search_title = title_str
    found_year = None
    
    # Look for year in parentheses at end: Title (2022)
    paren_year_match = re.search(r'\((19|20)\d{2}\)$', search_title)
    if paren_year_match:
        year_str = paren_year_match.group(0).strip('()')
        found_year = int(year_str)
        search_title = search_title[:paren_year_match.start()].strip()
        return search_title, found_year

    # Look for standalone year at end: Title 2022
    trailing_year_match = re.search(r'\s(19|20)\d{2}$', search_title)
    if trailing_year_match:
        found_year = int(trailing_year_match.group(0).strip())
        search_title = search_title[:trailing_year_match.start()].strip()
        return search_title, found_year
    
    # Remove country codes like (US), (UK) but keep the text
    search_title = re.sub(r'\([A-Z]{2}\)', '', search_title).strip()
    
    return search_title, found_year

# ==============================================================================
# 🔍 TMDB API LOGIC
# ==============================================================================

TMDB_API_BASE = "https://api.themoviedb.org/3"

def fetch_tmdb_config():
    global TMDB_IMAGE_BASE
    api_key = CONFIG.get('tmdb_api_key')
    if not api_key:
        return False
    config_url = f"{TMDB_API_BASE}/configuration"
    try:
        response = requests.get(config_url, params={'api_key': api_key}, timeout=10)
        response.raise_for_status()
        TMDB_IMAGE_BASE = response.json()['images']['secure_base_url']
        return True
    except: 
        return False

def get_best_image_path(image_list, language='en'):
    if not image_list: 
        return None
    en_images = [img for img in image_list if img.get('iso_639_1') == language and img.get('file_path')]
    if en_images:
        en_images.sort(key=lambda x: x.get('vote_count', 0), reverse=True)
        return en_images[0]['file_path']
    all_images = [img for img in image_list if img.get('file_path')]
    if all_images:
        all_images.sort(key=lambda x: x.get('vote_count', 0), reverse=True)
        return all_images[0]['file_path']
    return None

def get_best_fanart_asset(asset_list, name):
    if not asset_list: 
        return None, None
    asset_list.sort(key=lambda x: int(x.get('likes', 0)), reverse=True)
    url = asset_list[0]['url']
    return url, os.path.splitext(url)[1]

def verify_season_exists(show_id, season_num):
    """NEW: Verify the TV show actually has the requested season before selecting it."""
    api_key = CONFIG.get('tmdb_api_key')
    if not api_key:
        return True  # Fail open if no key
        
    url = f"{TMDB_API_BASE}/tv/{show_id}"
    try:
        resp = requests.get(url, params={
            'api_key': api_key, 
            'append_to_response': 'seasons'
        }, timeout=10).json()
        
        if resp.get('success') == False:
            return False
            
        seasons = resp.get('seasons', [])
        for s in seasons:
            if s.get('season_number') == season_num:
                return True
        return False
    except Exception as e:
        print(f"   ⚠️ Error verifying season existence: {e}")
        return True  # Fail open on error to avoid blocking

def input_with_timeout(prompt, timeout=45):
    try:
        import capture_m3u8
        if hasattr(capture_m3u8, 'get_user_input'):
            return capture_m3u8.get_user_input(prompt)
    except: 
        pass
    
    print(prompt, end='', flush=True)
    start_time = time.time()
    input_str = ""
    
    if os.name == 'nt': 
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getche().decode('utf-8')
                if char in ('\r', '\n'): 
                    print()
                    return input_str
                input_str += char
            if (time.time() - start_time) > timeout:
                return 's'
            time.sleep(0.1)
    else: 
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist: 
            return sys.stdin.readline().strip()
        else: 
            return 's'

def prompt_user_selection(results, media_type):
    if not results: 
        return None
    if len(results) == 1: 
        return results[0]

    print(f"\n🤔 **Multiple {media_type.upper()} results found!**")
    for i, res in enumerate(results[:8], 1):
        name = res.get('title') or res.get('name')
        date = res.get('release_date') or res.get('first_air_date', '????-??-??')
        year_str = date[:4] if date else '????'
        print(f"   {i}) {name} ({year_str})")
    print(f"   s) Skip / Move to **UNSORTED**")
    
    choice = input_with_timeout(f"\nSelection (1-{min(len(results), 8)} or 's'): ").lower()
    if choice.isdigit() and 1 <= int(choice) <= min(len(results), 8):
        return results[int(choice)-1]
    return None

def fetch_tmdb_metadata(parsed_data):
    api_key = CONFIG.get('tmdb_api_key')
    if not api_key: 
        print("🔌 [010_tmdb] Error: tmdb_api_key missing")
        return None
    
    endpoint = "tv" if parsed_data['type'] == 'tv' else "movie"
    url = f"{TMDB_API_BASE}/search/{endpoint}"
    params = {
        'api_key': api_key, 
        'query': parsed_data['search_title'],
        'include_adult': 'false'
    }
    
    # FIXED: Properly pass year parameters
    if parsed_data.get('year'):
        if parsed_data['type'] == 'tv': 
            params['first_air_date_year'] = parsed_data['year']
        else: 
            params['year'] = parsed_data['year']
        
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        results = resp.get('results', [])
        return results
    except Exception as e:
        print(f"🔌 [010_tmdb] API Error: {e}")
    return []

def fetch_tmdb_episode(tmdb_id, season, episode):
    api_key = CONFIG.get('tmdb_api_key')
    url = f"{TMDB_API_BASE}/tv/{tmdb_id}/season/{season}/episode/{episode}"
    try:
        return requests.get(url, params={'api_key': api_key}, timeout=10).json()
    except:
        return None

def fetch_omdb_data(title, year=None, media_type=None):
    if not CONFIG.get('omdb_api_key'): 
        return None
    params = {
        'apikey': CONFIG['omdb_api_key'], 
        't': title, 
        'plot': 'full',
        'r': 'json'
    }
    if year: 
        params['y'] = str(year)
    if media_type == 'movie': 
        params['type'] = 'movie'
    elif media_type == 'tv': 
        params['type'] = 'series'

    try:
        response = requests.get("http://www.omdbapi.com/", params=params, timeout=10)
        data = response.json()
        return data if data.get('Response') == 'True' else None
    except: 
        return None

def download_image(url, target_path):
    if not url: 
        return False
    try:
        r = requests.get(url, stream=True, timeout=15)
        if r.status_code == 200:
            with open(target_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except Exception as e:
        print(f"   ⚠️ Image download failed ({os.path.basename(target_path)}): {e}")
    return False

def fetch_fanart_assets(media_type, fanart_id):
    if not CONFIG.get('fanart_api_key') or not fanart_id: 
        return {}
    
    endpoint = "movies" if media_type == 'movie' else "tv"
    url = f"https://webservice.fanart.tv/v3/{endpoint}/{fanart_id}"
    try:
        resp = requests.get(url, params={'api_key': CONFIG['fanart_api_key']}, timeout=10).json()
        return resp if 'error' not in resp else {}
    except: 
        return {}

def create_tmdb_link(target_dir, media_type, tmdb_id):
    endpoint = "movie" if media_type == 'movie' else "tv"
    url = f"https://www.themoviedb.org/{endpoint}/{tmdb_id}"
    try:
        with open(os.path.join(target_dir, "tmdb.url.txt"), 'w', encoding='utf-8') as f:
            f.write(url)
    except:
        pass

# ==============================================================================
# 🎬 PROCESSING & ORGANIZATION
# ==============================================================================

def set_mkv_title(filepath, title):
    if not MKVPROPEDIT_PATH: 
        return
    command = [MKVPROPEDIT_PATH, filepath, '--set', f"title={title}"]
    print(f"\n🎬 Tagging MKV: {title}")
    
    # Hide window on Windows
    creation_flags = 0
    if os.name == 'nt':
        creation_flags = 0x08000000 # CREATE_NO_WINDOW

    try:
        subprocess.run(command, capture_output=True, text=True, check=True, creationflags=creation_flags)
    except Exception as e: 
        print(f"❌ Error during mkvpropedit: {e}")

def extract_video_thumb(video_path, output_path, percent=0.40):
    print(f"   --> 🎞️  Extracting frame {int(percent*100)}% ...")
    
    # Hide window on Windows
    creation_flags = 0
    if os.name == 'nt':
        creation_flags = 0x08000000 # CREATE_NO_WINDOW
    
    try:
        # Get duration
        probe_cmd = [
            FFPROBE_PATH, 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=creation_flags)
        duration_str = result.stdout.strip()
        timestamp = float(duration_str) * percent if duration_str else 60
        
        # Extract frame
        ff_cmd = [
            FFMPEG_PATH,
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "2",
            output_path,
            "-y",
            "-loglevel", "error"
        ]
        
        process = subprocess.Popen(
            ff_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags
        )
        
        stdout, _ = process.communicate()
        
        if process.returncode == 0:
            return True
        else:
            if stdout:
                print(f"      FFmpeg: {stdout.strip()}")
            return False
                
    except Exception as e:
        print(f"   --> ❌ FFmpeg Error: {e}")
        return False

def fetch_and_download_all_movie_assets(movie_id, media_dir, media_filepath=None):
    if not TMDB_IMAGE_BASE:
        fetch_tmdb_config()
        
    tmdb_images_url = f"{TMDB_API_BASE}/movie/{movie_id}/images"
    fanart_data = fetch_fanart_assets('movie', movie_id)
    
    try:
        tmdb_image_data = requests.get(
            tmdb_images_url, 
            params={'api_key': CONFIG.get('tmdb_api_key')}, 
            timeout=10
        ).json()
    except: 
        tmdb_image_data = {}
        
    print("\n🖼️ Starting Movie Asset Download...")
    ASSETS = [
        ('ClearLogo', 'hdmovielogo', 'logo', '.png'), 
        ('ClearArt', 'movieart', 'clearart', '.png'), 
        ('Disc', 'moviedisc', 'discart', '.png'), 
        ('Poster', 'posters', 'poster', '.jpg'), 
        ('Fanart', 'backdrops', 'fanart', '.jpg')
    ]
    
    for name, source_key, filename_stem, fallback_ext in ASSETS:
        url = None
        target_path = os.path.join(media_dir, f"{filename_stem}{fallback_ext}")
        
        if fanart_data and source_key in fanart_data:
            url, ext = get_best_fanart_asset(fanart_data[source_key], name)
            if url: 
                target_path = os.path.join(media_dir, f"{filename_stem}{ext}")
        elif tmdb_image_data and source_key in tmdb_image_data:
            path = get_best_image_path(tmdb_image_data[source_key])
            if path: 
                size = POSTER_SIZE if source_key == 'posters' else BACKDROP_SIZE
                url = f"{TMDB_IMAGE_BASE}{size}{path}"
        
        if url:
            if download_image(url, target_path):
                if filename_stem == 'poster': 
                    shutil.copyfile(target_path, os.path.join(media_dir, 'folder.jpg'))
        else: 
            print(f"   --> ℹ️ {name} not found.")

    # Generate fallback fanart from video if missing
    fanart_fallback = os.path.join(media_dir, 'fanart.jpg')
    if not os.path.exists(fanart_fallback) and media_filepath:
        extract_video_thumb(media_filepath, fanart_fallback, percent=0.19)
        
    # Generate backdrop slideshow
    if media_filepath:
        print("   --> 🎞️ Generating slideshow backdrops...")
        for i, pct in enumerate([0.25, 0.35, 0.40, 0.50, 0.60], 1):
            extract_video_thumb(
                media_filepath, 
                os.path.join(media_dir, f"backdrop-{i}.jpg"), 
                percent=pct
            )

def fetch_and_download_all_show_assets(show_id, show_dir, show_info):
    if not TMDB_IMAGE_BASE:
        fetch_tmdb_config()
        
    tmdb_images_url = f"{TMDB_API_BASE}/tv/{show_id}/images"
    fanart_data = fetch_fanart_assets('tv', show_id)
    
    try:
        tmdb_image_data = requests.get(
            tmdb_images_url, 
            params={'api_key': CONFIG.get('tmdb_api_key')}, 
            timeout=10
        ).json()
    except: 
        tmdb_image_data = {}
        
    print("\n🖼️ Starting TV Show Asset Download...")
    ASSETS = [
        ('ClearLogo', 'hdclearart', 'logo', '.png'), 
        ('ClearArt', 'clearart', 'clearart', '.png'),
        ('Poster', 'posters', 'poster', '.jpg'), 
        ('Fanart', 'backdrops', 'fanart', '.jpg')
    ]
    
    for name, source_key, filename_stem, fallback_ext in ASSETS:
        url = None
        target_path = os.path.join(show_dir, f"{filename_stem}{fallback_ext}")
        
        if fanart_data and source_key in fanart_data:
            url, ext = get_best_fanart_asset(fanart_data[source_key], name)
            if url: 
                target_path = os.path.join(show_dir, f"{filename_stem}{ext}")
        elif tmdb_image_data and source_key in tmdb_image_data:
            path = get_best_image_path(tmdb_image_data[source_key])
            if path: 
                size = POSTER_SIZE if source_key == 'posters' else BACKDROP_SIZE
                url = f"{TMDB_IMAGE_BASE}{size}{path}"
        
        if url:
            if download_image(url, target_path):
                if filename_stem == 'poster': 
                    shutil.copyfile(target_path, os.path.join(show_dir, 'folder.jpg'))
        else: 
            print(f"   --> ℹ️ {name} not found.")
            
    write_show_nfo(show_info, show_dir)

def handle_asset_downloads(parsed_data, tmdb_info, media_filepath, show_id=None, show_info=None, omdb_info=None): 
    media_dir = os.path.dirname(media_filepath)
    filename_stem = os.path.splitext(os.path.basename(media_filepath))[0]
    
    if parsed_data['type'] == 'tv':
        show_dir = os.path.dirname(media_dir)
        thumb_path = os.path.join(media_dir, f"{filename_stem}-thumb.jpg")
        if not os.path.exists(thumb_path): 
            extract_video_thumb(media_filepath, thumb_path, percent=0.15)
        write_episode_nfo(media_filepath, tmdb_info, show_id)
        if show_info and show_id: 
            fetch_and_download_all_show_assets(show_id, show_dir, show_info) 
        if show_id: 
            create_tmdb_link(show_dir, 'tv', show_id)
            
    elif parsed_data['type'] == 'movie':
        movie_id = tmdb_info.get('id')
        if movie_id: 
            fetch_and_download_all_movie_assets(movie_id, media_dir, media_filepath)
        write_movie_nfo(media_filepath, tmdb_info, omdb_info=omdb_info)
        if movie_id: 
            create_tmdb_link(media_dir, 'movie', movie_id)

# ==============================================================================
# 📝 NFO GENERATION
# ==============================================================================

def write_episode_nfo(media_filepath, episode_info, show_id):
    media_dir = os.path.dirname(media_filepath)
    filename_stem = os.path.splitext(os.path.basename(media_filepath))[0]
    nfo_path = os.path.join(media_dir, f"{filename_stem}.nfo")
    
    root = Element('episodedetails')
    SubElement(root, 'title').text = episode_info.get('name', filename_stem)
    SubElement(root, 'showtitle').text = episode_info.get('show_name', '')
    SubElement(root, 'season').text = str(episode_info.get('season_number', 0))
    SubElement(root, 'episode').text = str(episode_info.get('episode_number', 0))
    SubElement(root, 'plot').text = episode_info.get('overview', '')
    SubElement(root, 'premiered').text = episode_info.get('air_date', '0000-00-00')
    SubElement(root, 'thumb').text = f"{filename_stem}-thumb.jpg"
    
    crew = episode_info.get('crew', [])
    director = next((c['name'] for c in crew if c['job'] == 'Director'), None)
    writer = next((c['name'] for c in crew if c['job'] in ['Writer', 'Screenplay']), None)
    
    if director: 
        SubElement(root, 'director').text = director
    if writer: 
        SubElement(root, 'credits').text = writer
    if episode_info.get('id'): 
        SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(episode_info['id'])
        
    for actor in episode_info.get('guest_stars', [])[:10]:
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        if actor.get('profile_path'): 
            SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
            
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: 
        f.write(pretty_xml)

def write_movie_nfo(media_filepath, movie_info, omdb_info=None): 
    media_dir = os.path.dirname(media_filepath)
    stem = os.path.splitext(os.path.basename(media_filepath))[0]
    nfo_path = os.path.join(media_dir, f"{stem}.nfo")
    
    root = Element('movie')
    if movie_info.get('id'): 
        SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(movie_info['id'])
        
    imdb_id = (omdb_info or {}).get('imdbID') or movie_info.get('external_ids', {}).get('imdb_id')
    if imdb_id: 
        SubElement(root, 'uniqueid', type='imdb').text = imdb_id
        
    SubElement(root, 'title').text = movie_info.get('title', stem)
    SubElement(root, 'originaltitle').text = movie_info.get('original_title', movie_info.get('title'))
    
    rel = movie_info.get('release_date', '0000-00-00')
    SubElement(root, 'sorttitle').text = f"{movie_info.get('title')} :: {rel}"
    SubElement(root, 'year').text = rel[:4]
    SubElement(root, 'premiered').text = rel
    SubElement(root, 'plot').text = movie_info.get('overview', 'No plot.')
    
    # MPAA Rating
    mpaa = ''
    try:
        release_dates = movie_info.get('release_dates', {}).get('results', [])
        us_release = next((r for r in release_dates if r['iso_3166_1'] == 'US'), None)
        if us_release and us_release['release_dates']:
            certifications = [rd.get('certification') for rd in us_release['release_dates'] if rd.get('certification')]
            if certifications: 
                mpaa = certifications[0]
    except: 
        pass
    if mpaa: 
        SubElement(root, 'mpaa').text = mpaa

    if movie_info.get('runtime'): 
        SubElement(root, 'runtime').text = str(movie_info['runtime'])
        
    ratings = SubElement(root, 'ratings')
    t_rat = SubElement(ratings, 'rating', default='true', max='10', name='tmdb')
    SubElement(t_rat, 'value').text = str(round(movie_info.get('vote_average', 0), 1))
    SubElement(t_rat, 'votes').text = str(movie_info.get('vote_count', 0))
    
    if omdb_info and omdb_info.get('imdbRating') != 'N/A':
        i_rat = SubElement(ratings, 'rating', max='10', name='imdb')
        SubElement(i_rat, 'value').text = omdb_info['imdbRating']
        SubElement(i_rat, 'votes').text = omdb_info.get('imdbVotes', '0').replace(',', '')
        
    for g in movie_info.get('genres', []): 
        SubElement(root, 'genre').text = g['name']
    for k in movie_info.get('keywords', {}).get('keywords', []): 
        SubElement(root, 'tag').text = k['name']
    for c in movie_info.get('production_countries', []): 
        SubElement(root, 'country').text = c['iso_3166_1']
        
    crew = movie_info.get('credits', {}).get('crew', [])
    director = next((c['name'] for c in crew if c['job'] == 'Director'), None)
    if director: 
        SubElement(root, 'director').text = director
        
    for order, actor in enumerate(movie_info.get('credits', {}).get('cast', [])[:25]): 
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        SubElement(actor_el, 'order').text = str(order)
        if actor.get('profile_path'): 
            SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
            
    SubElement(root, 'thumb').text = 'poster.jpg' 
    SubElement(root, 'fanart').text = 'fanart.jpg'
    
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: 
        f.write(pretty_xml)

def write_show_nfo(show_info, show_dir):
    nfo_path = os.path.join(show_dir, 'tvshow.nfo')
    root = Element('tvshow')
    
    if show_info.get('id'): 
        SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(show_info['id'])
        
    imdb = show_info.get('external_ids', {}).get('imdb_id')
    if imdb: 
        SubElement(root, 'uniqueid', type='imdb').text = imdb
        
    SubElement(root, 'title').text = show_info.get('name', '')
    SubElement(root, 'plot').text = show_info.get('overview', 'No plot.')
    
    air = show_info.get('first_air_date', '0000-00-00')
    SubElement(root, 'premiered').text = air
    SubElement(root, 'year').text = air[:4]
    
    for g in show_info.get('genres', []): 
        SubElement(root, 'genre').text = g['name']
    for k in show_info.get('keywords', {}).get('results', []): 
        SubElement(root, 'tag').text = k['name']
        
    for actor in show_info.get('credits', {}).get('cast', [])[:25]: 
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        if actor.get('profile_path'): 
            SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
            
    SubElement(root, 'thumb').text = 'poster.jpg' 
    SubElement(root, 'fanart').text = 'fanart.jpg'
    
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: 
        f.write(pretty_xml)

# ==============================================================================
# 🚀 MAIN ENTRY POINT (FIXED)
# ==============================================================================

def get_tmdb_title(parsed_data, original_filepath):
    """Main logic to identify, verify season, and organize media."""
    api_key = CONFIG.get('tmdb_api_key')
    basename = os.path.basename(original_filepath)
    
    # Search TMDB
    results = fetch_tmdb_metadata(parsed_data)
    if not results:
        print(f"⚠️ No TMDB results found for: {parsed_data['search_title']}")
        return None
        
    # NEW: Filter TV results by season existence
    if parsed_data['type'] == 'tv':
        valid_results = []
        for r in results[:5]:  # Check top 5 results
            show_id = r['id']
            show_name = r.get('name', 'Unknown')
            
            if verify_season_exists(show_id, parsed_data['season_num']):
                valid_results.append(r)
            else:
                print(f"⛔ Rejected: {show_name} (Does not have Season {parsed_data['season_num']})")
        
        if valid_results:
            results = valid_results
        elif results:
            print(f"⚠️ Warning: None of the top results have Season {parsed_data['season_num']}")
            # Continue with original results but user will have to pick carefully
    
    selected = None
    
    # Smart Matching Logic
    if parsed_data['type'] == 'tv' and len(results) > 1:
        # Try to match by episode name in filename
        for candidate in results[:3]:
            try:
                ep_url = f"{TMDB_API_BASE}/tv/{candidate['id']}/season/{parsed_data['season_num']}/episode/{parsed_data['episode_num']}"
                ep_resp = requests.get(
                    ep_url, 
                    params={'api_key': api_key}, 
                    timeout=5
                ).json()
                ep_name = ep_resp.get('name', '').lower()
                if ep_name and ep_name in basename.lower().replace('_', ' '):
                    print(f"\n⚡ Smart Match by Episode Name: {candidate.get('name')}")
                    selected = candidate
                    break
            except: 
                continue

    # Year Prioritization
    if not selected and len(results) > 1 and parsed_data.get('year'):
        for r in results:
            date = r.get('first_air_date' if parsed_data['type'] == 'tv' else 'release_date', '')
            if date.startswith(str(parsed_data['year'])):
                print(f"\n⚡ Year Priority Match: {r.get('name') or r.get('title')} ({date[:4]})")
                selected = r
                break

    # FIXED: Strict Exact Match (prevent "Fire" matching "Fire Country")
    if not selected:
        first = results[0]
        first_name = first.get('name') or first.get('title', '')
        search_lower = parsed_data['search_title'].lower().strip()
        first_lower = first_name.lower().strip()
        
        # Exact match OR result starts with search term followed by space/end
        if first_lower == search_lower:
            print(f"\n⚡ Exact Match: {first_name}")
            selected = first
        elif len(results) == 1:
            print(f"\n⚡ Single Result: {first_name}")
            selected = first

    if not selected: 
        selected = prompt_user_selection(results, parsed_data['type'])
    if not selected: 
        return None

    # Process TV Show
    if parsed_data['type'] == 'tv':
        s_id = selected['id']
        s_num, e_num = parsed_data['season_num'], parsed_data['episode_num']
        
        # Fetch detailed info
        show_info = requests.get(
            f"{TMDB_API_BASE}/tv/{s_id}", 
            params={
                'api_key': api_key, 
                'append_to_response': 'credits,external_ids,keywords'
            },
            timeout=10
        ).json()
        
        ep_info = requests.get(
            f"{TMDB_API_BASE}/tv/{s_id}/season/{s_num}/episode/{e_num}", 
            params={'api_key': api_key},
            timeout=10
        ).json()
        
        if 'success' in ep_info and not ep_info['success']:
            print(f"❌ Episode S{s_num:02d}E{e_num:02d} not found in API")
            return None
            
        ep_info['show_name'] = show_info['name']
        
        title, yr = show_info['name'], show_info.get('first_air_date', '0000')[:4]
        safe_t = re.sub(r'[\\/:*?"<>|]', '_', title)
        
        target_dir = os.path.join(
            str(CONFIG.get('tv_dir') or os.path.join(get_base_dir(), 'TV')), 
            f"{safe_t} ({yr})", 
            f"Season {s_num:02d}"
        )
        
        ep_name = re.sub(r'[\\/:*?"<>|]', '_', ep_info.get('name', 'Unknown'))
        base_fn = f"{safe_t} ({yr}) - S{s_num:02d}E{e_num:02d} - {ep_name}"
        
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(original_filepath)[1]
        target_path = os.path.join(target_dir, f"{base_fn}{ext}")
        
        if os.path.exists(target_path):
            date_str = datetime.datetime.now().strftime('%m.%d.%Y')
            target_path = os.path.join(target_dir, f"{base_fn} - {date_str}{ext}")
            print(f"   --> ⚠️ File exists! Adding date suffix.")
        
        print(f"   🚚 Moving to: {target_path}")
        shutil.move(original_filepath, target_path)
        
        final_title = f"{title} ({yr}) - S{s_num:02d}E{e_num:02d} - {ep_info.get('name', 'Unknown')}"
        set_mkv_title(target_path, final_title)
        handle_asset_downloads(parsed_data, ep_info, target_path, show_id=s_id, show_info=show_info)
        return target_path

    # Process Movie
    elif parsed_data['type'] == 'movie':
        movie_id = selected['id']
        m_info = requests.get(
            f"{TMDB_API_BASE}/movie/{movie_id}", 
            params={
                'api_key': api_key, 
                'append_to_response': 'credits,external_ids,release_dates,keywords'
            },
            timeout=10
        ).json()
        
        omdb = fetch_omdb_data(m_info['title'], m_info.get('release_date', '0000')[:4], 'movie')

        movie_title, movie_year = m_info['title'], m_info.get('release_date', '0000')[:4]
        
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', movie_title)
        target_dir = os.path.join(
            str(CONFIG.get('movies_dir') or os.path.join(get_base_dir(), 'Movie')), 
            f"{safe_title} ({movie_year})"
        )
        base_filename = f"{safe_title} ({movie_year})"
        
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(original_filepath)[1]
        target_path = os.path.join(target_dir, f"{base_filename}{ext}")
        
        if os.path.exists(target_path):
            date_str = datetime.datetime.now().strftime("%m.%d.%Y")
            new_filename = f"{base_filename} - {date_str}{ext}"
            target_path = os.path.join(target_dir, new_filename)
            print(f"   --> ⚠️ File exists! Renaming to: {new_filename}")
        
        print(f"   🚚 Moving to: {target_path}")
        shutil.move(original_filepath, target_path)
        
        final_title = f"{movie_title} ({movie_year})"
        set_mkv_title(target_path, final_title)
        handle_asset_downloads(parsed_data, m_info, target_path, omdb_info=omdb)
        return target_path

    return None

def process(file_path):
    load_config()
    setup_logging()
    
    if not CONFIG.get('tmdb_api_key'): 
        return file_path
        
    check_dependencies()
    fetch_tmdb_config()
    
    print(f"--- 🔍 Analyzing: {os.path.basename(file_path)} ---")
    
    parsed = parse_filename(file_path)
    if not parsed: 
        print(f"⚠️ Could not parse filename format")
        return file_path
    
    print(f"   Parsed: {parsed['search_title']} ({parsed.get('year') or 'Unknown Year'}) "
          f"S{parsed.get('season_num', 0):02d}E{parsed.get('episode_num', 0):02d}")
    
    final_path = get_tmdb_title(parsed, file_path)
    
    if not final_path:
        print("⚠️ Identification failed or skipped.")
        unsorted = CONFIG.get('unsorted_dir')
        if unsorted:
            os.makedirs(unsorted, exist_ok=True)
            target = os.path.join(unsorted, os.path.basename(file_path))
            # Avoid collision in unsorted
            if os.path.exists(target):
                base, ext = os.path.splitext(target)
                target = f"{base}_{int(time.time())}{ext}"
            print(f"   🚚 Moving to Unsorted: {target}")
            shutil.move(file_path, target)
            return target
        return file_path
        
    return final_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1])
    else:
        load_config()
        print(f"🔌 [010_tmdb] Configuration check complete.")