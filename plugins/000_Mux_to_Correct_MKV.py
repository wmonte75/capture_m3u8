import os
import sys
import subprocess
import json
import shutil

# ==============================================================================
# ⚙️ CONFIGURATION & UTILITIES
# ==============================================================================

def get_base_dir():
    """Returns the base directory of the main application."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Root is up one level from plugins folder
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Global Config
CONFIG = {}

def load_config():
    global CONFIG
    config_path = os.path.join(get_base_dir(), 'config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
        
        # Auto-update config.json if required keys are missing
        required = {
            "ffmpeg_path": "",
            "ffprobe_path": ""
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
                print(f"🔌 [000_mux] Updated config.json with missing fields.")
            except Exception as e:
                print(f"🔌 [000_mux] Error writing config.json: {e}")
    except Exception as e:
        print(f"🔌 [000_mux] Warning: Could not load config.json: {e}")

def find_exe(name, config_key=None):
    """Robust executable discovery (Priority: Config -> Root -> System Path)."""
    base_dir = get_base_dir()
    is_win = os.name == 'nt'
    
    # 1. Check config
    if config_key and CONFIG.get(config_key):
        conf_path = CONFIG[config_key]
        if os.path.isabs(conf_path) and os.path.exists(conf_path):
            return conf_path
        abs_conf = os.path.join(base_dir, conf_path)
        if os.path.exists(abs_conf):
            return abs_conf

    # 2. Check root folder
    exts = [".exe"] if is_win else [""]
    search_names = [name]
    if name == "ffmpeg" and is_win:
        search_names.append("ffmpeg_libfdk_aac_1")
        
    for s_name in search_names:
        for ext in exts:
            local_path = os.path.join(base_dir, s_name + ext)
            if os.path.exists(local_path):
                return local_path
    
    # 3. Check system PATH
    return shutil.which(name) or name

# ==============================================================================
# 🚀 PLUGIN LOGIC
# ==============================================================================

def is_matroska(file_path, ffprobe_bin):
    """Checks if the file is internally a Matroska container."""
    try:
        cmd = [
            ffprobe_bin, "-v", "error", 
            "-show_entries", "format=format_name", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        format_name = result.stdout.strip().lower()
        # Matroska format name in ffprobe is often 'matroska,webm'
        return 'matroska' in format_name
    except Exception as e:
        print(f"   ⚠️ Container check failed: {e}")
        return False

def process(file_path):
    load_config()
    ffmpeg_bin = find_exe("ffmpeg", "ffmpeg_path")
    ffprobe_bin = find_exe("ffprobe", "ffprobe_path")

    print(f"🔌 [000_mux] Validating container for: {os.path.basename(file_path)}")
    
    if not os.path.exists(file_path):
        return file_path

    # Check if it's already a proper MKV
    if is_matroska(file_path, ffprobe_bin):
        print("   ✅ Already a valid Matroska container.")
        return file_path

    # If not, remux it
    print("   ⚠️ File is NOT a proper Matroska container (Detected as MPEG-TS or similar).")
    print("   🛠️ Remuxing to correct MKV format...")
    
    temp_path = file_path + ".correcting.mkv"
    
    cmd = [
        ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
        "-i", file_path,
        "-c", "copy",
        "-map", "0",
        temp_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
        if os.path.exists(temp_path):
            shutil.move(temp_path, file_path)
            print(f"   ✅ Remuxing complete. File successfully corrected.")
            return file_path
    except Exception as e:
        print(f"   ❌ Remuxing failed: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    return file_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1])
    else:
        load_config()
        print(f"🔌 [000_mux] Configuration check complete.")
