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
from PIL import Image, ImageStat
import io
import argparse

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
    # Use configured log location if provided, otherwise default to tools/logs
    log_location = CONFIG.get('log_dir', '').strip() if CONFIG else ''
    if log_location:
        log_dir = os.path.abspath(log_location)
    else:
        log_dir = os.path.join(get_base_dir(), "tools", "logs")
    
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    return log_dir

def setup_logging():
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, 'TMDB.log')
    if not isinstance(sys.stdout, DualLogger):
        sys.stdout = DualLogger(log_file, sys.stdout)

def load_config():
    """Load configuration from tmdb.json (read-only)."""
    global CONFIG
    
    # Config file lives next to the script or executable
    if getattr(sys, 'frozen', False):
        config_dir = os.path.dirname(sys.executable)
    else:
        config_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(config_dir, 'tmdb.json')
    
    defaults = {
        "movies_dir": "Movie",
        "tv_dir": "TV",
        "unsorted_dir": "Unsorted",
        "ffmpeg_path": "",
        "ffprobe_path": "",
        "mkvpropedit_path": "",
        "language": "en",
        "log_dir": ""
    }
    
    CONFIG = dict(defaults)
    
    if not os.path.exists(config_path):
        msg = f"[010_tmdb] Critical: Config file not found: {config_path}"
        print(msg)
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("TMDB Plugin Configuration", msg)
            root.destroy()
        except: pass
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Map tmdb.json nested structure to flat CONFIG
        CONFIG['tmdb_api_key'] = data.get('TMDB', {}).get('API_KEY', '')
        CONFIG['fanart_api_key'] = data.get('fanart.tv', {}).get('API_KEY', '')
        CONFIG['omdb_api_key'] = data.get('OMDb', {}).get('API_KEY', '')
        
        paths = data.get('PATH', {})
        # Preserve explicit null for UNSORTED (disabled), otherwise use default if missing
        for path_key, config_key, default_val in [
            ('TV', 'tv_dir', defaults['tv_dir']),
            ('MOVIE', 'movies_dir', defaults['movies_dir']),
            ('UNSORTED', 'unsorted_dir', defaults['unsorted_dir'])
        ]:
            if path_key in paths:
                CONFIG[config_key] = paths[path_key]
            else:
                CONFIG[config_key] = default_val
        
        # Optional top-level settings override defaults
        for key in ['ffmpeg_path', 'ffprobe_path', 'mkvpropedit_path', 'language', 'log_dir']:
            if key in data:
                CONFIG[key] = data[key]
        
        print(f"[010_tmdb] Loaded config: {config_path}")
    except Exception as e:
        print(f"[010_tmdb] Error loading config: {e}")
        sys.exit(1)
    
    if not CONFIG.get('tmdb_api_key'):
        msg = "[010_tmdb] Critical: TMDb API Key is missing in tmdb.json."
        print(msg)
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("TMDB Plugin Configuration", msg)
            root.destroy()
        except: pass
        sys.exit(1)

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
    (?P<tv_tail>.*)$ 
    | 
    ^
    (?P<movie_title>.+?) 
    [.\s_\(-]+ 
    (?P<movie_year>(?:19|20)\d{2}) 
    (?P<movie_tail>.*)$ """,
    re.VERBOSE | re.IGNORECASE
)

def _normalize_separators(text):
    """Replace common ASCII and Unicode separators/bullets with spaces."""
    # Covers dots, underscores, brackets, and common bullets/dashes.
    text = re.sub(r'[._\[\]·•‐‑‒–—―]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_filename(filename):
    """Parse filename to extract media info. FIXED to handle years and multi-word titles."""
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]
    
    # Normalize separators/bullets/dashes so the regex can treat them as whitespace.
    name_cleaned = _normalize_separators(name_no_ext)

    # Normalize common episode patterns: 2x03 -> S02E03
    name_cleaned = re.sub(r'\b(\d+)[xX](\d+)\b', lambda m: f"S{int(m.group(1)):02d}E{int(m.group(2)):02d}", name_cleaned)

    # Clean standard plugin suffixes to improve TMDB search accuracy
    for suffix in _PLUGIN_SUFFIXES:
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
        
        # Extract edition/version info, then strip quality/group tags from search title
        edition, search_title = _extract_edition(search_title)
        search_title = _clean_search_title(search_title)
            
        return {
            'type': 'tv', 
            'search_title': search_title, 
            'season_num': int(data['season']), 
            'episode_num': int(data['episode']),
            'year': year,
            'edition': edition
        }

    # MOVIE PARSING
    elif data.get('movie_title'):
        raw_title = data['movie_title'].strip()
        year = int(data.get('movie_year') or 0) or None
        search_title = re.sub(r'[\s._\(]+$', '', raw_title).strip()
        search_title, _ = _clean_title_and_year_smart(search_title)
        
        # Extract edition/version info from both title and trailing text (e.g., after year),
        # then strip quality/group tags from search title
        edition_title, search_title = _extract_edition(search_title)
        edition_tail, _ = _extract_edition(data.get('movie_tail', ''))
        edition = ' '.join(filter(None, [edition_title, edition_tail]))
        search_title = _clean_search_title(search_title)
        
        return {
            'type': 'movie', 
            'search_title': search_title, 
            'year': year,
            'edition': edition
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

    # Look for year followed by trailing punctuation/separator at end: Title 2022 ·
    punct_year_match = re.search(r'\s((?:19|20)\d{2})\W*$', search_title)
    if punct_year_match:
        found_year = int(punct_year_match.group(1))
        search_title = search_title[:punct_year_match.start()].strip()
        return search_title, found_year
    
    # Remove country codes like (US), (UK) but keep the text
    search_title = re.sub(r'\([A-Z]{2}\)', '', search_title).strip()
    
    return search_title, found_year


# Tags commonly found in filenames that should not be sent to TMDB
_QUALITY_TAGS = [
    r'1080p', r'720p', r'2160p', r'4K', r'UHD', r'\d+p',
    r'BluRay', r'WEB[-]?DL', r'WEBRip', r'HDRip', r'BRRip', r'DVDRip', r'DVD', r'HDTV',
    r'REMUX', r'WEB', r'HD', r'SD',
    r'x264', r'x265', r'HEVC', r'H\.264', r'H\.265', r'AVC', r'VC-1',
]

_AUDIO_TAGS = [
    r'AAC', r'AC3', r'DD[Pp]?[\d\.]+', r'DTS', r'TrueHD', r'Atmos', r'5\.1', r'7\.1',
    r'2\.0', r'EAC3',
]

_EDITION_TAGS = [
    r'Extended', r'Director\'?s Cut', r'Theatrical', r'Final Cut', r'IMAX',
    r'Unrated', r'Remastered', r'Special Edition', r'Limited Edition',
    r'Part One', r'Part Two', r'Part 1', r'Part 2',
]

_PLUGIN_SUFFIXES = ["Sanitized", "DualAudio", "Normalized", "CleanAudio", "HQ"]


def _extract_edition(title_str):
    """Extract edition/version keywords to preserve in final filename."""
    matches = []
    for pattern in _EDITION_TAGS:
        for match in re.finditer(rf'\b({pattern})\b', title_str, re.IGNORECASE):
            matches.append((match.start(), match.group(1)))
    
    if not matches:
        return '', title_str
    
    # Preserve original order
    matches.sort(key=lambda x: x[0])
    edition_parts = [m[1] for m in matches]
    
    # Remove matches from title (in reverse order to preserve string indices)
    remaining = title_str
    for _, part in sorted(matches, key=lambda x: x[0], reverse=True):
        remaining = re.sub(rf'\b{re.escape(part)}\b', '', remaining, flags=re.IGNORECASE, count=1)
    
    remaining = re.sub(r'\s+', ' ', remaining).strip()
    return ' '.join(edition_parts), remaining


def _clean_search_title(title_str):
    """Prepare title for TMDB search by stripping quality, group, codec tags."""
    cleaned = title_str
    
    # Remove standard plugin suffixes
    for suffix in _PLUGIN_SUFFIXES:
        cleaned = re.sub(rf'\b{suffix}\b', '', cleaned, flags=re.IGNORECASE)
    
    # Remove bracketed/parenthesized release group tags
    cleaned = re.sub(r'[\(\[\{][^\)\]\}]{1,35}[\)\]\}]', ' ', cleaned)
    
    # Remove quality, codec, and audio tags
    for tag in _QUALITY_TAGS + _AUDIO_TAGS:
        cleaned = re.sub(rf'\b{tag}\b', ' ', cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\W+$', '', cleaned).strip()
    return cleaned


def _aggressive_title_clean(title):
    """Last-resort title cleaning for TMDB search (removes years and leftover tags)."""
    if not title:
        return title

    cleaned = _normalize_separators(title)
    # Remove standard plugin suffixes
    for suffix in _PLUGIN_SUFFIXES:
        cleaned = re.sub(rf'\b{suffix}\b', '', cleaned, flags=re.IGNORECASE)

    # Remove bracketed/parenthesized release group tags
    cleaned = re.sub(r'[\(\[\{][^\)\]\}]{1,35}[\)\]\}]', ' ', cleaned)

    # Remove any standalone 19xx/20xx year numbers
    cleaned = re.sub(r'\b(19|20)\d{2}\b', ' ', cleaned)

    # Remove quality, codec, and audio tags
    for tag in _QUALITY_TAGS + _AUDIO_TAGS:
        cleaned = re.sub(rf'\b{tag}\b', ' ', cleaned, flags=re.IGNORECASE)

    # Collapse whitespace and strip trailing punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\W+$', '', cleaned).strip()
    return cleaned


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
    
    pref_lang = CONFIG.get('language', language)
    lang_images = [img for img in image_list if img.get('iso_639_1') == pref_lang and img.get('file_path')]
    if lang_images:
        lang_images.sort(key=lambda x: x.get('vote_count', 0), reverse=True)
        return lang_images[0]['file_path']
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

def _score_candidate(candidate, parsed_data):
    """Score a TMDB result by how well it matches the parsed filename."""
    score = 0
    candidate_name = candidate.get('name') or candidate.get('title', '')
    search_title = parsed_data.get('search_title', '').lower().strip()
    candidate_lower = candidate_name.lower().strip()
    
    if not search_title or not candidate_lower:
        return score
    
    # Title match
    if candidate_lower == search_title:
        score += 100
    elif candidate_lower.startswith(search_title + ' '):
        score += 80
    elif ' ' in search_title and search_title in candidate_lower:
        score += 60
    elif search_title in candidate_lower:
        score += 40
    
    # Year proximity
    filename_year = parsed_data.get('year') or 0
    if filename_year:
        date = candidate.get('first_air_date') or candidate.get('release_date', '')
        candidate_year = int(date[:4]) if date and len(date) >= 4 and date[:4].isdigit() else None
        if candidate_year:
            if candidate_year == filename_year:
                score += 30
            elif abs(candidate_year - filename_year) <= 1:
                score += 15
    
    # Popularity tie-breaker (capped)
    score += min(candidate.get('popularity', 0) * 0.5, 15)
    
    # Vote average tie-breaker (capped)
    score += min(candidate.get('vote_average', 0), 10)
    
    return score


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
    
    year = parsed_data.get('year')
    year_label = str(year) if year else 'any'
    print(f"SEARCH: TMDB {endpoint.upper()} query='{parsed_data['search_title']}' filename_year={year_label}")
    
    # FIXED: Properly pass year parameters
    if year:
        if parsed_data['type'] == 'tv': 
            params['first_air_date_year'] = year
        else: 
            params['year'] = year
        
    try:
        resp = requests.get(url, params=params, timeout=10).json()
        results = resp.get('results', [])
    except Exception as e:
        print(f"🔌 [010_tmdb] API Error: {e}")
        return []
    
    # Fallback: if a year filter produced no results, retry without it.
    # The year in a filename is often the episode air year for TV or a wrong
    # metadata year, not necessarily the series/movie release year.
    if not results and parsed_data.get('year'):
        print(f"WARNING: No results with year {parsed_data['year']}. Retrying without year filter...")
        params.pop('year', None)
        params.pop('first_air_date_year', None)
        try:
            resp = requests.get(url, params=params, timeout=10).json()
            results = resp.get('results', [])
        except Exception as e:
            print(f"🔌 [010_tmdb] API Error on fallback: {e}")
            return []
    
    # Final fallback: aggressively clean the title (strip years, trailing
    # punctuation, and leftover tags) and search without a year filter.
    if not results:
        aggressive_title = _aggressive_title_clean(parsed_data['search_title'])
        if aggressive_title and aggressive_title != parsed_data['search_title']:
            print(f"WARNING: No results. Retrying with cleaned title: {aggressive_title}")
            params['query'] = aggressive_title
            params.pop('year', None)
            params.pop('first_air_date_year', None)
            try:
                resp = requests.get(url, params=params, timeout=10).json()
                results = resp.get('results', [])
            except Exception as e:
                print(f"🔌 [010_tmdb] API Error on final fallback: {e}")
                return []
    
    return results

def fetch_tmdb_episode(tmdb_id, season, episode):
    api_key = CONFIG.get('tmdb_api_key')
    url = f"{TMDB_API_BASE}/tv/{tmdb_id}/season/{season}/episode/{episode}"
    try:
        return requests.get(url, params={'api_key': api_key}, timeout=10).json()
    except:
        return None

def _is_placeholder_title(title):
    """Detect generic/placeholder titles from IMDb that should not override TMDB."""
    if not title or not title.strip():
        return True
    t = title.strip()
    # Generic episode placeholders: "Episode #3.3", "Episode 3", "Ep. 3", "Ep 1.2"
    if re.match(r'^(Episode|Ep\.?)\s*#?\s*\d+(\.\d+)?$', t, re.IGNORECASE):
        return True
    # Just a number like "3" or "3.3"
    if re.match(r'^\d+(\.\d+)?$', t):
        return True
    # Common generic placeholders
    if t.lower() in ('tbd', 'untitled', 'n/a', 'unknown'):
        return True
    return False


def fetch_omdb_data(title, year=None, media_type=None, season=None, episode=None, imdb_id=None):
    if not CONFIG.get('omdb_api_key'): 
        return None
    params = {
        'apikey': CONFIG['omdb_api_key'], 
        'plot': 'full',
        'r': 'json'
    }
    
    # Prefer IMDB ID for precision, fall back to title
    if imdb_id:
        params['i'] = imdb_id
    elif title:
        params['t'] = title
    else:
        return None
    
    if year: 
        params['y'] = str(year)
    if media_type == 'movie': 
        params['type'] = 'movie'
    elif media_type == 'tv': 
        params['type'] = 'series'
    
    # Episode-specific lookup
    if season is not None:
        params['Season'] = str(season)
    if episode is not None:
        params['Episode'] = str(episode)

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

def _unique_target_path(target_dir, base_filename, ext):
    """Generate a unique target path, appending - Copy, - Copy (2), etc."""
    target_path = os.path.join(target_dir, f"{base_filename}{ext}")
    if not os.path.exists(target_path):
        return target_path
    
    counter = 1
    while True:
        if counter == 1:
            candidate = f"{base_filename} - Copy{ext}"
        else:
            candidate = f"{base_filename} - Copy ({counter}){ext}"
        candidate_path = os.path.join(target_dir, candidate)
        if not os.path.exists(candidate_path):
            return candidate_path
        counter += 1


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

def is_image_too_dark(image_path, threshold=35):
    """Checks if an image is too dark using mean brightness (0-255)."""
    try:
        with Image.open(image_path) as img:
            # Convert to grayscale to calculate luminosity
            stat = ImageStat.Stat(img.convert('L'))
            brightness = stat.mean[0]
            return brightness < threshold
    except Exception:
        return False

def extract_video_thumb(video_path, output_path, percent=0.40):
    # Hide window on Windows
    creation_flags = 0
    if os.name == 'nt':
        creation_flags = 0x08000000 # CREATE_NO_WINDOW
    
    duration = 0.0
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
        if duration_str:
            duration = float(duration_str)

        # Try extracting and check for dark frames. 
        # If dark, increment percentage by 1% (0.01) up to 15 times.
        for attempt in range(15):
            current_percent = min(percent + (attempt * 0.01), 0.95)
            timestamp = duration * current_percent if duration > 0 else (60 + (attempt * 60))
            
            print(f"   --> 🎞️  Extracting frame at {int(current_percent*100)}% ...")

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
            
            if process.returncode == 0 and os.path.exists(output_path):
                if is_image_too_dark(output_path) and attempt < 14:
                    print(f"      ⚠️  Frame at {int(current_percent*100)}% is too dark. Nudging +1%...")
                    continue
                return True
            elif stdout:
                print(f"      FFmpeg: {stdout.strip()}")

    except Exception as e:
        print(f"   --> ❌ FFmpeg Error: {e}")
        return False
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
            fetch_and_download_season_assets(show_id, parsed_data['season_num'], show_dir, media_dir)
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

def fetch_and_download_season_assets(show_id, season_num, show_dir, season_dir):
    """Downloads season-specific posters and fanart to both the series root and the season folder with professional fallbacks."""
    root_poster = os.path.join(show_dir, f"Season{season_num:02d}-poster.jpg")
    folder_poster = os.path.join(season_dir, "folder.jpg")
    root_fanart = os.path.join(show_dir, f"Season{season_num:02d}-fanart.jpg")
    folder_fanart = os.path.join(season_dir, "fanart.jpg")
    series_fanart = os.path.join(show_dir, "fanart.jpg")
    
    fanart_data = fetch_fanart_assets('tv', show_id)
    if not TMDB_IMAGE_BASE:
        fetch_tmdb_config()
    api_key = CONFIG.get('tmdb_api_key')

    # Process Posters and Fanart (Thumbs)
    asset_types = [
        ('poster', 'seasonposter', 'posters', POSTER_SIZE, root_poster, folder_poster),
        ('fanart', 'seasonthumb', 'backdrops', BACKDROP_SIZE, root_fanart, folder_fanart)
    ]

    for label, fanart_key, tmdb_key, size, r_path, f_path in asset_types:
        # Skip if both already exist
        if os.path.exists(r_path) and os.path.exists(f_path):
            continue

        print(f"   --> 🖼️ Searching for Season {season_num} {label}...")
        url = None

        # 1. Try Fanart.tv first (Priority)
        if fanart_data and fanart_key in fanart_data:
            assets = [p for p in fanart_data[fanart_key] if p.get('season') == str(season_num)]
            if assets:
                assets.sort(key=lambda x: int(x.get('likes', 0)), reverse=True)
                url = assets[0]['url']
                print(f"   --> Found Season {season_num} {label} on Fanart.tv")

        # 2. Try TMDB Fallback
        if not url and api_key:
            tmdb_url = f"{TMDB_API_BASE}/tv/{show_id}/season/{season_num}/images"
            try:
                resp = requests.get(tmdb_url, params={'api_key': api_key}, timeout=10).json()
                tmdb_assets = resp.get(tmdb_key, [])
                path = get_best_image_path(tmdb_assets)
                if path:
                    url = f"{TMDB_IMAGE_BASE}{size}{path}"
                    print(f"   --> Found Season {season_num} {label} on TMDB")
            except:
                pass

        # 3. Try Episode 1 Stills (Only for Fanart/Backdrops)
        if not url and label == 'fanart' and api_key:
            ep_img_url = f"{TMDB_API_BASE}/tv/{show_id}/season/{season_num}/episode/1/images"
            try:
                ep_resp = requests.get(ep_img_url, params={'api_key': api_key}, timeout=10).json()
                stills = ep_resp.get('stills', [])
                path = get_best_image_path(stills)
                if path:
                    url = f"{TMDB_IMAGE_BASE}{size}{path}"
                    print(f"   --> Found Season {season_num} backdrop from Episode 1 Stills")
            except:
                pass

        # 3. Download and Duplicate
        if url:
            if download_image(url, r_path):
                try:
                    shutil.copyfile(r_path, f_path)
                    print(f"   --> ✅ Season {label} saved to root and season folder.")
                except Exception as e:
                    print(f"   ⚠️ Could not copy season {label}: {e}")
        else:
            print(f"   --> ℹ️ Season {season_num} {label} not found.")

    # Fallback: Inherit Series Fanart or Generate from video
    if not os.path.exists(root_fanart) and not os.path.exists(folder_fanart):
        # 1. Try to copy the main show fanart (Much better than video capture)
        if os.path.exists(series_fanart):
            print(f"   --> 📎 Using series-level fanart as season fallback...")
            try:
                shutil.copyfile(series_fanart, root_fanart)
                shutil.copyfile(series_fanart, folder_fanart)
                return
            except:
                pass

        # 2. Last resort: Video capture
        video_files = [f for f in os.listdir(season_dir) if f.endswith(('.mkv', '.mp4', '.ts'))]
        if video_files:
            sample_video = os.path.join(season_dir, video_files[0])
            try:
                if not os.path.exists(root_fanart):
                    print(f"   --> 🎞️ Generating fallback season fanart from video...")
                    extract_video_thumb(sample_video, root_fanart, percent=0.35) # Hit 35% for better chance of non-intro
                if os.path.exists(root_fanart) and not os.path.exists(folder_fanart):
                    shutil.copyfile(root_fanart, folder_fanart)
            except Exception as e:
                print(f"   ⚠️ Could not generate fallback season fanart: {e}")

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
        
    print(f"   RESULTS: TMDB returned {len(results)} candidate(s)")
    
    # NEW: Filter TV results by season existence
    if parsed_data['type'] == 'tv':
        valid_results = []
        for r in results[:5]:  # Check top 5 results
            show_id = r['id']
            show_name = r.get('name', 'Unknown')
            first_air = r.get('first_air_date', '????')[:4]
            
            if verify_season_exists(show_id, parsed_data['season_num']):
                print(f"   OK: Season {parsed_data['season_num']} confirmed for: {show_name} ({first_air})")
                valid_results.append(r)
            else:
                print(f"   REJECTED: {show_name} ({first_air}) - No Season {parsed_data['season_num']}")
        
        if valid_results:
            results = valid_results
        elif results:
            print(f"   ⚠️ Warning: None of the top results have Season {parsed_data['season_num']}")
            # Continue with original results but user will have to pick carefully
    
    selected = None
    
    # 1. TV-only: Try to match by episode name in filename (very high confidence)
    if parsed_data['type'] == 'tv' and len(results) > 1:
        for candidate in results[:3]:
            try:
                ep_url = f"{TMDB_API_BASE}/tv/{candidate['id']}/season/{parsed_data['season_num']}/episode/{parsed_data['episode_num']}"
                ep_resp = requests.get(
                    ep_url, 
                    params={'api_key': api_key}, 
                    timeout=5
                ).json()
                ep_name = ep_resp.get('name', '')
                ep_name_lower = ep_name.lower()
                candidate_name = candidate.get('name', 'Unknown')
                if ep_name_lower and ep_name_lower in basename.lower().replace('_', ' '):
                    print(f"\n⚡ Smart Match by Episode Name: {candidate_name} -> '{ep_name}'")
                    selected = candidate
                    break
                elif ep_name:
                    print(f"   INFO: Episode '{ep_name}' on {candidate_name} does not match filename")
            except: 
                continue

    # 2. Score candidates and either auto-select or prompt
    if not selected:
        scored = [(_score_candidate(r, parsed_data), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        print("\n   CANDIDATE SCORES:")
        for score, candidate in scored[:5]:
            name = candidate.get('name') or candidate.get('title', 'Unknown')
            date = candidate.get('first_air_date') or candidate.get('release_date', '????')
            print(f"      {score:>6.1f}  {name} ({date[:4]})")
        
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0
        gap = best_score - second_score
        best_name = best.get('name') or best.get('title', 'Unknown')
        
        if len(results) == 1:
            selected = best
            print(f"\n⚡ Single Result: {best_name}")
        elif best_score >= 100:
            selected = best
            print(f"\n⚡ High-Confidence Match: {best_name} (score {best_score:.1f})")
        elif gap >= 25 and best_score >= 70:
            selected = best
            print(f"\n⚡ Best Match (gap {gap:.1f}): {best_name} (score {best_score:.1f})")
        else:
            print(f"\n   UNCLEAR: best score {best_score:.1f}, gap {gap:.1f}. Prompting user...")
            selected = prompt_user_selection([r for _, r in scored], parsed_data['type'])
    
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
        
        # Cross-reference episode title with IMDb (OMDb) if available
        omdb_ep = fetch_omdb_data(
            title=show_info['name'],
            media_type='tv',
            season=s_num,
            episode=e_num,
            imdb_id=show_info.get('external_ids', {}).get('imdb_id')
        )
        if omdb_ep and omdb_ep.get('Title'):
            tmdb_title = ep_info.get('name', '')
            omdb_title = omdb_ep['Title']
            
            if _is_placeholder_title(omdb_title):
                print(f"   TITLE CROSS-CHECK: IMDb returned placeholder '{omdb_title}'. Keeping TMDb title '{tmdb_title}'.")
            elif omdb_title.lower().strip() != tmdb_title.lower().strip():
                print(f"   TITLE CROSS-CHECK: TMDb='{tmdb_title}' -> IMDb='{omdb_title}'. Using IMDb.")
                ep_info['name'] = omdb_title
            else:
                print(f"   TITLE CROSS-CHECK: TMDb and IMDb agree on '{omdb_title}'")
            
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
            target_path = _unique_target_path(target_dir, base_fn, ext)
            print(f"   --> ⚠️ File exists! Using unique name: {os.path.basename(target_path)}")
        
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
        
        # Preserve edition/version label (e.g., Extended, Director's Cut) in filename
        edition = parsed_data.get('edition', '').strip()
        edition_safe = re.sub(r'[\\/:*?"<>|]', '_', edition)
        base_filename = f"{safe_title} ({movie_year})"
        if edition_safe:
            base_filename += f" - {edition_safe}"
        
        os.makedirs(target_dir, exist_ok=True)
        ext = os.path.splitext(original_filepath)[1]
        target_path = os.path.join(target_dir, f"{base_filename}{ext}")
        
        if os.path.exists(target_path):
            target_path = _unique_target_path(target_dir, base_filename, ext)
            print(f"   --> ⚠️ File exists! Using unique name: {os.path.basename(target_path)}")
        
        print(f"   🚚 Moving to: {target_path}")
        shutil.move(original_filepath, target_path)
        
        final_title = f"{movie_title} ({movie_year})"
        set_mkv_title(target_path, final_title)
        handle_asset_downloads(parsed_data, m_info, target_path, omdb_info=omdb)
        return target_path

    return None

def process(file_path, tv_dir=None, movie_dir=None, unsorted_dir=None):
    load_config()
    setup_logging()
    
    # Allow command-line overrides for output paths (config.json is the default)
    if tv_dir:
        CONFIG['tv_dir'] = tv_dir
    if movie_dir:
        CONFIG['movies_dir'] = movie_dir
    if unsorted_dir:
        CONFIG['unsorted_dir'] = unsorted_dir
    
    if not CONFIG.get('tmdb_api_key'): 
        return file_path
        
    check_dependencies()
    fetch_tmdb_config()
    
    print(f"--- 🔍 Analyzing: {os.path.basename(file_path)} ---")
    
    parsed = parse_filename(file_path)
    if not parsed: 
        print(f"⚠️ Could not parse filename format")
        return file_path
    
    print(f"   Parsed: title='{parsed['search_title']}', filename_year={parsed.get('year') or 'none'}, "
          f"S{parsed.get('season_num', 0):02d}E{parsed.get('episode_num', 0):02d}")
    
    final_path = get_tmdb_title(parsed, file_path)
    
    if not final_path:
        print("⚠️ Identification failed or skipped.")
        unsorted = CONFIG.get('unsorted_dir')
        if unsorted:
            os.makedirs(unsorted, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            ext = os.path.splitext(file_path)[1]
            target = _unique_target_path(unsorted, base_name, ext)
            print(f"   🚚 Moving to Unsorted: {target}")
            shutil.move(file_path, target)
            return target
        return file_path
        
    return final_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Lookup metadata, rename, and organize media files using TMDB."
    )
    parser.add_argument('filepath', type=str, nargs='?', help='Path to media file')
    parser.add_argument('-to', '--tv-output', type=str, help='Override TV output folder')
    parser.add_argument('-mo', '--movie-output', type=str, help='Override Movie output folder')
    parser.add_argument('-unsortedout', '--unsorted-output', type=str, help='Override Unsorted folder')
    
    def _show_usage_and_wait():
        parser.print_help()
        print("\nPress Enter to Exit...", end='')
        input()
    
    if len(sys.argv) == 1:
        _show_usage_and_wait()
    else:
        args = parser.parse_args()
        
        if args.filepath:
            process(
                args.filepath,
                tv_dir=args.tv_output,
                movie_dir=args.movie_output,
                unsorted_dir=args.unsorted_output
            )
        else:
            _show_usage_and_wait()