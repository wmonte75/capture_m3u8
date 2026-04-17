import shutil
import json
import sys
import os
import re
import subprocess

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

def load_config():
    global CONFIG
    config_path = os.path.join(get_base_dir(), 'config.json')
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
        
        required = {"ffmpeg_path": ""}
        updated = False
        for key, default in required.items():
            if key not in CONFIG:
                CONFIG[key] = default
                updated = True
        
        if updated:
            try:
                import capture_m3u8
                capture_m3u8.save_config(CONFIG)
                print(f"🔌 [002_norm] Updated config.json.")
            except Exception as e:
                print(f"🔌 [002_norm] Error writing config.json: {e}")
    except Exception as e:
        print(f"🔌 [002_norm] Warning: Could not load config.json: {e}")

def find_exe(name, config_key=None):
    """Robust executable discovery."""
    base_dir = get_base_dir()
    is_win = os.name == 'nt'
    
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
    
    return shutil.which(name) or name

def process(file_path):
    load_config()
    ffmpeg_bin = find_exe("ffmpeg", "ffmpeg_path")
    
    if not os.path.exists(file_path):
        return file_path

    # 1. TV Series Check
    if not re.search(r'S\d+E\d+', os.path.basename(file_path), re.IGNORECASE):
        print("   🎬 Movie detected. Skipping TV-specific plugin.")
        return file_path

    print(f"🔌 [Plugin] Processing TV Audio: {os.path.basename(file_path)}")

    # 2. Detect Input Channels
    is_51 = False
    creation_flags = 0
    if os.name == 'nt':
        creation_flags = 0x08000000 # CREATE_NO_WINDOW

    try:
        result = subprocess.run([ffmpeg_bin, "-i", file_path], stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, creationflags=creation_flags)
        if re.search(r"Stream #0:\d+.*Audio:.*(5\.1|6 channels)", result.stderr):
            is_51 = True
    except Exception as e:
        print(f"   ⚠️ Could not probe file: {e}")

    # 3. Dynamic Logic based on Source Channels
    if is_51:
        # Source is 5.1: No upmix needed, just normalize Track 1. Track 2 stays 5.1.
        print("   ℹ️ Source is already 5.1. Normalizing T1, keeping T2 as 5.1 Direct.")
        filter_complex = "[0:a]asplit=2[v1][v2];[v1]dynaudnorm=f=200:g=7[norm];[v2]anull[direct]"
        direct_channels = "6"
        direct_title = "Direct 5.1"
    else:
        # Source is Stereo: Upmix + Normalize Track 1. Track 2 stays Stereo.
        print("   ℹ️ Source is Stereo. Upmixing T1 to 5.1, keeping T2 as Stereo Direct.")
        filter_complex = (
            "[0:a]asplit=2[v1][v2];"
            "[v1]pan=5.1|FL=c0|FR=c1|FC=0.5*c0+0.5*c1|LFE=0.5*c0+0.5*c1|BL=c0|BR=c1,dynaudnorm=f=200:g=7[norm];"
            "[v2]anull[direct]"
        )
        direct_channels = "2"
        direct_title = "Direct Stereo"

    base_name, extension = os.path.splitext(file_path)
    base_name = base_name.replace("_Sanitized", "")
    output_path = f"{base_name}_DualAudio{extension}"

    # 4. Construct FFmpeg command
    cmd = [
        ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error", "-stats",
        "-i", file_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",            # Map Video
        "-map", "[norm]",         # Map Track 1 (Always 5.1)
        "-map", "[direct]",       # Map Track 2 (Source Match)
        "-map", "0:s?",           # Map Subtitles
        "-c:v", "copy",           
        "-c:a:0", "aac", "-ac:a:0", "6", "-q:a:0", "2",
        "-c:a:1", "aac", "-ac:a:1", direct_channels, "-q:a:1", "2",
        "-metadata:s:a:0", f"title=Normalized 5.1",
        "-metadata:s:a:1", f"title={direct_title}",
        "-disposition:a:0", "default",
        "-disposition:a:1", "0",
        "-map_chapters", "-1",
        "-map_metadata", "-1",
        "-threads", "2",
        output_path
    ]
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            bufsize=0,
            creationflags=creation_flags
        )

        if process.stdout:
            buffer = bytearray()
            while True:
                char = process.stdout.read(1)
                if not char: break
                buffer.extend(char)
                if char == b'\r' or char == b'\n':
                    try:
                        line = buffer.decode('utf-8', errors='replace')
                        sys.stdout.write(line)
                        sys.stdout.flush()
                        buffer.clear()
                    except: pass

        process.wait()
        
        if process.returncode == 0 and os.path.exists(output_path):
            print(f"   ✅ Done: {os.path.basename(output_path)}")
            os.remove(file_path) 
            return output_path   
        else:
            print(f"   ❌ FFmpeg failed (Code {process.returncode})")
            return file_path
            
    except Exception as e:
        print(f"   ❌ Processing failed: {e}")
        return file_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1])
    else:
        load_config()
        print(f"🔌 [002_norm_tv] Ready for TV processing.")