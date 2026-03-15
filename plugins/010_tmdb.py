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
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(CONFIG, f, indent=4)
                print(f"🔌 [010_tmdb] Updated config.json with missing fields.")
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
        
    # Missing mkvpropedit -> Prompt User (it's the only one we might prompt for if not found)
    msg = "mkvpropedit is missing but required for MKV tagging.\n\nWould you like to auto-install/download it?"
    
    try:
        # Try to show a GUI prompt
        root = tk.Tk()
        root.withdraw()
        response = messagebox.askyesno("Missing Dependency", msg)
        root.destroy()
    except Exception:
        # Fallback to CLI
        print(f"\n🔌 [010_tmdb] {msg}")
        response = input("Auto-install? (y/n): ").lower() == 'y'
        
    if response:
        print("🔌 [010_tmdb] Processing auto-install request (instructional only for now)...")
        if os.name == 'nt':
            print("   👉 Note: For Windows, please extract 'mkvpropedit.exe' from MKVToolNix into the program root.")
            print("   🔗 Download: https://mkvtoolnix.download/downloads.html#windows")
        else:
            print("   👉 Note: On Linux, run: sudo apt update && sudo apt install -y mkvtoolnix")
        return False
    else:
        print("\n🔌 [010_tmdb] ⚠️ mkvpropedit missing. MKV title tagging will be skipped.")
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
        found_year = int(paren_year_match.group(1))
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

# ==============================================================================
# 🎞️ ASSETS & NFO
# ==============================================================================

def extract_video_thumb(video_path, output_path, percent=0.15):
    try:
        cmd_probe = [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        result = subprocess.run(cmd_probe, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        timestamp = duration * percent
        cmd_extract = [FFMPEG_PATH, "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", "-q:v", "2", output_path, "-y", "-loglevel", "error"]
        subprocess.run(cmd_extract, check=True)
        return True
    except:
        return False

def write_nfo(target_path, data, media_type):
    nfo_path = os.path.splitext(target_path)[0] + ".nfo"
    root_tag = 'movie' if media_type == 'movie' else 'episodedetails'
    root = Element(root_tag)
    SubElement(root, 'title').text = data.get('title' if media_type == 'movie' else 'name', '')
    SubElement(root, 'plot').text = data.get('overview', '')
    if media_type == 'movie':
        SubElement(root, 'year').text = data.get('release_date', '')[:4]
    else:
        SubElement(root, 'season').text = str(data.get('season_number', ''))
        SubElement(root, 'episode').text = str(data.get('episode_number', ''))
    pretty_xml = minidom.parseString(tostring(root, 'utf-8')).toprettyxml(indent="  ")
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)

# ==============================================================================
# 🚀 PLUGIN ENTRY POINT
# ==============================================================================

def process(file_path):
    load_config()
    
    # Requirement check: We need at least the TMDB API key to do anything
    if not CONFIG.get('tmdb_api_key'):
        return file_path

    check_dependencies()
    
    print(f"🔌 [010_tmdb] Start processing: {os.path.basename(file_path)}")
    
    parsed = parse_filename(file_path)
    if not parsed:
        print(f"🔌 [010_tmdb] ⚠️ Could not parse filename: {os.path.basename(file_path)}")
        return file_path
        
    print(f"   🔍 Parsed: {parsed}")
    tmdb_data = fetch_tmdb_metadata(parsed)
    
    if not tmdb_data:
        print(f"   ❌ TMDB lookup failed for: {parsed['search_title']}")
        return file_path

    # Organize
    base_dir = get_base_dir()
    media_type = parsed['type']
    
    if media_type == 'movie':
        title = tmdb_data.get('title', 'Unknown Movie')
        year = tmdb_data.get('release_date', '0000')[:4]
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        target_dir = os.path.join(str(CONFIG.get('movies_dir') or os.path.join(base_dir, 'Movie')), f"{safe_title} ({year})")
        target_filename = f"{safe_title} ({year}){os.path.splitext(file_path)[1]}"
    else:
        show_title = tmdb_data.get('name', 'Unknown Series')
        show_year = tmdb_data.get('first_air_date', '0000')[:4]
        s = parsed['season_num']
        e = parsed['episode_num']
        ep_data = fetch_tmdb_episode(tmdb_data['id'], s, e)
        ep_name = ep_data.get('name', 'Unknown') if ep_data else 'Unknown'
        safe_show = re.sub(r'[\\/:*?"<>|]', '_', show_title)
        safe_ep = re.sub(r'[\\/:*?"<>|]', '_', ep_name)
        target_dir = os.path.join(str(CONFIG.get('tv_dir') or os.path.join(base_dir, 'TV')), f"{safe_show} ({show_year})", f"Season {s:02d}")
        target_filename = f"{safe_show} ({show_year}) - S{s:02d}E{e:02d} - {safe_ep}{os.path.splitext(file_path)[1]}"

    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, target_filename)

    print(f"   🚚 Organizing to: {target_path}")
    try:
        shutil.move(file_path, target_path)
        
        # Tag MKV
        if MKVPROPEDIT_PATH:
            title_tag = target_filename.rsplit('.', 1)[0]
            print(f"   🏷️ Tagging MKV: {title_tag}")
            subprocess.run([MKVPROPEDIT_PATH, target_path, "--set", f"title={title_tag}"], capture_output=True)
            
        # NFO and Thumb
        write_nfo(target_path, ep_data if media_type == 'tv' else tmdb_data, media_type)
        thumb_path = os.path.splitext(target_path)[0] + "-thumb.jpg"
        extract_video_thumb(target_path, thumb_path)
        
        return target_path
    except Exception as e:
        print(f"   ❌ Move failed: {e}")
        return file_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1])
    else:
        load_config()
        print(f"🔌 [010_tmdb] Configuration check complete.")
