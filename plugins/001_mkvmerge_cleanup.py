import shutil
import json
import sys
import os
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
    except Exception as e:
        print(f"🔌 [001_mkvmerge] Warning: Could not load config.json: {e}")

def find_exe(name, config_key=None):
    """Robust executable discovery (Binaries Folder -> Root -> System Path)."""
    base_dir = get_base_dir()
    is_win = os.name == 'nt'
    
    if config_key and CONFIG.get(config_key):
        conf_path = CONFIG[config_key]
        if os.path.isabs(conf_path) and os.path.exists(conf_path):
            return conf_path
        abs_conf = os.path.join(base_dir, conf_path)
        if os.path.exists(abs_conf):
            return abs_conf

    ext = ".exe" if is_win else ""
    
    search_dirs = [os.path.join(base_dir, "binaries"), base_dir]
    for d in search_dirs:
        if not os.path.exists(d): continue
        local_path = os.path.join(d, name + ext)
        if os.path.exists(local_path):
            return local_path
    
    return shutil.which(name) or name

def process(file_path):
    """
    Passes the MKV through mkvmerge to ensure container integrity.
    This fixes timestamp jank and 'Duration: N/A' issues common in HLS streams.
    """
    load_config()
    mkvmerge_bin = find_exe("mkvmerge", "mkvmerge_path")
    
    if not os.path.exists(file_path):
        return file_path

    # Skip if it looks like we've already merged it (to prevent loops)
    if "_Sanitized" in file_path:
        return file_path

    # Note: We no longer strictly require .mkv extension here because 
    # mkvmerge can convert .ts or .mp4 files into sanitized .mkv files.

    base_name, extension = os.path.splitext(file_path)
    # mkvmerge always outputs a Matroska container. 
    # We force the output extension to .mkv to ensure correct file typing.
    output_path = f"{base_name}_Sanitized.mkv"

    print(f"🔌 [Plugin] Sanitizing/Remuxing to MKV: {os.path.basename(file_path)}")

    # Ensure output doesn't exist to prevent 'already exists' errors
    if os.path.exists(output_path):
        try: os.remove(output_path)
        except Exception as e:
            print(f"   ⚠️ Could not remove stale output: {e}")

    # Construct mkvmerge command
    # --output: The new clean file
    cmd = [
        mkvmerge_bin,
        "--output", output_path,
        file_path
    ]
    
    creation_flags = 0
    if os.name == 'nt':
        creation_flags = 0x08000000 # CREATE_NO_WINDOW

    try:
        # mkvmerge outputs progress to stdout
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            bufsize=0,
            creationflags=creation_flags
        )

        if process.stdout:
            while True:
                line = process.stdout.readline()
                if not line: break
                try:
                    text = line.decode('utf-8', errors='replace').strip()
                    if "Progress:" in text:
                        # Forward progress to the GUI/CLI log
                        sys.stdout.write(f"\r   {text}")
                        sys.stdout.flush()
                    # elif text:
                    #     print(f"   [mkvmerge] {text}")
                except: pass
            print() # New line after progress

        process.wait()
        
        if process.returncode in [0, 1] and os.path.exists(output_path):
            # Code 0 = Success, Code 1 = Success with warnings
            if process.returncode == 1:
                print("   ⚠️  mkvmerge finished with warnings (usually minor).")
            
            print(f"   ✅ Container integrity verified.")
            try:
                os.remove(file_path)
                return output_path   
            except Exception as e:
                print(f"   ⚠️ Could not delete original after merge: {e}")
                return output_path
        else:
            print(f"   ❌ mkvmerge failed (Code {process.returncode})")
            return file_path
            
    except Exception as e:
        print(f"   ❌ Sanitization failed: {e}")
        return file_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        process(sys.argv[1])
    else:
        load_config()
        print(f"🔌 [001_mkvmerge] Ready for container sanitization.")