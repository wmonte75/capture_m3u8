import os
import sys
import re
import subprocess
import json
import requests
import time
import shutil
import datetime
import difflib
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
    # The plugin is in root/plugins/010_tmdb.py, so we go up one level
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Global Config
CONFIG = {}
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"
MKVPROPEDIT_PATH = None
TMDB_IMAGE_BASE = None
POSTER_SIZE = 'w500'
BACKDROP_SIZE = 'w1280'

# Standalone Logging (Mirroring tmdb_new.py)
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

def setup_logging():
    base_dir = get_base_dir()
    log_file = os.path.join(base_dir, 'TMDB.log')
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
        
        # Ensure required keys exist (Auto-update config.json)
        required = {
            "movies_dir": "Movie",
            "tv_dir": "TV",
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
                import capture_m3u8
                capture_m3u8.save_config(CONFIG)
                print(f"🔌 [010_tmdb] Updated config.json with missing fields (safely).")
            except Exception as e:
                print(f"🔌 [010_tmdb] Error writing config.json: {e}")

        # Validate critical key for operation
        if not CONFIG.get('tmdb_api_key'):
            msg = "🔌 [010_tmdb] Critical: 'tmdb_api_key' is missing in config.json.\n\nPlease refer to 'plugins/TMDB_README.md' for setup instructions."
            print(msg)
            try:
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("TMDB Plugin Configuration", msg)
                root.destroy()
            except: pass
    except Exception as e:
        print(f"🔌 [010_tmdb] Warning: Could not load config.json: {e}")

def check_dependencies():
    """Verify presence of ffmpeg, ffprobe, and mkvpropedit, checking root folder first."""
    global FFMPEG_PATH, FFPROBE_PATH, MKVPROPEDIT_PATH
    
    base_dir = get_base_dir()
    is_win = os.name == 'nt'
    
    # helper to find executable
    def find_exe(name, config_key=None):
        # 1. Check config
        if config_key and CONFIG.get(config_key):
            conf_path = CONFIG[config_key]
            if os.path.isabs(conf_path) and os.path.exists(conf_path):
                return conf_path
            # Relative to base
            abs_conf = os.path.join(base_dir, conf_path)
            if os.path.exists(abs_conf):
                return abs_conf

        # 2. Check root folder
        exts = [".exe"] if is_win else [""]
        # Special case for the user's custom ffmpeg name seen in tmdb_new.py
        search_names = [name]
        if name == "ffmpeg" and is_win:
            search_names.append("ffmpeg_libfdk_aac_1")
            
        for s_name in search_names:
            for ext in exts:
                local_path = os.path.join(base_dir, s_name + ext)
                if os.path.exists(local_path):
                    return local_path
        
        # 3. Check system PATH
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
    
    # Missing mkvpropedit -> Instruction only
    print(f"\n🔌 [010_tmdb] mkvpropedit is missing but required for MKV tagging.")
    if os.name == 'nt':
        print("   👉 Note: For Windows, please extract 'mkvpropedit.exe' from MKVToolNix into the program root.")
        print("   🔗 Download: https://mkvtoolnix.download/downloads.html#windows")
    else:
        print("   👉 Note: On Linux, run: sudo apt update && sudo apt install -y mkvtoolnix")
    
    MKVPROPEDIT_PATH = None
    return False

# ==============================================================================
# 🔍 FILENAME PARSING LOGIC (Ported from tmdb_new.py)
# ==============================================================================

FILENAME_REGEX = re.compile(
    r"""
    ^
    (?P<title>.+?)                  
    [.\s_-]+                        
    (?:
        [S|s](?:eason)?\s*(?P<season>\d+) 
        [.\s_-]* [E|e|x](?:pisode)?\s*(?P<episode>\d+)
    )
    .*$ 
    | 
    ^
    (?P<movie_title>.+?) 
    [.\s_\(-]+ 
    (?P<year>(?:19|20)\d{2}) 
    (?:[.\s_\)-]|$).* """,
    re.VERBOSE | re.IGNORECASE
)

def parse_filename(filename):
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]
    # Clean common separators
    name_cleaned = re.sub(r'[._\[\]]', ' ', name_no_ext).strip()
    match = FILENAME_REGEX.search(name_cleaned)
    if not match: return None

    data = match.groupdict()
    
    # TV SHOW PARSING
    if data.get('season') and data.get('episode'):
        raw_title = data['title'].strip()
        search_title, found_year = _clean_title_and_year_smart(raw_title)
        return {
            'type': 'tv', 
            'search_title': search_title, 
            'season_num': int(data['season']), 
            'episode_num': int(data['episode']),
            'year': found_year
        }

    # MOVIE PARSING
    elif data.get('movie_title'):
        raw_title = data['movie_title'].strip()
        year = int(data.get('year') or 0)
        search_title = re.sub(r'[\s._\(]+$', '', raw_title).strip()
        return {
            'type': 'movie', 
            'search_title': search_title, 
            'year': year
        }
    return None

def _clean_title_and_year_smart(title_str):
    search_title = title_str
    found_year = None
    year_regex = r'\b(19|20)\d{2}\b'
    years = re.findall(year_regex, title_str)
    
    paren_year_match = re.search(r'\((19|20)\d{2}\)', title_str)
    if paren_year_match:
        found_year = int(paren_year_match.group(0)[1:-1])
        search_title = re.sub(r'\s*\((19|20)\d{2}\)\s*', ' ', title_str).strip()
        return search_title, found_year

    trailing_year_match = re.search(r'\s(19|20)\d{2}$', search_title)
    if trailing_year_match:
        found_year = int(trailing_year_match.group(0).strip())
        search_title = search_title[:trailing_year_match.start()].strip()
        return search_title, found_year

    search_title = re.sub(r'[\(\)\-:]+$', '', search_title).strip()
    return search_title, found_year

# ==============================================================================
# 🔍 TMDB API LOGIC
# ==============================================================================

TMDB_API_BASE = "https://api.themoviedb.org/3"

def fetch_tmdb_config():
    global TMDB_IMAGE_BASE
    api_key = CONFIG.get('tmdb_api_key')
    config_url = f"{TMDB_API_BASE}/configuration"
    try:
        response = requests.get(config_url, params={'api_key': api_key}, timeout=10)
        response.raise_for_status()
        TMDB_IMAGE_BASE = response.json()['images']['secure_base_url']
        return True
    except: return False

def get_best_image_path(image_list, language='en'):
    if not image_list: return None
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
    if not asset_list: return None, None
    # Sort by 'likes'
    asset_list.sort(key=lambda x: int(x.get('likes', 0)), reverse=True)
    url = asset_list[0]['url']
    return url, os.path.splitext(url)[1]

def input_with_timeout(prompt, timeout=45):
    # Check if we are running inside the main app (with IPC)
    try:
        import capture_m3u8
        if hasattr(capture_m3u8, 'get_user_input'):
            # The main app handles its own timeout/UI
            return capture_m3u8.get_user_input(prompt)
    except: pass
    
    # Standalone fallback (like tmdb_new.py)
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
        import select
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist: return sys.stdin.readline().strip()
        else: return 's'

def prompt_user_selection(results, media_type):
    if not results: return None
    if len(results) == 1: return results[0]

    print(f"\n🤔 **Multiple {media_type.upper()} results found!**")
    for i, res in enumerate(results[:8], 1):
        name = res.get('title') or res.get('name')
        date = res.get('release_date') or res.get('first_air_date', '????-??-??')
        print(f"   {i}) {name} ({date[:4]})")
    print(f"   s) Skip / Move to **UNSORTED**")
    
    choice = input_with_timeout(f"\nSelection (1-{min(len(results), 8)} or 's'): ").lower()
    if choice.isdigit() and 1 <= int(choice) <= min(len(results), 8):
        return results[int(choice)-1]
    return None

def fetch_tmdb_metadata(parsed_data):
    api_key = CONFIG.get('tmdb_api_key')
    if not api_key: 
        print("🔌 [010_tmdb] Error: tmdb_api_key missing in config.json")
        return None
    
    endpoint = "tv" if parsed_data['type'] == 'tv' else "movie"
    url = f"{TMDB_API_BASE}/search/{endpoint}"
    params = {'api_key': api_key, 'query': parsed_data['search_title']}
    if parsed_data.get('year'):
        if parsed_data['type'] == 'tv': params['first_air_date_year'] = parsed_data['year']
        else: params['year'] = parsed_data['year']
        
    try:
        resp = requests.get(url, params=params).json()
        results = resp.get('results', [])
        if results:
            res = results[0] # Pick first match
            tmdb_id = res['id']
            full_url = f"{TMDB_API_BASE}/{endpoint}/{tmdb_id}"
            params = {'api_key': api_key, 'append_to_response': 'credits,external_ids,release_dates,keywords'}
            return requests.get(full_url, params=params).json()
    except Exception as e:
        print(f"🔌 [010_tmdb] API Error: {e}")
    return None

def fetch_tmdb_episode(tmdb_id, season, episode):
    api_key = CONFIG.get('tmdb_api_key')
    url = f"{TMDB_API_BASE}/tv/{tmdb_id}/season/{season}/episode/{episode}"
    try:
        return requests.get(url, params={'api_key': api_key}).json()
    except:
        return None

def fetch_omdb_data(title, year=None, media_type=None, season=None, episode=None):
    if not CONFIG.get('omdb_api_key'): return None
    params = {'apikey': CONFIG['omdb_api_key'], 't': title, 'plot': 'full'}
    if year: params['y'] = str(year)
    if media_type == 'tv': params['type'] = 'series'
    
    if season and episode:
        params['Season'] = str(season)
        params['Episode'] = str(episode)
        params.pop('type', None) 

    try:
        response = requests.get("http://www.omdbapi.com/", params=params, timeout=10)
        data = response.json()
        return data if data.get('Response') == 'True' else None
    except: return None

def fetch_omdb_rating(imdb_id):
    """Fetches accurate IMDB rating and additional metadata from OMDB."""
    api_key = CONFIG.get('omdb_api_key')
    if not api_key or not imdb_id: return None
    url = "http://www.omdbapi.com/"
    try:
        data = requests.get(url, params={'apikey': api_key, 'i': imdb_id}, timeout=10).json()
        if data.get('Response') == 'True':
            return data
    except:
        pass
    return None

def download_image(url, target_path):
    """Downloads an image from a URL to a local path."""
    if not url: return False
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
    """Fetches high-quality logos and art from Fanart.tv. fanart_id is TMDB ID for movies, TVDB ID for TV."""
    if not CONFIG.get('fanart_api_key') or not fanart_id: return {}
    
    endpoint = "movies" if media_type == 'movie' else "tv"
    url = f"https://webservice.fanart.tv/v3/{endpoint}/{fanart_id}"
    try:
        resp = requests.get(url, params={'api_key': CONFIG['fanart_api_key']}, timeout=10).json()
        return resp if 'error' not in resp else {}
    except: return {}

def fetch_fanart_tv_data(tmdb_id, media_type): return fetch_fanart_assets(media_type, tmdb_id)

def create_tmdb_link(target_dir, media_type, tmdb_id):
    """Creates a shortcut text file to the TMDB page."""
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
    if not MKVPROPEDIT_PATH: return
    command = [MKVPROPEDIT_PATH, filepath, '--set', f"title={title}"]
    print(f"\n🎬 Tagging MKV: {title}")
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except Exception as e: print(f"❌ Error during mkvpropedit: {e}")

def extract_video_thumb(video_path, output_path, percent=0.40):
    print(f"   --> 🎞️  Extracting frame {int(percent*100)}% ...")
    ffmpeg_cmd = f'"{FFMPEG_PATH}"' if os.path.exists(FFMPEG_PATH) else 'ffmpeg'
    ffprobe_cmd = f'"{FFPROBE_PATH}"' if os.path.exists(FFPROBE_PATH) else 'ffprobe'

    try:
        probe_cmd = f'{ffprobe_cmd} -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{video_path}"'
        result = subprocess.run(probe_cmd, shell=True, capture_output=True, text=True)
        duration_str = result.stdout.strip()
        timestamp = float(duration_str) * percent if duration_str else 60
        try:
        # Construct the FFmpeg command
            ff_cmd = [
                ffmpeg_cmd.replace('"', ''),
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
                bufsize=1,
                universal_newlines=True
            )

            if process.stdout:
                for line in process.stdout:
                    print(f"      {line.strip()}", flush=True)
            
            process.wait()
            
            if process.returncode == 0:
                return True
            else:
                print(f"   --> ❌ FFmpeg failed with exit code {process.returncode}")
                return False
                
        except Exception as e:
            print(f"   --> ❌ FFmpeg Error: {e}")
            return False
    except Exception as e:
        print(f"   --> ❌ FFmpeg failed: {e}")
        return False

def fetch_and_download_all_movie_assets(movie_id, media_dir, media_filepath=None):
    tmdb_images_url = f"{TMDB_API_BASE}/movie/{movie_id}/images"
    fanart_data = fetch_fanart_tv_data(movie_id, 'movie')
    try:
        tmdb_image_data = requests.get(tmdb_images_url, params={'api_key': CONFIG['tmdb_api_key']}).json()
    except: tmdb_image_data = {}
        
    print("\n🖼️ Starting Movie Asset Download...")
    ASSETS = [('ClearLogo', 'hdmovielogo', 'logo', '.png'), ('ClearArt', 'movieart', 'clearart', '.png'), 
              ('Disc', 'moviedisc', 'discart', '.png'), ('Poster', 'posters', 'poster', '.jpg'), ('Fanart', 'backdrops', 'fanart', '.jpg')]
    
    for name, source_key, filename_stem, fallback_ext in ASSETS:
        url = None
        target_path = os.path.join(media_dir, f"{filename_stem}{fallback_ext}")
        if fanart_data and source_key in fanart_data:
            url, ext = get_best_fanart_asset(fanart_data[source_key], name)
            if url: target_path = os.path.join(media_dir, f"{filename_stem}{ext}")
        elif tmdb_image_data and source_key in tmdb_image_data:
            path = get_best_image_path(tmdb_image_data[source_key])
            if path: url = f"{TMDB_IMAGE_BASE}{POSTER_SIZE if source_key == 'posters' else BACKDROP_SIZE}{path}"
        if url:
            download_image(url, target_path)
            if filename_stem == 'poster': shutil.copyfile(target_path, os.path.join(media_dir, 'folder.jpg'))
        else: print(f"   --> ℹ️ {name} not found.")

    fanart_fallback = os.path.join(media_dir, 'fanart.jpg')
    if not os.path.exists(fanart_fallback) and media_filepath:
        extract_video_thumb(media_filepath, fanart_fallback, percent=0.19)
    if media_filepath:
        print("   --> 🎞️ Generating slideshow backdrops...")
        for i, pct in enumerate([0.25, 0.35, 0.40, 0.50, 0.60], 1):
            extract_video_thumb(media_filepath, os.path.join(media_dir, f"backdrop-{i}.jpg"), percent=pct)

def fetch_and_download_all_show_assets(show_id, show_dir, show_info):
    tmdb_images_url = f"{TMDB_API_BASE}/tv/{show_id}/images"
    fanart_data = fetch_fanart_tv_data(show_id, 'tv')
    try:
        tmdb_image_data = requests.get(tmdb_images_url, params={'api_key': CONFIG['tmdb_api_key']}).json()
    except: tmdb_image_data = {}
        
    print("\n🖼️ Starting TV Show Asset Download...")
    ASSETS = [('ClearLogo', 'hdclearart', 'logo', '.png'), ('ClearArt', 'clearart', 'clearart', '.png'),
              ('Poster', 'posters', 'poster', '.jpg'), ('Fanart', 'backdrops', 'fanart', '.jpg')]
    
    for name, source_key, filename_stem, fallback_ext in ASSETS:
        url = None
        target_path = os.path.join(show_dir, f"{filename_stem}{fallback_ext}")
        if fanart_data and source_key in fanart_data:
            url, ext = get_best_fanart_asset(fanart_data[source_key], name)
            if url: target_path = os.path.join(show_dir, f"{filename_stem}{ext}")
        elif tmdb_image_data and source_key in tmdb_image_data:
            path = get_best_image_path(tmdb_image_data[source_key])
            if path: url = f"{TMDB_IMAGE_BASE}{POSTER_SIZE if source_key == 'posters' else BACKDROP_SIZE}{path}"
        if url:
            download_image(url, target_path)
            if filename_stem == 'poster': shutil.copyfile(target_path, os.path.join(show_dir, 'folder.jpg'))
        else: print(f"   --> ℹ️ {name} not found.")
    write_show_nfo(show_info, show_dir)

def handle_asset_downloads(parsed_data, tmdb_info, media_filepath, show_id=None, show_info=None, omdb_info=None): 
    media_dir = os.path.dirname(media_filepath)
    filename_stem = os.path.splitext(os.path.basename(media_filepath))[0]
    
    if parsed_data['type'] == 'tv':
        show_dir = os.path.dirname(media_dir)
        thumb_path = os.path.join(media_dir, f"{filename_stem}-thumb.jpg")
        if not os.path.exists(thumb_path): extract_video_thumb(media_filepath, thumb_path, percent=0.15)
        write_episode_nfo(media_filepath, tmdb_info, show_id)
        if show_info and show_id: fetch_and_download_all_show_assets(show_id, show_dir, show_info) 
        if show_id: create_tmdb_link(show_dir, 'tv', show_id)
            
    elif parsed_data['type'] == 'movie':
        movie_id = tmdb_info.get('id')
        if movie_id: fetch_and_download_all_movie_assets(movie_id, media_dir, media_filepath)
        write_movie_nfo(media_filepath, tmdb_info, omdb_info=omdb_info)
        if movie_id: create_tmdb_link(media_dir, 'movie', movie_id)

# ==============================================================================
# 🚀 PLUGIN ENTRY POINT
# ==============================================================================

def write_episode_nfo(media_filepath, episode_info, show_id):
    media_dir = os.path.dirname(media_filepath)
    filename_stem = os.path.splitext(os.path.basename(media_filepath))[0]
    nfo_path = os.path.join(media_dir, f"{filename_stem}.nfo")
    root = Element('episodedetails')
    SubElement(root, 'title').text = episode_info.get('name', filename_stem)
    SubElement(root, 'showtitle').text = episode_info.get('show_name')
    SubElement(root, 'season').text = str(episode_info.get('season_number'))
    SubElement(root, 'episode').text = str(episode_info.get('episode_number'))
    SubElement(root, 'plot').text = episode_info.get('overview')
    SubElement(root, 'premiered').text = episode_info.get('air_date', '0000-00-00')
    SubElement(root, 'thumb').text = f"{filename_stem}-thumb.jpg"
    crew = episode_info.get('crew', [])
    director = next((c['name'] for c in crew if c['job'] == 'Director'), None)
    writer = next((c['name'] for c in crew if c['job'] in ['Writer', 'Screenplay']), None)
    if director: SubElement(root, 'director').text = director
    if writer: SubElement(root, 'credits').text = writer
    if episode_info.get('id'): SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(episode_info['id'])
    for actor in episode_info.get('guest_stars', [])[:10]:
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        if actor.get('profile_path'): SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: f.write(pretty_xml)

def write_movie_nfo(media_filepath, movie_info, omdb_info=None): 
    media_dir = os.path.dirname(media_filepath)
    stem = os.path.splitext(os.path.basename(media_filepath))[0]
    nfo_path = os.path.join(media_dir, f"{stem}.nfo")
    root = Element('movie')
    if movie_info.get('id'): SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(movie_info['id'])
    imdb_id = (omdb_info or {}).get('imdbID') or movie_info.get('external_ids', {}).get('imdb_id')
    if imdb_id: SubElement(root, 'uniqueid', type='imdb').text = imdb_id
    SubElement(root, 'title').text = movie_info.get('title', stem)
    SubElement(root, 'originaltitle').text = movie_info.get('original_title', movie_info.get('title'))
    rel = movie_info.get('release_date', '0000-00-00')
    # Absolute Parity: Full release date in sorttitle
    SubElement(root, 'sorttitle').text = f"{movie_info.get('title')} :: {rel}"
    SubElement(root, 'year').text = rel[:4]
    SubElement(root, 'premiered').text = rel
    SubElement(root, 'plot').text = movie_info.get('overview', 'No plot.')
    # Absolute Parity: MPAA / Certification Logic
    mpaa = ''
    try:
        release_dates = movie_info.get('release_dates', {}).get('results', [])
        us_release = next((r for r in release_dates if r['iso_3166_1'] == 'US'), None)
        if us_release and us_release['release_dates']:
            certifications = [rd.get('certification') for rd in us_release['release_dates'] if rd.get('certification')]
            if certifications: mpaa = certifications[0]
    except: pass
    if mpaa: SubElement(root, 'mpaa').text = mpaa

    if movie_info.get('runtime'): SubElement(root, 'runtime').text = str(movie_info['runtime'])
    ratings = SubElement(root, 'ratings')
    t_rat = SubElement(ratings, 'rating', default='true', max='10', name='tmdb')
    SubElement(t_rat, 'value').text = str(round(movie_info.get('vote_average', 0), 1))
    SubElement(t_rat, 'votes').text = str(movie_info.get('vote_count', 0))
    if omdb_info and omdb_info.get('imdbRating') != 'N/A':
        i_rat = SubElement(ratings, 'rating', max='10', name='imdb')
        SubElement(i_rat, 'value').text = omdb_info['imdbRating']
        SubElement(i_rat, 'votes').text = omdb_info.get('imdbVotes', '0').replace(',', '')
    for g in movie_info.get('genres', []): SubElement(root, 'genre').text = g['name']
    for k in movie_info.get('keywords', {}).get('keywords', []): SubElement(root, 'tag').text = k['name']
    for c in movie_info.get('production_countries', []): SubElement(root, 'country').text = c['iso_3166_1']
    crew = movie_info.get('credits', {}).get('crew', [])
    dir = next((c['name'] for c in crew if c['job'] == 'Director'), None)
    if dir: SubElement(root, 'director').text = dir
    for order, actor in enumerate(movie_info.get('credits', {}).get('cast', [])[:25]): 
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        SubElement(actor_el, 'order').text = str(order)
        if actor.get('profile_path'): SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
    SubElement(root, 'thumb').text = 'poster.jpg' 
    SubElement(root, 'fanart').text = 'fanart.jpg'
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: f.write(pretty_xml)

def write_show_nfo(show_info, show_dir):
    nfo_path = os.path.join(show_dir, 'tvshow.nfo')
    root = Element('tvshow')
    if show_info.get('id'): SubElement(root, 'uniqueid', type='tmdb', default='true').text = str(show_info['id'])
    imdb = show_info.get('external_ids', {}).get('imdb_id')
    if imdb: SubElement(root, 'uniqueid', type='imdb').text = imdb
    SubElement(root, 'title').text = show_info.get('name')
    SubElement(root, 'plot').text = show_info.get('overview', 'No plot.')
    air = show_info.get('first_air_date', '0000-00-00')
    SubElement(root, 'premiered').text = air
    SubElement(root, 'year').text = air[:4]
    for g in show_info.get('genres', []): SubElement(root, 'genre').text = g['name']
    for k in show_info.get('keywords', {}).get('results', []): SubElement(root, 'tag').text = k['name']
    for actor in show_info.get('credits', {}).get('cast', [])[:25]: 
        actor_el = SubElement(root, 'actor')
        SubElement(actor_el, 'name').text = actor.get('name')
        SubElement(actor_el, 'role').text = actor.get('character')
        if actor.get('profile_path'): SubElement(actor_el, 'thumb').text = f"{TMDB_IMAGE_BASE}original{actor['profile_path']}"
    SubElement(root, 'thumb').text = 'poster.jpg' 
    SubElement(root, 'fanart').text = 'fanart.jpg'
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f: f.write(pretty_xml)

def get_tmdb_title(parsed_data, original_filepath):
    api_key = CONFIG.get('tmdb_api_key')
    basename = os.path.basename(original_filepath)
    endpoint = "tv" if parsed_data['type'] == 'tv' else "movie"
    params = {'api_key': api_key, 'query': parsed_data['search_title']}
    if parsed_data.get('year'):
        if parsed_data['type'] == 'tv': params['first_air_date_year'] = parsed_data['year']
        else: params['year'] = parsed_data['year']
    
    try:
        results = requests.get(f"{TMDB_API_BASE}/search/{endpoint}", params=params).json().get('results', [])
    except: results = []
    if not results: return None

    # --- NEW: FileBot-style Smart Filtering ---
    filtered_results = []
    search_title_clean = parsed_data['search_title'].lower().strip()
    target_year = parsed_data.get('year')
    
    for r in results:
        name = (r.get('name') or r.get('title') or "").lower().strip()
        orig_name = (r.get('original_name') or r.get('original_title') or "").lower().strip()
        
        sim_name = difflib.SequenceMatcher(None, search_title_clean, name).ratio()
        sim_orig = difflib.SequenceMatcher(None, search_title_clean, orig_name).ratio()
        
        # Discard if similarity is below 80% and the title isn't a direct substring
        best_sim = max(sim_name, sim_orig)
        if best_sim < 0.8 and search_title_clean not in name and search_title_clean not in orig_name:
            continue
            
        # Strict Year Tolerance (±1 year)
        if target_year:
            date_str = r.get('first_air_date' if parsed_data['type'] == 'tv' else 'release_date', '')
            if date_str and len(date_str) >= 4:
                try:
                    cand_year = int(date_str[:4])
                    if abs(cand_year - target_year) > 1:
                        continue
                except: pass
        
        filtered_results.append(r)
        
    results = filtered_results
    if not results: return None
    # --- END SMART FILTERING ---

    # Smart Matching
    selected = None
    if parsed_data['type'] == 'tv' and len(results) > 1:
        for candidate in results[:3]:
            try:
                # Season Boundary Check: Reject shows that don't have this season
                show_details_url = f"{TMDB_API_BASE}/tv/{candidate['id']}"
                show_resp = requests.get(show_details_url, params={'api_key': api_key}).json()
                seasons = show_resp.get('seasons', [])
                if not any(s.get('season_number') == parsed_data['season_num'] for s in seasons):
                    print(f"   ⛔ Rejected: {candidate.get('name')} (Does not have Season {parsed_data['season_num']})")
                    continue
                
                ep_url = f"{TMDB_API_BASE}/tv/{candidate['id']}/season/{parsed_data['season_num']}/episode/{parsed_data['episode_num']}"
                ep_resp = requests.get(ep_url, params={'api_key': api_key}).json()
                
                # Empty Episode Name Bug Fix
                ep_name = ep_resp.get('name', '').strip()
                if ep_name and len(ep_name) > 2:
                    if ep_name.lower() in basename.lower().replace('_', ' '):
                        print(f"\n⚡ Smart Match: {candidate.get('name')}")
                        selected = candidate; break
            except: continue

    # Year Prioritization Intelligence
    if not selected and len(results) > 1 and parsed_data.get('year'):
        for r in results:
            date = r.get('first_air_date' if parsed_data['type'] == 'tv' else 'release_date', '')
            if date.startswith(str(parsed_data['year'])):
                print(f"\n⚡ Year Priority Match: {r.get('name') or r.get('title')} ({date[:4]})")
                selected = r
                break

    # Exact Title Match Intelligence
    if not selected:
        first = results[0]
        first_name = first.get('name') or first.get('title', '')
        if first_name.lower().strip() == parsed_data['search_title'].lower().strip() and len(results) == 1:
            print(f"\n⚡ Exact Match: {first_name}")
            selected = first

    if not selected: selected = prompt_user_selection(results, parsed_data['type'])
    if not selected: return None

    if parsed_data['type'] == 'tv':
        s_id = selected['id']
        s_num, e_num = parsed_data['season_num'], parsed_data['episode_num']
        show_info = requests.get(f"{TMDB_API_BASE}/tv/{s_id}", params={'api_key': api_key, 'append_to_response': 'credits,external_ids,keywords'}).json()
        ep_info = requests.get(f"{TMDB_API_BASE}/tv/{s_id}/season/{s_num}/episode/{e_num}", params={'api_key': api_key}).json()
        ep_info['show_name'] = show_info['name']
        title, yr = show_info['name'], show_info.get('first_air_date', '0000')[:4]
        safe_t = re.sub(r'[\\/:*?"<>|]', '_', title)
        target_dir = os.path.join(str(CONFIG.get('tv_dir') or os.path.join(get_base_dir(), 'TV')), f"{safe_t} ({yr})", f"Season {s_num:02d}")
        ep_name = re.sub(r'[\\/:*?"<>|]', '_', ep_info.get('name', 'Unknown'))
        base_fn = f"{safe_t} ({yr}) - S{s_num:02d}E{e_num:02d} - {ep_name}"
        
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(original_filepath)[1]
        target_path = os.path.join(target_dir, f"{base_fn}{ext}")
        if os.path.exists(target_path):
            target_path = os.path.join(target_dir, f"{base_fn} - {datetime.datetime.now().strftime('%m.%d.%Y')}{ext}")
        
        print(f"   🚚 Moving to: {target_path}")
        shutil.move(original_filepath, target_path)
        
        final_title = f"{title} ({yr}) - S{s_num:02d}E{e_num:02d} - {ep_info.get('name', 'Unknown')}"
        set_mkv_title(target_path, final_title)
        handle_asset_downloads(parsed_data, ep_info, target_path, show_id=s_id, show_info=show_info)
        return target_path

    elif parsed_data['type'] == 'movie':
        movie_id = selected['id']
        m_info = requests.get(f"{TMDB_API_BASE}/movie/{movie_id}", params={'api_key': api_key, 'append_to_response': 'credits,external_ids,release_dates,keywords'}).json()
        omdb = fetch_omdb_data(m_info['title'], m_info.get('release_date', '0000')[:4], 'movie')

        movie_title, movie_year = m_info['title'], m_info.get('release_date', '0000')[:4]
        
        # Absolute Parity: Sanitized folder/filename
        safe_title = re.sub(r'[\\/:*?\"<>|]', '_', movie_title)
        target_dir = os.path.join(str(CONFIG.get('movies_dir') or os.path.join(get_base_dir(), 'Movie')), f"{safe_title} ({movie_year})")
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
        
        # Absolute Parity: Use raw title (with possible quotes/colons) for internal MKV metadata
        final_title = f"{movie_title} ({movie_year})"
        set_mkv_title(target_path, final_title)
        
        handle_asset_downloads(parsed_data, m_info, target_path, omdb_info=omdb)
        return target_path

def process(file_path):
    load_config()
    setup_logging()
    if not CONFIG.get('tmdb_api_key'): return file_path
    check_dependencies()
    fetch_tmdb_config()
    print(f"--- 🔍 Analyzing: {os.path.basename(file_path)} ---")
    parsed = parse_filename(file_path)
    if not parsed: return file_path
    
    final_path = get_tmdb_title(parsed, file_path)
    if not final_path:
        print("⚠️ Identification failed or skipped.")
        unsorted = CONFIG.get('unsorted_dir')
        if unsorted:
            os.makedirs(unsorted, exist_ok=True)
            target = os.path.join(unsorted, os.path.basename(file_path))
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
