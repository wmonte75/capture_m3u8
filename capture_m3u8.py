import os
import sys
import asyncio
import re
import shutil
import subprocess
import json
import random
import importlib.util
import ctypes
import signal
import io
import zipfile
import tarfile
import platform
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import redirect_stdout, suppress
from typing import List, Tuple, Dict, Optional, Set, Any, Union, Callable

# Soft import for optional SCP/SFTP support
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

# Dependency Check
try:
    from playwright.async_api import async_playwright
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    # ... (dependency check remains the same)
    missing_module = str(e).split("'")[1] if "'" in str(e) else str(e)
    print(f"\n❌ Missing required Python library: {missing_module}")
    print("\nPlease install the missing requirements to run this script.")
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        print("\nRun this command in your terminal:")
        print("    python3 -m pip install -r requirements.txt\n")
    else:
        print("\nRun this command in your command prompt/terminal:")
        print("    pip install -r requirements.txt\n")
    sys.exit(1) # ... (dependency check remains the same)


def get_base_dir():
    """Returns the directory where the executable or script is located."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.absolute()

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return str(base_path / relative_path)

def get_log_dir():
    """Returns the absolute path to the Logs directory, creating it if needed."""
    log_dir = get_base_dir() / "binaries" / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return str(log_dir)

# Handle SSL Certificates for Frozen Apps
if getattr(sys, 'frozen', False):
    import certifi
    cert_path = certifi.where()
    os.environ["SSL_CERT_FILE"] = cert_path
    os.environ["REQUESTS_CA_BUNDLE"] = cert_path

def get_browser_executable(browser_type="chromium"):
    """
    Finds the actual executable path for the browser in the local playwright_browsers folder.
    Forces use of full Chromium even in headless mode to save space/avoid errors.
    """
    browsers_base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not browsers_base or not os.path.exists(browsers_base):
        return None

    # Determine executable name based on OS and browser
    exec_name = "chrome.exe" # Default
    if sys.platform == "win32":
        exec_name = "firefox.exe" if browser_type == "firefox" else "chrome.exe"
    else:
        exec_name = "firefox" if browser_type == "firefox" else "chrome"
    
    # We want to find a folder matching the browser type but EXCLUDING headless shell
    folder_keyword = "FIREFOX" if browser_type == "firefox" else "CHROMIUM"

    # Search for the executable within the correct browser folder
    for root, dirs, files in os.walk(browsers_base):
        if exec_name in files:
            path_upper = root.upper()
            # Must contain keyword but MUST NOT contain 'HEADLESS_SHELL'
            if folder_keyword in path_upper and "HEADLESS_SHELL" not in path_upper:
                return os.path.normpath(os.path.join(root, exec_name))
    
    return None

# Set Playwright to look for browsers in the bundled folder or local dev folder
def get_smart_browsers_path():
    """
    Determines where to look for browser binaries.
    1. Check if a 'playwright_browsers_path' is specified in config.json.
    2. Check if a 'binaries/playwright_browsers' folder exists (Priority).
    3. Check if a 'playwright_browsers' folder exists next to the EXE/Script (Root).
    4. If not, check if it's bundled inside (PyInstaller temp folder).
    """
    base_dir = get_base_dir()
    
    # 1. Config First
    if 'CONFIG' in globals() and CONFIG.get('playwright_browsers_path'):
        conf_path = CONFIG['playwright_browsers_path']
        if os.path.exists(conf_path):
            return conf_path
        abs_conf = os.path.join(base_dir, conf_path)
        if os.path.exists(abs_conf):
            return abs_conf

    # 2. Binaries Folder (Priority)
    binaries_path = Path(base_dir) / "binaries" / "playwright_browsers"
    if binaries_path.exists() and any(binaries_path.iterdir()):
        return str(binaries_path)

    # 3. Root Folder (Legacy/Default)
    exe_path = Path(base_dir) / "playwright_browsers"
    if exe_path.exists() and any(exe_path.iterdir()):
        return str(exe_path)
        
    # 4. Bundled location (PyInstaller temporary folder)
    if getattr(sys, 'frozen', False):
        try:
            bundle_path = Path(getattr(sys, '_MEIPASS', '')) / "playwright_browsers"
            if bundle_path.exists() and any(bundle_path.iterdir()):
                return str(bundle_path)
        except:
            pass
            
    return str(binaries_path)

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = get_smart_browsers_path()

def ensure_playwright_browsers():
    """Download Playwright browsers if they don't exist locally."""
    browsers_path = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    # Check if the folder exists and has contents (meaning browsers are downloaded)
    if not os.path.exists(browsers_path) or not os.listdir(browsers_path):
        os.makedirs(browsers_path, exist_ok=True)
        browsers_to_install = ["firefox"] if sys.platform.startswith('linux') else ["chromium"]
        
        log(f"\n🌐 First run detected: Downloading required browser engines ({', '.join(browsers_to_install)})...")
        log("   This may take a minute or two but only happens once.")
        try:
            from playwright._impl._driver import compute_driver_executable, get_driver_env
            driver_executable, driver_cli = compute_driver_executable()
            env = get_driver_env()
            
            for browser in browsers_to_install:
                log(f"   ⬇️  Downloading {browser}...")
                subprocess.run([driver_executable, driver_cli, "install", browser], env=env, check=True)
                
            log("   ✅ Browser engines downloaded successfully!\n")
        except Exception as e:
            log(f"   ❌ Failed to download browser engines: {e}\n")

# User-Agent matched to the actual OS to avoid fingerprint mismatch detection.
# Sites like vidsrcme.ru cross-check the UA OS against the real OS and block
# when they don't match (e.g. Windows UA running on Linux → about:blank).
if sys.platform.startswith('linux'):
    # Match the browser engine (Firefox) used on Linux to avoid detection
    USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'
elif sys.platform == 'darwin':
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
else:
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

async def block_resources(route):
    """Block images, fonts, and trackers to save CPU/bandwidth."""
    if route.request.resource_type in ["image", "font", "media"]:
        await route.abort()
    elif any(x in route.request.url for x in ["google-analytics", "doubleclick", "amazon-adsystem", "adnxs"]):
        await route.abort()
    else:
        await route.continue_()

# Download speed limit to avoid 429 "Too Many Requests" errors (e.g., '5M', '10M', '15M', '20M')
DOWNLOAD_SPEED = '6M'

# Random cooldown range between queue items (min_seconds, max_seconds)
COOLDOWN_RANGE = (10, 25)

# Global to track custom session directory for cleanup
CUSTOM_SESSION_DIR = None

# --- GUI / EXTERNAL INTERFACE HELPERS ---
LOG_CALLBACK = None
INPUT_CALLBACK = None
STATUS_CALLBACK = None
STOP_CALLBACK = None
CONFIG = {}

# Track active N_m3u8DL-RE subprocesses for clean shutdown
_active_download_processes: Set[asyncio.subprocess.Process] = set()

def is_process_running(pid: int) -> bool:
    """OS-aware check to see if a process ID is currently active."""
    if pid <= 0: return False
    if sys.platform == 'win32':
        # Standard Windows API check for process existence
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    else:
        # Unix-like signal 0 check
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

class DownloadLock:
    """Context manager to ensure only one instance downloads at a time with queueing."""
    def __init__(self, title: str):
        self.lock_file = os.path.join(get_log_dir(), "download.lock")
        self.title = title

    async def __aenter__(self):
        while True:
            check_stop()
            if os.path.exists(self.lock_file):
                try:
                    with open(self.lock_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    if '|' in content:
                        pid_str, locked_title = content.split('|', 1)
                        pid = int(pid_str)
                        
                        if is_process_running(pid):
                            report_status(f"Waiting for: {locked_title}")
                            log(f"⏳ Waiting for {locked_title} to finish... (Queueing)", end="\r")
                            await asyncio.sleep(5)
                            continue
                        else:
                            log(f"⚠️  Detected stale lock from dead PID {pid}. Cleaning up...")
                    
                except (ValueError, OSError, Exception):
                    pass 
                
                # If we reach here, the lock is stale or invalid
                with suppress(OSError):
                    os.remove(self.lock_file)
            
            # Attempt to acquire lock atomically
            try:
                with open(self.lock_file, 'x', encoding='utf-8') as f:
                    f.write(f"{os.getpid()}|{self.title}")
                log(f"🔓 Lock acquired for: {self.title}")
                return self
            except FileExistsError:
                continue

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        with suppress(OSError):
            if os.path.exists(self.lock_file):
                # Only delete if it's our lock (matches our PID)
                with open(self.lock_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content.startswith(f"{os.getpid()}|"):
                    os.remove(self.lock_file)
                    log(f"🔒 Lock released for: {self.title}")

async def update_nm3u8dl_re():
    """Queries GitHub API for the latest N_m3u8DL-RE release and updates the local binary."""
    repo = "nilaoda/N_m3u8DL-RE"
    bin_dir = os.path.join(get_base_dir(), "binaries")
    os.makedirs(bin_dir, exist_ok=True)
    
    # Determine platform keyword for GitHub asset matching
    if sys.platform == 'win32':
        keyword = "win-x64"
    elif sys.platform == 'darwin':
        # Apple Silicon vs Intel Mac
        keyword = "osx-arm64" if platform.machine() == 'arm64' else "osx-x64"
    else:
        keyword = "linux-x64"

    log(f"🔄 Checking GitHub for latest N_m3u8DL-RE release ({keyword})...")

    try:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        resp = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code == 404:
            resp = requests.get(f"https://api.github.com/repos/{repo}/releases", headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            data = resp.json()[0]
        else:
            resp.raise_for_status()
            data = resp.json()

        tag = data.get("tag_name", "Unknown")
        assets = data.get("assets", [])

        download_url = next((a["browser_download_url"] for a in assets if keyword in a["name"].lower()), None)

        if not download_url:
            log(f"   ❌ Could not find a suitable binary for {keyword} in release {tag}.")
            return

        log(f"   ⬇️  Downloading version {tag}...")
        asset_resp = requests.get(download_url, stream=True, timeout=60)
        asset_resp.raise_for_status()

        content = io.BytesIO(asset_resp.content)
        exe_name = "N_m3u8DL-RE.exe" if sys.platform == "win32" else "N_m3u8DL-RE"
        target_path = os.path.join(bin_dir, exe_name)

        if download_url.endswith(".zip"):
            with zipfile.ZipFile(content) as z:
                for zinfo in z.infolist():
                    if zinfo.filename.lower().endswith(exe_name.lower()):
                        source = z.open(zinfo)
                        with open(target_path, "wb") as f:
                            shutil.copyfileobj(source, f)
                        break
        elif download_url.endswith(".tar.gz"):
            with tarfile.open(fileobj=content, mode="r:gz") as t:
                for member in t.getmembers():
                    if member.isfile() and member.name.lower().endswith(exe_name.lower()):
                        source = t.extractfile(member)
                        with open(target_path, "wb") as f:
                            shutil.copyfileobj(source, f)
                        break
        else:
            with open(target_path, "wb") as f:
                f.write(content.getbuffer())

        # Ensure executable bit on Unix systems
        if sys.platform != 'win32' and os.path.exists(target_path):
            os.chmod(target_path, 0o755)

        log(f"   ✅ Successfully updated to {tag} in /binaries.")

    except Exception as e:
        log(f"   ❌ Update failed: {e}")

async def update_mkvtoolnix():
    """Queries GitHub for the latest MKVToolNix static build (Windows only)."""
    if sys.platform != 'win32':
        # For Linux/Mac, mkvpropedit is best managed via package manager
        if not shutil.which("mkvpropedit"):
            log("\n🐧 mkvpropedit not found.")
            log("   Please install via your package manager:")
            log("   Ubuntu/Debian: sudo apt install mkvtoolnix")
            log("   Arch/BigLinux: sudo pacman -S mkvtoolnix-gui")
            log("   MacOS: brew install mkvtoolnix")
        return

    base_url = "https://mkvtoolnix.download/windows/releases/"
    bin_dir = os.path.join(get_base_dir(), "binaries")
    os.makedirs(bin_dir, exist_ok=True)
    
    log(f"🔄 Checking official MKVToolNix server for latest portable build...")
    
    try:
        # 1. Scrape the main releases page to find the latest version directory
        resp = requests.get(base_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Collect links that represent version folders
        version_folders = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Normalize the path to get the last folder name (e.g., "88.0/" or "/path/88.0/")
            folder_name = href.strip('/').split('/')[-1]
            
            # Check if this part looks like a version number (digits and dots)
            if re.match(r'^\d+(\.\d+)*$', folder_name):
                version_folders.append(href)

        if not version_folders:
            log("   ❌ Could not identify version folders on the official server.")
            return

        # Sort folders by version number (descending)
        version_folders.sort(key=lambda s: [int(u) for u in s.strip('/').split('/')[-1].split('.')], reverse=True)
        latest_folder = version_folders[0]
        latest_version = latest_folder.strip('/').split('/')[-1]
        
        # 2. Enter the latest version folder and find the 64-bit zip
        folder_url = urllib.parse.urljoin(base_url, latest_folder)
        if not folder_url.endswith('/'):
            folder_url += '/'
        resp = requests.get(folder_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        zip_link = next((a['href'] for a in soup.find_all('a', href=True) if '64-bit' in a['href'] and a['href'].endswith('.zip')), None)
        
        if not zip_link:
            log(f"   ❌ Could not find 64-bit zip in version {latest_version}.")
            return
            
        download_url = urllib.parse.urljoin(folder_url, zip_link)
        log(f"   ⬇️  Downloading version {latest_version}...")
        asset_resp = requests.get(download_url, stream=True, timeout=120)
        asset_resp.raise_for_status()
        
        content = io.BytesIO(asset_resp.content)
        with zipfile.ZipFile(content) as z:
            # We only want specific tools to keep the binaries folder clean
            targets = ["mkvpropedit.exe", "mkvmerge.exe"]
            extracted_count = 0
            
            for zinfo in z.infolist():
                filename = os.path.basename(zinfo.filename)
                if filename.lower() in [t.lower() for t in targets]:
                    # Extract and flatten to binaries/
                    source = z.open(zinfo)
                    target_path = os.path.join(bin_dir, filename)
                    with open(target_path, "wb") as f:
                        shutil.copyfileobj(source, f)
                    extracted_count += 1
            
            if extracted_count > 0:
                log(f"   ✅ Successfully updated {extracted_count} MKVToolNix component(s) to {latest_version}.")
            else:
                log("   ⚠️  Download finished, but could not find target executables inside the ZIP.")
    except Exception as e:
        log(f"   ❌ MKVToolNix official update failed: {e}")

async def update_ffmpeg():
    """Queries BtbN/ffmpeg-builds for the latest auto-build (Windows only)."""
    if sys.platform != 'win32':
        # Linux users should use 'sudo apt install ffmpeg' or 'sudo pacman -S ffmpeg'
        return

    repo = "BtbN/ffmpeg-builds"
    bin_dir = os.path.join(get_base_dir(), "binaries")
    os.makedirs(bin_dir, exist_ok=True)
    
    log(f"🔄 Checking GitHub for latest FFmpeg (BtbN win64-gpl)...")
    
    try:
        # BtbN uses the standard 'latest' tag for their master builds
        api_url = f"https://api.github.com/repos/{repo}/releases"
        resp = requests.get(api_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()[0] # Grab the absolute latest auto-build
        tag = data.get("tag_name", "Unknown")
        assets = data.get("assets", [])
        
        # Target the shared GPL win64 zip
        download_url = next((a["browser_download_url"] for a in assets if "win64-gpl.zip" in a["name"]), None)
        
        if not download_url:
            log(f"   ❌ Could not find win64-gpl.zip in release {tag}.")
            return
            
        log(f"   ⬇️  Downloading version {tag}...")
        asset_resp = requests.get(download_url, stream=True, timeout=180) # FFmpeg is larger, higher timeout
        asset_resp.raise_for_status()
        
        content = io.BytesIO(asset_resp.content)
        with zipfile.ZipFile(content) as z:
            targets = ["ffmpeg.exe", "ffprobe.exe"]
            extracted_count = 0
            for zinfo in z.infolist():
                filename = os.path.basename(zinfo.filename)
                if filename.lower() in [t.lower() for t in targets]:
                    source = z.open(zinfo)
                    target_path = os.path.join(bin_dir, filename)
                    with open(target_path, "wb") as f:
                        shutil.copyfileobj(source, f)
                    extracted_count += 1
            
            if extracted_count > 0:
                log(f"   ✅ Successfully updated {extracted_count} FFmpeg component(s) to {tag}.")
    except Exception as e:
        log(f"   ❌ FFmpeg update failed: {e}")

def find_binary(name, config_key=None, local_only=False):
    """
    Robust binary discovery (Priority: Config -> Binaries Folder -> Root -> System Path).
    
    local_only=True restricts the search to config paths and local directories
    (./binaries/, ./).  Use this for dependency-checking so the GUI/CLI only
    reports binaries that are actually bundled/configured, not whatever happens
    to be installed globally on the system PATH.
    """
    base_dir = get_base_dir()
    is_win = sys.platform == 'win32'
    
    # 1. Config First (if available in global CONFIG)
    if config_key and 'CONFIG' in globals() and CONFIG.get(config_key):
        conf_path = CONFIG[config_key]
        if os.path.exists(conf_path):
            return conf_path
        # Relative to base dir
        abs_conf = os.path.join(base_dir, conf_path)
        if os.path.exists(abs_conf):
            return abs_conf
            
    # 2. Search Directories (Priority: Binaries Folder -> Root)
    exts = [".exe"] if is_win else [""]
    search_names = [name]
    if name == "ffmpeg" and is_win:
        search_names.append("ffmpeg_libfdk_aac_1")
        
    search_dirs = [
        os.path.join(base_dir, "binaries"), # 1. Binaries Subfolder
        base_dir                            # 2. Root Folder
    ]
    
    for d in search_dirs:
        if not os.path.exists(d): continue
        for s_name in search_names:
            for ext in exts:
                local_path = os.path.join(d, s_name + ext)
                if os.path.exists(local_path):
                    return os.path.abspath(local_path)
                    
    # 3. System Path (skipped when checking for bundled dependencies)
    if local_only:
        return None
    return shutil.which(name) or name


# ── Shared Binary Registry ───────────────────────────────────────────────────
REQUIRED_BINARIES = [
    {"name": "N_m3u8DL-RE", "binary": "N_m3u8DL-RE", "config_key": "nm3u8dl_re_path", "pkg_name": None, "updater": "nm3u8dl"},
    {"name": "FFmpeg",     "binary": "ffmpeg",     "config_key": "ffmpeg_path",     "pkg_name": "ffmpeg",     "updater": "ffmpeg"},
    {"name": "FFprobe",    "binary": "ffprobe",    "config_key": "ffprobe_path",    "pkg_name": "ffmpeg",     "updater": "ffmpeg"},
    {"name": "MKVPropEdit","binary": "mkvpropedit","config_key": "mkvpropedit_path","pkg_name": "mkvtoolnix", "updater": "mkvtoolnix"},
    {"name": "MKVMerge",   "binary": "mkvmerge",   "config_key": "mkvmerge_path",   "pkg_name": "mkvtoolnix", "updater": "mkvtoolnix"},
]

FALLBACK_BUNDLE_URL = "http://files.wmonte75.com:8080/Project_Binaries/capture_m3u8_binaries.zip"


def get_package_command(package_name: str) -> str:
    """Return the appropriate package manager command for the current platform."""
    if sys.platform == 'darwin':
        return f"brew install {package_name}"
    if shutil.which("apt") or shutil.which("apt-get"):
        return f"sudo apt install {package_name}"
    elif shutil.which("pacman"):
        return f"sudo pacman -S {package_name}"
    elif shutil.which("dnf"):
        return f"sudo dnf install {package_name}"
    elif shutil.which("zypper"):
        return f"sudo zypper install {package_name}"
    return f"Install {package_name} via your package manager"


def _is_auto_updatable(dep: dict) -> bool:
    """Determine whether this dep can be auto-downloaded on the current OS."""
    is_win = sys.platform == 'win32'
    updater = dep.get("updater")
    # N_m3u8DL-RE updater works on all platforms; ffmpeg/mkvtoolnix are Windows-only
    if updater == "nm3u8dl":
        return True
    return is_win and updater in ("ffmpeg", "mkvtoolnix")


def get_missing_binaries() -> list:
    """
    Scan REQUIRED_BINARIES and return a list of missing dependency dicts.
    Only checks local/config paths (ignores system PATH) so the app reports
    what is actually bundled, not what happens to be installed globally.
    Each dict contains: name, binary, config_key, updater, auto, command (if manual).
    """
    missing = []
    for dep in REQUIRED_BINARIES:
        path = find_binary(dep["binary"], dep["config_key"], local_only=True)
        if path and os.path.exists(path):
            continue
        entry = {
            "name": dep["name"],
            "binary": dep["binary"],
            "config_key": dep["config_key"],
            "updater": dep.get("updater"),
            "auto": _is_auto_updatable(dep),
        }
        pkg = dep.get("pkg_name")
        if pkg and not entry["auto"]:
            entry["command"] = get_package_command(pkg)
        missing.append(entry)
    return missing


async def download_fallback_binaries() -> list:
    """
    Download the consolidated fallback bundle and extract only the binaries
    we track into ./binaries/. Returns list of extracted filenames.
    """
    bin_dir = os.path.join(get_base_dir(), "binaries")
    os.makedirs(bin_dir, exist_ok=True)

    # Build a set of expected filenames (with and without .exe)
    expected = set()
    for dep in REQUIRED_BINARIES:
        expected.add(dep["binary"].lower())
        expected.add(dep["binary"].lower() + ".exe")

    log(f"🔄 Trying fallback bundle: {FALLBACK_BUNDLE_URL}")
    try:
        resp = requests.get(FALLBACK_BUNDLE_URL, stream=True, timeout=120)
        resp.raise_for_status()
        content = io.BytesIO(resp.content)

        extracted = []
        with zipfile.ZipFile(content) as z:
            for zinfo in z.infolist():
                if zinfo.is_dir():
                    continue
                filename = os.path.basename(zinfo.filename)
                if filename.lower() in expected:
                    target_path = os.path.join(bin_dir, filename)
                    with z.open(zinfo) as source, open(target_path, "wb") as f:
                        shutil.copyfileobj(source, f)
                    extracted.append(filename)

        if extracted:
            log(f"   ✅ Fallback bundle extracted: {', '.join(extracted)}")
        else:
            log("   ⚠️  Fallback bundle downloaded but no tracked binaries found inside.")
        return extracted
    except Exception as e:
        log(f"   ❌ Fallback bundle failed: {e}")
        return []


async def ensure_binaries(cli_mode: bool = True) -> list:
    """
    Unified binary resolver.
    • cli_mode=True  → prompts via terminal, auto-installs, returns final missing list.
    • cli_mode=False → meant for GUI; just returns the missing list (GUI handles its own dialog).
    """
    missing = get_missing_binaries()
    if not missing:
        return []

    is_win = sys.platform == 'win32'
    is_tty = sys.stdin.isatty()

    # ── Print summary ──
    log("\n" + "=" * 60)
    log("⚠️  Missing required binaries:")
    for dep in missing:
        if dep.get("auto"):
            status = "Auto-install available"
        else:
            status = dep.get("command", "Manual install required")
        log(f"   • {dep['name']}: {status}")
    log("=" * 60)

    auto_missing = [d for d in missing if d.get("auto")]

    # ── Try normal auto-installers ──
    if auto_missing and is_tty:
        if cli_mode:
            choice = input("\nAuto-install supported tools now? (y/n): ").strip().lower()
            run_auto = (choice == 'y')
        else:
            run_auto = False

        if run_auto:
            # Run each updater once (they cover multiple binaries)
            ran = set()
            for dep in auto_missing:
                updater = None
                for reg in REQUIRED_BINARIES:
                    if reg["name"] == dep["name"]:
                        updater = reg.get("updater")
                        break
                if not updater or updater in ran:
                    continue
                ran.add(updater)

                if updater == "nm3u8dl":
                    await update_nm3u8dl_re()
                elif updater == "ffmpeg":
                    await update_ffmpeg()
                elif updater == "mkvtoolnix":
                    await update_mkvtoolnix()

            missing = get_missing_binaries()
            auto_missing = [d for d in missing if d.get("auto")]

    # ── Fallback bundle (Windows only) ──
    if is_win and auto_missing and is_tty and cli_mode:
        choice = input(
            "\nOfficial downloads failed or incomplete. Try fallback bundle from wmonte75.com? (y/n): "
        ).strip().lower()
        if choice == 'y':
            await download_fallback_binaries()
            missing = get_missing_binaries()

    # ── Final report ──
    if missing:
        log("\n⚠️  Still missing after install attempts:")
        for dep in missing:
            cmd = dep.get("command", "")
            log(f"   • {dep['name']}" + (f": {cmd}" if cmd else ""))

    return missing


def _probe_resolution(url: str, referer: str = None, cookies: dict = None) -> Optional[Tuple[int, int]]:
    """
    Use ffprobe to detect video resolution from a URL (HLS master/media playlist or direct stream).
    Returns (width, height) or None on failure.
    """
    ffprobe_bin = find_binary("ffprobe", "ffprobe_path")
    if not ffprobe_bin or not os.path.exists(ffprobe_bin):
        log("   ⚠️  ffprobe binary not found; skipping probe fallback.")
        return None

    headers_list = [f"User-Agent: {USER_AGENT}"]
    if referer:
        headers_list.append(f"Referer: {referer}")
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers_list.append(f"Cookie: {cookie_str}")
    headers_str = "\r\n".join(headers_list)

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        "-headers", headers_str,
        "-analyzeduration", "5000000",
        "-probesize", "5000000",
        url,
    ]
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=creation_flags,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else ""
            if stderr:
                log(f"   ⚠️  ffprobe failed: {stderr[:200]}")
            return None
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None
        width = streams[0].get("width")
        height = streams[0].get("height")
        if width and height:
            return int(width), int(height)
    except Exception as e:
        log(f"   ⚠️  ffprobe exception: {e}")
    return None


def _bandwidth_to_height(bandwidth: int) -> int:
    """Roughly estimate video height from HLS bandwidth (bits/sec)."""
    # Approximate ranges for AVC; HEVC/VP9 may be lower but this is a safe fallback.
    if bandwidth >= 3_500_000:
        return 1080
    elif bandwidth >= 1_500_000:
        return 720
    elif bandwidth >= 800_000:
        return 480
    elif bandwidth >= 400_000:
        return 360
    else:
        return 240


def extract_base_url(url: str) -> str:
    """Return the scheme + netloc (base domain) from a URL."""
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def parse_master_manifest(master_url: str, referer: str = None, cookies: dict = None, fallback_text: str = None) -> Tuple[Optional[str], Optional[Dict[int, str]], Optional[int]]:
    """
    Fetch the master.m3u8 manifest and inspect variant streams for RESOLUTION + variant URLs.
    Falls back to bandwidth estimation and ffprobe probing if resolution tags are missing
    or if the manifest cannot be fetched at all.
    Returns (speed_cap, variants_dict, max_height) where variants_dict maps height -> variant URL.
    Returns (None, None, None) on failure.
    """
    if not master_url or not master_url.startswith("http"):
        return None, None, None

    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer

    variants: Dict[int, str] = {}
    heights: List[int] = []
    widths: List[int] = []
    bandwidths: List[Tuple[int, str]] = []  # (bandwidth, variant_url)
    is_media_playlist = False

    manifest_text = ""
    if fallback_text:
        manifest_text = fallback_text
        log("   📄 Using locally saved manifest for parsing.")
    else:
        text = ""
        fetch_failed = False
        try:
            session = requests.Session()
            if cookies:
                session.cookies.update(cookies)
            resp = session.get(master_url, headers=headers, timeout=10)
            if not resp.ok:
                log(f"   ⚠️  Manifest fetch returned HTTP {resp.status_code}; will try fallback.")
                fetch_failed = True
            else:
                text = resp.text
                # Strip BOM if present before checking header
                if not text.lstrip('\ufeff').strip().startswith("#EXTM3U"):
                    log("   ⚠️  Manifest response is not a valid M3U8; will try fallback.")
                    fetch_failed = True
        except Exception as e:
            log(f"   ⚠️  Manifest fetch failed: {e}; will try fallback.")
            fetch_failed = True

        if not fetch_failed and text:
            manifest_text = text

    if manifest_text:
        lines = manifest_text.splitlines()
        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Detect media playlist segments (not a master playlist)
            if line_stripped.startswith("#EXTINF"):
                is_media_playlist = True

            # --- Resolution parsing ---
            match = re.search(r'RESOLUTION=(\d+)x(\d+)', line_stripped)
            if match:
                width = int(match.group(1))
                height = int(match.group(2))
                widths.append(width)
                heights.append(height)
                # Scan forward for the next non-comment, non-empty line (variant URL)
                variant_url = None
                for j in range(i + 1, len(lines)):
                    candidate = lines[j].strip()
                    if not candidate:
                        continue
                    if candidate.startswith("#"):
                        continue
                    variant_url = candidate
                    break
                if variant_url:
                    variants[height] = urllib.parse.urljoin(master_url, variant_url)
                continue

            # --- Bandwidth parsing (fallback metadata) ---
            bw_match = re.search(r'BANDWIDTH=(\d+)', line_stripped)
            if bw_match:
                bandwidth = int(bw_match.group(1))
                variant_url = None
                for j in range(i + 1, len(lines)):
                    candidate = lines[j].strip()
                    if not candidate:
                        continue
                    if candidate.startswith("#"):
                        continue
                    variant_url = candidate
                    break
                if variant_url:
                    bandwidths.append((bandwidth, urllib.parse.urljoin(master_url, variant_url)))

    # --- Fallback 1: estimate height from bandwidth ---
    if not heights and bandwidths:
        log("   🔍 No RESOLUTION tags found; estimating from BANDWIDTH...")
        for bw, vurl in bandwidths:
            est_height = _bandwidth_to_height(bw)
            heights.append(est_height)
            widths.append(int(est_height * 16 / 9))
            if est_height not in variants:
                variants[est_height] = vurl
            # Prefer the higher bandwidth for the same estimated height
            else:
                existing_bw = next((b for b, u in bandwidths if u == variants[est_height]), 0)
                if bw > existing_bw:
                    variants[est_height] = vurl

    # --- Fallback 2: ffprobe the URL directly ---
    if not heights:
        log("   🔍 Probing resolution with ffprobe...")
        probe = _probe_resolution(master_url, referer, cookies)
        if probe:
            width, height = probe
            heights.append(height)
            widths.append(width)
            variants[height] = master_url
            log(f"   🎛️  ffprobe detected {width}w x {height}h stream → PRO speed cap")
        elif bandwidths:
            # ffprobe on master failed but we have bandwidth variants; try ffprobe on the highest bandwidth variant
            best_variant = max(bandwidths, key=lambda x: x[0])[1]
            probe = _probe_resolution(best_variant, referer, cookies)
            if probe:
                width, height = probe
                heights.append(height)
                widths.append(width)
                variants[height] = best_variant
                log(f"   🎛️  ffprobe detected {width}w x {height}h stream (via variant) → PRO speed cap")
        elif is_media_playlist:
            # Media playlist with no variants — already tried ffprobe on master_url above
            pass

    if not heights:
        log("   ⚠️  Could not detect resolution via manifest, bandwidth, or ffprobe.")
        return None, None, None

    # Use width for speed cap determination; fallback to height if no widths available
    max_height = max(heights)
    max_width = max(widths) if widths else int(max_height * 16 / 9)
    caps = {
        1920: CONFIG.get('speed_cap_1080', '2.5M'),
        1280: CONFIG.get('speed_cap_720',  '2M'),
        854:  CONFIG.get('speed_cap_480',  '1.5M'),
        640:  CONFIG.get('speed_cap_360',  '1M'),
    }

    if max_width >= 1920:
        speed = caps[1920]
    elif max_width >= 1280:
        speed = caps[1280]
    elif max_width >= 854:
        speed = caps[854]
    else:
        speed = caps[640]

    log(f"   🎛️  Detected {max_width}w stream → PRO speed cap: {speed}")
    return speed, variants, max_width


def get_speed_for_resolution(master_url: str, referer: str = None, cookies: dict = None, fallback_text: str = None) -> Optional[str]:
    """Convenience wrapper that returns only the speed cap."""
    speed, _, _ = parse_master_manifest(master_url, referer, cookies, fallback_text)
    return speed


def get_variant_for_resolution(master_url: str, prefer_height: int, referer: str = None, cookies: dict = None, fallback_text: str = None) -> Optional[str]:
    """
    Parse master.m3u8 and return the variant URL closest to prefer_height.
    Returns None if parsing fails or no variants found.
    """
    speed, variants, max_height = parse_master_manifest(master_url, referer, cookies, fallback_text)
    if not variants:
        return None

    if prefer_height in variants:
        log(f"   🎯 Preferred resolution {prefer_height}p found → using exact variant")
        return variants[prefer_height]

    # Find closest available height
    closest = min(variants.keys(), key=lambda h: abs(h - prefer_height))
    log(f"   🎯 Preferred {prefer_height}p not found → using closest: {closest}p")
    return variants[closest]

def setup_interface(config_data=None, log_cb=None, input_cb=None, status_cb=None, stop_cb=None):
    global CONFIG, LOG_CALLBACK, INPUT_CALLBACK, STATUS_CALLBACK, STOP_CALLBACK
    if config_data: CONFIG.update(config_data)
    if log_cb: LOG_CALLBACK = log_cb
    if input_cb: INPUT_CALLBACK = input_cb
    if status_cb: STATUS_CALLBACK = status_cb
    if stop_cb: STOP_CALLBACK = stop_cb

def log(msg, end="\n"):
    if LOG_CALLBACK: LOG_CALLBACK(str(msg) + end)
    else:
        # Use sys.__stdout__ directly to bypass redirection and avoid infinite recursion in CLI
        try:
            if sys.__stdout__:
                sys.__stdout__.write(str(msg) + end)
                sys.__stdout__.flush()
            else:
                print(msg, end=end)
        except:
            print(msg, end=end)

class RealTimeLogger(io.TextIOBase):
    """A file-like object that streams stdout/stderr to the global log() function instantly."""
    def write(self, s):
        if s:
            log(s, end="")
        return len(s)
    def flush(self):
        pass

def get_user_input(prompt):
    if INPUT_CALLBACK: return INPUT_CALLBACK(prompt)
    return input(prompt)

def report_status(msg):
    if STATUS_CALLBACK: STATUS_CALLBACK(msg)

def check_stop():
    if STOP_CALLBACK and STOP_CALLBACK():
        raise Exception("Stopped by user")

def get_ignored_iframes():
    """Reads ignored domains from ignore_iframes.txt next to the executable."""
    ignore_file = os.path.join(get_base_dir(), "ignore_iframes.txt")
    
    # Default list of domains to ignore
    default_ignores = [
        "cloudflare.com", "turnstile.com", "recaptcha.net",
        "dtscout.com", "lijit.com", "sharethis.com",
        "crwdcntrl.net", "intentiq.com", "doubleclick.net",
        "googlesyndication.com", "amazon-adsystem.com",
        "facebook.com", "google-analytics.com",
        "scorecardresearch.com", "quantserve.com",
        "adnxs.com", "rubiconproject.com", "pubmatic.com",
        "2embed.cc", "unpkg.com"
    ]

    if not os.path.exists(ignore_file):
        try:
            with open(ignore_file, "w", encoding="utf-8") as f:
                f.write("# Add domains or URL patterns to ignore when scanning for iframes (one per line)\n")
                f.write("# Lines starting with # are comments\n")
                for domain in default_ignores:
                    f.write(f"{domain}\n")
            log(f"   📝 Created default ignore list: {ignore_file}")
        except Exception as e:
            log(f"   ⚠️ Could not create {ignore_file}: {e}")
            return default_ignores

    ignored = []
    try:
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    ignored.append(line.lower())
    except Exception as e:
        log(f"   ⚠️ Error reading {ignore_file}: {e}")
        return default_ignores

    return ignored

class PluginManager:
    def __init__(self):
        self.plugins_dir = os.path.join(get_base_dir(), "plugins")
        os.makedirs(self.plugins_dir, exist_ok=True)

    def get_plugin_count(self):
        """Returns the number of valid plugin files found."""
        return len(self.get_plugin_names())

    def get_plugin_names(self):
        """Returns a list of valid plugin filenames."""
        if not os.path.exists(self.plugins_dir):
            return []
        return sorted([f for f in os.listdir(self.plugins_dir) if f.endswith(".py") and not f.startswith("_")])

    def run_plugins(self, file_path):
        """
        Scans "plugins" folder and executes .py files sequentially.
        Each plugin must have a process(file_path) function.
        """
        if not os.path.exists(self.plugins_dir):
            return file_path
        
        files = sorted([f for f in os.listdir(self.plugins_dir) if f.endswith(".py") and not f.startswith("_")])
        if not files:
            return file_path

        log(f"\n🔌 Scanning plugins in: {self.plugins_dir}")
        current_path = file_path

        for filename in files:
            filename_str: str = str(filename)
            plugin_path = os.path.join(self.plugins_dir, filename_str)
            try:
                plugin_name = filename_str[:-3] if filename_str.endswith(".py") else filename_str
                spec = importlib.util.spec_from_file_location(plugin_name, plugin_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    if spec.loader:
                        spec.loader.exec_module(module)
                    
                    if hasattr(module, "process"):
                        new_path = None
                        
                        try:
                            # Log the handoff for visibility (CLI & GUI)
                            log(f"🔌 [Plugin] Passing '{os.path.basename(current_path)}' to {filename_str}...")
                            
                            # Use RealTimeLogger to stream any print() calls inside the plugin directly to log()
                            rtl = RealTimeLogger()
                            with redirect_stdout(rtl):
                                new_path = module.process(current_path)
                        except Exception as e:
                            # If plugin fails during execution, log the error
                            log(f"   ❌ Plugin {filename_str} failed during execution: {e}")
                            continue # Move to the next plugin

                        # Check if the plugin did something (path changed)
                        if new_path and os.path.exists(new_path):
                            if new_path != current_path:
                                pass # Removed duplicate log message
                            current_path = new_path
                    else:
                        log(f"   ⚠️  Skipping {filename_str}: No 'process' function found.")
            except Exception as e:
                log(f"   ❌ Plugin {filename_str} failed to load: {e}")
        
        return current_path

class MasterM3U8Finder:
    """
    Main class responsible for:
    1. Launching a browser (Playwright).
    2. Intercepting network requests to find 'master.m3u8'.
    3. Handling iframes and clicking play buttons to trigger streams.
    4. Downloading the stream using yt-dlp.
    """
    def __init__(self):
        self.master_url: Optional[str] = None
        self.candidates: List[str] = []
        self.bad_candidates: Set[str] = set()
        self.title: str = "Unknown"
        self._verify_in_progress: bool = False
        
    def find_ytdlp(self):
        """Check if yt-dlp exists with priority: Config -> Root -> System Path"""
        # 1. Priority: Config
        config_path = CONFIG.get('ytdlp_path')
        if config_path and os.path.exists(config_path):
            return config_path
            
        # 2. Priority: Root folder & binaries subfolder
        base_dir = get_base_dir()
        is_win = os.name == 'nt'
        return find_binary("yt-dlp", "ytdlp_path")
    
    async def extract_title(self, page):
        """Extract video title from page with fast timeouts"""
        try:
            # 2s timeout to prevent hanging on missing tags
            og_title = await page.locator('meta[property="og:title"]').get_attribute('content', timeout=2000)
            if og_title and len(og_title) > 2:
                return og_title.strip()
        except:
            pass
            
        try:
            title = await page.title()
            title = re.sub(r'\s*[-|]\s*(Watch|Stream|Movie|Online|Free|HD|Full).*', '', title, flags=re.IGNORECASE)
            if title and len(title) > 2:
                return title.strip()
        except:
            pass
            
        try:
            h1 = await page.locator('h1').first.inner_text(timeout=2000)
            if h1 and len(h1) > 2:
                return h1.strip()
        except:
            pass
            
        try:
            # Quick check for JSON-LD without a long wait
            scripts = page.locator('script[type="application/ld+json"]')
            count = await scripts.count()
            for i in range(count):
                script = await scripts.nth(i).inner_text(timeout=1000)
                if '"name"' in script:
                    match = re.search(r'"name"\s*:\s*"([^"]+)"', script)
                    if match:
                        return match.group(1).strip()
        except:
            pass
            
        return "Unknown"
    
    def sanitize_filename(self, title):
        """Convert title to safe filename"""
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\.+', '.', safe)
        if len(safe) > 50:
            safe = safe[:50]
        return safe.strip()

    async def save_cookies(self, context):
        """Save session cookies to Netscape format for yt-dlp and store dict for requests."""
        try:
            cookie_file = os.path.join(get_log_dir(), 'cookies.txt')
            cookies = await context.cookies()
            self.cookies_dict = {c['name']: c['value'] for c in cookies}
            with open(cookie_file, 'w', encoding='utf-8') as f:
                f.write("# Netscape HTTP Cookie File\n")
                for c in cookies:
                    domain = c['domain']
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = c['path']
                    secure = 'TRUE' if c['secure'] else 'FALSE'
                    expires = int(c['expires']) if 'expires' in c and c['expires'] != -1 else 0
                    name = c['name']
                    value = c['value']
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
        except Exception as e:
            log(f"   ⚠️ Failed to save cookies: {e}")

    async def save_local_manifest(self, context, master_url: str) -> Optional[str]:
        """Fetch master.m3u8 via browser context and save locally for parsing/download."""
        if not master_url or not master_url.startswith("http"):
            return None
        try:
            response = await context.request.get(master_url, timeout=10000)
            if response.ok:
                text = await response.text()
                if text.lstrip('\ufeff').strip().startswith("#EXTM3U"):
                    temp_dir = os.path.join(get_base_dir(), "temp_downloads")
                    os.makedirs(temp_dir, exist_ok=True)
                    safe_name = self.sanitize_filename(self.title) if self.title and self.title != "Unknown" else "manifest"
                    local_path = os.path.join(temp_dir, f"{safe_name}_master.m3u8")
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(text)
                    self.local_manifest_path = local_path
                    self.base_url = extract_base_url(master_url)
                    log(f"   💾 Saved local manifest: {local_path}")
                    return local_path
                else:
                    log("   ⚠️  Browser manifest response is not a valid M3U8.")
            else:
                log(f"   ⚠️  Browser manifest fetch returned HTTP {response.status}.")
        except Exception as e:
            log(f"   ⚠️  Failed to save local manifest: {e}")
        return None

    async def get_working_url(self, context) -> Optional[str]:
        """Test all new candidates in parallel and return the first working one."""
        new_candidates = [u for u in self.candidates if u not in self.bad_candidates and u != self.master_url]
        if not new_candidates:
            return self.master_url if self.master_url else None

        async def check_url(url):
            if '{' in url or '}' in url:
                self.bad_candidates.add(url)
                return None
            try:
                # 2s timeout for fast rejection
                response = await context.request.get(url, timeout=2000)
                if response.ok:
                    return url
                self.bad_candidates.add(url)
            except:
                self.bad_candidates.add(url)
            return None

        log(f"   🧪 Testing {len(new_candidates)} candidate(s) in parallel...")
        results = await asyncio.gather(*[check_url(u) for u in new_candidates])
        
        for r in results:
            if r:
                log(f"   ✅ Verified working: {r[:80]}")
                return r
        
        return self.master_url if self.master_url else None

    async def run_nm3u8dl_re(self, binary_path, master_url, output_file, referer=None, status_prefix=""):
        """Execute download using N_m3u8DL-RE with native speed control logic."""
        check_stop()
        save_dir = os.path.dirname(output_file)
        save_name = os.path.splitext(os.path.basename(output_file))[0]

        # Handle native speed control based on GUI setting
        limit_speed = CONFIG.get('download_speed', 'Unlimited')
        download_url = master_url
        use_auto_select = True
        preferred = CONFIG.get('preferred_resolution', 'Auto')

        # Check for locally saved manifest from browser session
        local_manifest = getattr(self, 'local_manifest_path', None)
        base_url = getattr(self, 'base_url', None)
        manifest_text = None
        if local_manifest and os.path.exists(local_manifest):
            try:
                with open(local_manifest, 'r', encoding='utf-8') as f:
                    manifest_text = f.read()
            except Exception as e:
                log(f"   ⚠️  Failed to read local manifest: {e}")

        # Parse manifest once for both speed cap and resolution preference
        speed, variants, max_height = parse_master_manifest(master_url, referer, getattr(self, 'cookies_dict', None), fallback_text=manifest_text)

        if CONFIG.get('auto_speed_by_resolution', False):
            if speed:
                limit_speed = speed
            else:
                log(f"   ⚠️  Could not detect resolution. Fallback speed: {limit_speed}")

        if preferred != 'Auto' and variants:
            try:
                pref_height = int(preferred.replace('p', ''))
                if pref_height in variants:
                    download_url = variants[pref_height]
                    use_auto_select = False
                    log(f"   📐 Preferred resolution: {pref_height}p (exact match)")
                else:
                    closest = min(variants.keys(), key=lambda h: abs(h - pref_height))
                    download_url = variants[closest]
                    use_auto_select = False
                    log(f"   📐 Preferred {pref_height}p not found → using closest: {closest}p")
            except Exception as e:
                log(f"   ⚠️  Resolution preference failed: {e}")

        # Use local manifest + base-url if available and auto-selecting
        base_url_flag = []
        if local_manifest and base_url:
            if use_auto_select:
                download_url = local_manifest
                base_url_flag = ["--base-url", base_url]
                log(f"   📁 Using local manifest with base URL: {base_url}")
            else:
                # Variant URL is already absolute from parse_master_manifest
                pass

        cmd = [
            binary_path,
            download_url,
            "--save-dir", save_dir,
            "--save-name", save_name,
            "--binary-merge",
            "--del-after-done",
            "--download-retry-count", "20",
            '--mux-after-done', 'format=mkv:ffmpeg_args="-fflags +genpts"'
        ] + base_url_flag

        if use_auto_select:
            cmd.insert(2, "--auto-select")  # Insert after binary_path and URL

        # if referer:
        #     cmd.extend(["--header", f"Referer: {referer}"])

        if limit_speed != "Unlimited":
            # Speed control requires thread-count 1 for strict enforcement on many servers
            cmd.extend(["--thread-count", "1", "--max-speed", limit_speed])
            log(f"   🐢 Throttling enabled (GUI Limit: {limit_speed}). Using 1 thread.")
        else:
            cmd.extend(["--thread-count", "8"]) # Safer default

        # Link FFmpeg only for fragment muxing (assembly), not downloading
        ffmpeg_bin = find_binary("ffmpeg", "ffmpeg_path")
        if ffmpeg_bin:
            cmd.extend(["--ffmpeg-binary-path", ffmpeg_bin])

        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW

        log(f"\n⬇️  Starting download with N_m3u8DL-RE...")
        report_status(f"{status_prefix}Downloading (RE)...")

        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creation_flags
            )
            _active_download_processes.add(process)

            while True:
                check_stop()
                line = await process.stdout.readline()
                if not line: break
                text = line.decode('utf-8', errors='replace').strip()
                if text:
                    if '%' in text:
                        parts = text.split()
                        pct = next((p for p in parts if '%' in p), None)
                        if pct: report_status(f"{status_prefix}DL: {pct}")
                    log(f"\r   {text}", end="")
            
            await process.wait()
            return process.returncode == 0 and any(os.path.exists(os.path.join(save_dir, f"{save_name}{ext}")) for ext in ['.mkv', '.ts', '.mp4'])
        except Exception as e:
            log(f"❌ N_m3u8DL-RE download error: {e}")
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                except Exception:
                    pass
                _kill_process_tree(process.pid)
            return False
        finally:
            if process is not None:
                _active_download_processes.discard(process)
                # Safety net: if the process is still alive at this point, force-kill it
                if process.returncode is None:
                    try:
                        _kill_process_tree(process.pid)
                    except Exception:
                        pass

    async def capture(self, start_url: str, headless: bool = False) -> Tuple[Optional[str], str, Optional[str], str]:
        """
        The core logic:
        - Opens the URL.
        - Listens for network traffic matching .m3u8.
        - Scans iframes if not found immediately.
        - Returns the master URL and page title.
        """
        check_stop()
        report_status("Hunting...")
        log(f"🔍 Hunting for master.m3u8 at: {start_url}")
        mode = "hidden" if headless else "visible"
        log(f"🖥️  Browser mode: {mode}\n")
        
        # Initialize the ignore list file if it doesn't exist
        get_ignored_iframes()
        
        # Use a persistent user data directory to save cookies/session
        # Use get_base_dir() so the session folder lives next to the .exe, not in CWD
        if CUSTOM_SESSION_DIR:
            user_data_dir = os.path.join(get_base_dir(), CUSTOM_SESSION_DIR)
        else:
            user_data_dir = os.path.join(get_base_dir(), "browser_session")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        # Ensure browsers are downloaded before launching
        ensure_playwright_browsers()

        async with async_playwright() as p:
            if sys.platform.startswith('linux'):
                exec_path = get_browser_executable("firefox")
                if not exec_path:
                    return None, "", None, "error"
                # Use Firefox on Linux — different TLS/browser fingerprint bypasses
                # Cloudflare bot detection that blocks Chromium headless on Linux.
                # Windows/Mac continue to use Chromium (proven working, unchanged).
                context = await p.firefox.launch_persistent_context(
                    user_data_dir,
                    headless=headless,
                    executable_path=exec_path,
                    user_agent=USER_AGENT,
                    firefox_user_prefs={
                        # Block JS popup windows
                        "dom.popup_allowed_events": "",
                        "dom.disable_open_during_load": True,
                        # Suppress alerts/confirms/prompts
                        "dom.disable_beforeunload": True,
                        # Allow autoplay so the video starts without a click
                        "media.autoplay.default": 0,
                        "media.autoplay.blocking_policy": 0,
                        # Force all popup windows into tabs (easier to close)
                        "browser.link.open_newwindow": 3,
                        "browser.link.open_newwindow.restriction": 0,
                    }
                )

                # Auto-close any ad popups or new tabs that open
                def _close_extra_page(new_page):
                    asyncio.ensure_future(new_page.close())
                context.on("page", _close_extra_page)
            else:
                exec_path = get_browser_executable("chromium")
                if not exec_path:
                    return None, "", None, "error"
                # Chromium for Windows / Mac — proven working, unchanged
                context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=headless,
                    executable_path=exec_path,
                    viewport=None if not headless else {'width': 1280, 'height': 720},
                    user_agent=USER_AGENT,
                    bypass_csp=True,
                    args=[
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--autoplay-policy=no-user-gesture-required',
                        '--disable-blink-features=AutomationControlled',
                        # Only minimize in headless mode. In visible mode, a minimized window
                        # prevents Cloudflare from completing its JS challenge → about:blank
                        *(['--start-minimized'] if headless else []),
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-background-timer-throttling',
                    ],
                    ignore_default_args=["--enable-automation"]
                )
            
            page = context.pages[0] if context.pages else await context.new_page()

            # Optimzed Ad-blocking: Block images/media natively, and only check scripts for ads
            ad_regex = re.compile(r'googlesyndication|doubleclick|adnxs|ads-twitter|facebook|quantserve|taboola|outbrain|advertising|mathtag|dtscout|amazon-adsystem', re.IGNORECASE)
            
            async def block_junk(route):
                request = route.request
                if request.resource_type in ["image", "media", "font"]:
                    return await route.abort()
                
                url = request.url.lower()
                # Reinforce blocking of unpkg and ads
                if "unpkg.com" in url or ad_regex.search(url):
                    # log(f"   🚫 Blocked: {url[:60]}")
                    return await route.abort()
                
                await route.continue_()
            
            await context.route("**/*", block_junk)

            # Use a lightweight event listener instead of route interception.
            # context.on('request') fires for ALL requests across every page,
            # sub-iframe and popup in the session — without intercepting or
            # slowing them down. This catches m3u8 URLs from nested iframes.
            def on_request(request):
                url = request.url
                if 'master.m3u8' in url.lower() and url not in self.candidates:
                    log(f"   🔎 Candidate found: {url[:80]}")
                    self.candidates.append(url)

            context.on("request", on_request)

            # Inject stealth overrides at CONTEXT level so ALL pages/iframes get them.
            # This runs before any page scripts execute.
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer2', description: 'Portable Document Format plugin' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ]
                });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
                Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
                window.chrome = window.chrome || {};
                window.chrome.runtime = window.chrome.runtime || {};
                window.chrome.csi = function() { return { onloadT: Date.now(), pageT: Date.now(), startE: Date.now() }; };
                window.chrome.loadTimes = function() {
                    return {
                        commitLoadTime: performance.timing.domContentLoadedEventStart / 1000,
                        connectionInfo: 'h2',
                        finishDocumentLoadTime: performance.timing.domContentLoadedEventEnd / 1000,
                        finishLoadTime: performance.timing.loadEventEnd / 1000,
                        firstPaintAfterLoadTime: 0,
                        firstPaintTime: performance.timing.domContentLoadedEventStart / 1000,
                        navigationType: 'Other',
                        npnNegotiatedProtocol: 'h2',
                        requestTime: performance.timing.requestStart / 1000,
                        startLoadTime: performance.timing.navigationStart / 1000,
                        wasAlternateProtocolAvailable: false,
                        wasFetchedViaSpdy: true
                    };
                };

                // Fix HeadlessChrome in userAgent without recursion
                try {
                    const _origUA = navigator.userAgent;
                    if (_origUA.includes('HeadlessChrome')) {
                        Object.defineProperty(navigator, 'userAgent', {
                            get: () => _origUA.replace('HeadlessChrome', 'Chrome')
                        });
                    }
                } catch(e) {}
            """)
            
            log("Step 1: Hunting for master.m3u8...")
            # Optimization: Load page concurrently with proactive link sniffing and interaction.
            goto_task = asyncio.create_task(page.goto(start_url, wait_until="commit", timeout=60000))
            
            # Unified Hunting Loop: Polling, Clicking, and Iframe scanning all at once.
            self._verify_in_progress = False
            
            for tick in range(600): # Max 60s total hunting
                check_stop()
                
                # 1. Parallel verification of network candidates
                if not self._verify_in_progress:
                    new_candidates = [u for u in self.candidates if u not in self.bad_candidates and u != self.master_url]
                    if new_candidates:
                        self._verify_in_progress = True
                        try:
                            # Use a helper task to verify in background
                            async def run_verify():
                                try:
                                    res = await self.get_working_url(context)
                                    if res:
                                        self.master_url = res
                                finally:
                                    self._verify_in_progress = False
                            asyncio.create_task(run_verify())
                        except:
                            self._verify_in_progress = False
                
                if self.master_url:
                    break

                # 2. Proactive "Wake-up" clicks (Every 1s) to trigger JS links
                if tick > 0 and tick % 10 == 0:
                    try:
                        # Click the main body and any found iframes
                        await page.evaluate("() => document.body.click()")
                        iframes = page.locator('iframe')
                        count = await iframes.count()
                        for i in range(count):
                            await iframes.nth(i).click(timeout=100)
                    except:
                        pass

                # 3. Check for late-discovered candidates in HTML
                if tick % 30 == 0:
                    try:
                        content = await page.content()
                        matches = re.findall(r'https?://[^\s"\']+master\.m3u8[^\s"\']*', content, re.IGNORECASE)
                        for match in matches:
                            if match not in self.candidates:
                                self.candidates.append(match)
                    except:
                        pass
                
                await asyncio.sleep(0.1)

            # Cleanup navigation task
            if not goto_task.done():
                goto_task.cancel()

            if self.master_url:
                if self.title == "Unknown":
                    self.title = await self.extract_title(page)
                log(f"   ⚡ Master URL found! Finalizing...")
                await self.save_local_manifest(context, self.master_url)
                await self.save_cookies(context)
                await context.close()
                return self.master_url, self.title, start_url, "success"
            
            self.title = await self.extract_title(page)
            title_found = True
            log(f"📝 Page Title: {self.title}")
            
            if "404" in self.title or "Not Found" in self.title:
                log("   ❌ 404 Not Found detected.")
                await context.close()
                return None, self.title, start_url, "404"
            
            await asyncio.sleep(1)
            
            log("Step 2: Scanning for video iframes...")
            frames = page.frames
            iframe_urls = []
            
            # Load ignored domains live from the text file
            skip_patterns = get_ignored_iframes()
            
            for frame in frames:
                check_stop()
                try:
                    url = frame.url
                    if url and url != start_url and 'about:blank' not in url:
                        low_url = url.lower()
                        
                        # Skip domains/patterns in the ignore list
                        if any(x in low_url for x in skip_patterns):
                            continue

                        # Specifically ignore Cloudnestra ProRCP as requested
                        if 'cloudnestra.com/prorcp/' in low_url:
                            continue

                        # Only keep iframes that look like video embeds
                        video_patterns = [
                            'cloudnestra.com/rcp/', 'vidsrc', '/embed/',
                            'streamtape', 'doodstream', 'filemoon', 'mixdrop',
                            'upstream', 'vidplay', 'mycloud', 'mp4upload',
                        ]
                        
                        # If it's Cloudnestra, it MUST start with the RCP prefix
                        if 'cloudnestra.com' in low_url and not low_url.startswith('https://cloudnestra.com/rcp/'):
                            continue

                        if not any(x in low_url for x in video_patterns):
                            continue

                        log(f"   Found iframe: {url[:80]}")
                        iframe_urls.append(url)
                except:
                    pass
            
            if not self.master_url and iframe_urls:
                log(f"\nStep 3: Checking {len(iframe_urls)} iframe(s)...")

                if len(iframe_urls) > 1:
                    if headless:
                        log(f"⚠️  Multiple sources detected ({len(iframe_urls)}) in headless mode. Switching to visible...")
                        await context.close()
                        return None, self.title, start_url, "retry"

                    log(f"\n⚠️  Multiple sources detected ({len(iframe_urls)}). Needs human input.")
                    for i, url in enumerate(iframe_urls):
                        log(f"   {i+1}: {url}")

                    choice = get_user_input(f"\nSelect source (1-{len(iframe_urls)}) or Press Enter to scan all: ").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(iframe_urls):
                            iframe_urls = [iframe_urls[idx]]
                            log(f"   ✅ Selected: {iframe_urls[0]}")

                for iframe_url in iframe_urls:
                    check_stop()
                    if self.master_url:
                        break

                    log(f"   Navigating to: {iframe_url[:80]}...")
                    try:
                        await page.set_extra_http_headers({'Referer': start_url})
                        timeout = 10000 if headless else 15000
                        await page.goto(iframe_url, wait_until="domcontentloaded", timeout=timeout)

                        if headless and self.master_url:
                            break

                        iframe_title = await self.extract_title(page)
                        if iframe_title != "Unknown" and self.title == "Unknown":
                            self.title = iframe_title
                            log(f"   📝 Iframe Title: {self.title}")

                        try:
                            # More aggressive interaction including multiple clicks and keypress
                            await page.evaluate("""() => {
                                const video = document.querySelector('video');
                                if (video) { video.muted = true; video.play().catch(e => {}); }
                                const btn = document.querySelector('.vjs-big-play-button, .play-button, [class*="play"], [id*="play"]');
                                if (btn) { btn.click(); }
                                document.body.click();
                            }""")
                            # Extra fallback for persistent players
                            await page.mouse.click(640, 360)
                            await page.keyboard.press(' ') # Trigger play with space
                        except:
                            pass

                        # Also try Playwright native click
                        play_selectors = [
                            '.vjs-big-play-button', '.play-button',
                            'button[class*="play"]', '[class*="play"][role="button"]', 'video',
                        ]
                        for sel in play_selectors:
                            try:
                                if await page.locator(sel).count() > 0:
                                    await page.locator(sel).first.click(timeout=1000)
                                    break
                            except:
                                continue

                        if headless:
                            for tick in range(150):  # Max 15s wait, check every 0.1s
                                verified = await self.get_working_url(context)
                                if verified:
                                    self.master_url = verified
                                    break
                                if tick > 0 and tick % 30 == 0:
                                    try:
                                        await page.evaluate("""() => {
                                            const video = document.querySelector('video');
                                            if (video) { video.muted = true; video.play().catch(()=>{}); }
                                            const btn = document.querySelector('.vjs-big-play-button, .play-button, [class*="play"]');
                                            if (btn) btn.click();
                                        }""")
                                    except:
                                        pass
                                await asyncio.sleep(0.1)
                        else:
                            await asyncio.sleep(5)

                    except Exception as e:
                        log(f"      Error: {str(e)[:60]}")
                        continue
            
            if not self.master_url:
                log("Step 4: Checking page source...")
                content = await page.content()
                matches = re.findall(r'https?://[^\s"\']+master\.m3u8[^\s"\']*', content, re.IGNORECASE)
                for match in matches:
                    if match not in self.candidates:
                        log(f"   Found in HTML: {match}")
                        self.candidates.append(match)
                
                verified = await self.get_working_url(context)
                if verified:
                    self.master_url = verified
                    await self.save_local_manifest(context, self.master_url)

            referer = page.url if 'page' in locals() else ""
            status = "success" if self.master_url else "timeout"
            if self.master_url and not getattr(self, 'local_manifest_path', None):
                await self.save_local_manifest(context, self.master_url)
            await self.save_cookies(context)
            await context.close()
            return self.master_url, self.title, referer, status

    def set_download_speed(self, speed):
        self.download_speed = speed

def get_output_paths(title: str, url: str) -> Tuple[str, str]:
    finder = MasterM3U8Finder()
    safe_title = finder.sanitize_filename(title)
    
    season_match = re.search(r'[?&]season=(\d+)', url)
    episode_match = re.search(r'[?&]episode=(\d+)', url)
    
    if season_match:
        # TV Series
        base_dir = CONFIG.get('tv_dir')
        if not base_dir or base_dir == ".":
            base_dir = os.path.join(get_base_dir(), "TV")
            
        season_num = int(season_match.group(1))
        episode_num = int(episode_match.group(1)) if episode_match else 0
        
        # Clean the title to remove existing Season/Episode info
        # This prevents redundancy like "Series.S01E01.S01E01.mkv"
        clean_title = safe_title
        clean_title = re.sub(r'[. ]S\d+E\d+.*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'[. ]S\d+\.?$', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'[. ]Season[ .]\d+.*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'[ .(\)]+(\d{4})[ .(\)]+\1', r' (\1)', clean_title) # Fix duplicate years like (2024) (2024)
        clean_title = clean_title.strip()
        
        series_dir = os.path.join(base_dir, clean_title)
        final_dir = os.path.join(series_dir, f"Season {season_num:02d}")
        filename = f"{clean_title}.S{season_num:02d}E{episode_num:02d}.mkv"
    else:
        # Movie
        base_dir = CONFIG.get('movies_dir')
        if not base_dir or base_dir == ".":
            base_dir = os.path.join(get_base_dir(), "Movie")
            
        final_dir = os.path.join(base_dir, safe_title)
        filename = f"{safe_title}.mkv"
        
    return final_dir, filename

def scp_transfer(local_path: str, remote_path: str, host: str, username: str,
                 auth_type: str = "SSH Key", key_path: str = "", password: str = "") -> bool:
    """Upload a local file to a remote server via SFTP (SSH). Returns True on success."""
    if not PARAMIKO_AVAILABLE:
        log("⚠️  paramiko is not installed. Run: pip install paramiko")
        return False
    client = None
    try:
        log(f"\n📡 Connecting to {host} via SFTP...")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": host,
            "username": username,
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": 30,
        }
        if auth_type == "SSH Key":
            if not key_path or not os.path.exists(key_path):
                log(f"❌ SSH key not found: {key_path}")
                return False
            connect_kwargs["key_filename"] = key_path
        else:
            connect_kwargs["password"] = password
        client.connect(**connect_kwargs)
        sftp = client.open_sftp()
        remote_dir = os.path.dirname(remote_path).replace("\\", "/")
        if remote_dir:
            dirs_to_create = []
            d = remote_dir
            while d and d != "/":
                try:
                    sftp.stat(d)
                    break
                except IOError:
                    dirs_to_create.append(d)
                    d = os.path.dirname(d)
            for d in reversed(dirs_to_create):
                try:
                    sftp.mkdir(d)
                except IOError:
                    pass
        file_size = os.path.getsize(local_path)
        log(f"📤 Uploading {os.path.basename(local_path)} ({file_size / (1024*1024):.1f} MB)")
        last_pct = -1
        def progress_callback(sent, total):
            nonlocal last_pct
            pct = int((sent / total) * 100) if total else 0
            if pct != last_pct and pct % 10 == 0:
                log(f"   ↳ Upload progress: {pct}%")
                last_pct = pct
        sftp.put(local_path, remote_path, callback=progress_callback)
        sftp.close()
        log(f"✅ Remote transfer complete.")
        return True
    except paramiko.PasswordRequiredException:
        log("❌ SSH key requires a passphrase. Please use an unencrypted key or switch to Password auth.")
    except paramiko.AuthenticationException:
        log("❌ SFTP authentication failed. Check your username/password or SSH key.")
    except paramiko.SSHException as e:
        log(f"❌ SSH connection error: {e}")
    except Exception as e:
        log(f"❌ SFTP transfer failed: {e}")
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass
    return False


async def process_video(url: str, headless: bool = True, auto_mode: bool = True) -> Union[bool, str]:
    """
    Orchestrates the download process for a single URL:
    1. Converts IMDB URLs if needed.
    2. Runs MasterM3U8Finder to get the stream.
    3. Saves metadata to a .txt file.
    4. Runs N_m3u8DL-RE to download.
    5. Moves the file to the final destination on success.
    """
    check_stop()
    report_status("Analyzing...")
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Check for IMDB URL and convert to appropriate embed
    if "imdb.com/title/" in url:
        match = re.search(r'(tt\d+)', url)
        if match:
            imdb_id = match.group(1)
            log(f"\nℹ️  Detected IMDB URL. ID: {imdb_id}")
            
            # Fetch metadata to see if it's a series or movie
            meta = await get_imdb_info(imdb_id)
            if meta and meta.get('type') == 'tv':
                # For TV series, default to S1E1 if not specified in URL
                s = 1
                e = 1
                s_match = re.search(r'[?&]season=(\d+)', url)
                e_match = re.search(r'[?&]episode=(\d+)', url)
                if s_match: s = int(s_match.group(1))
                if e_match: e = int(e_match.group(1))
                
                template = CONFIG.get('tv_template', "https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}")
                url = template.replace("{imdb}", imdb_id).replace("{s}", str(s)).replace("{e}", str(e))
                log(f"   Detected TV Series. Using: {url}")
            else:
                template = CONFIG.get('movie_template', "https://vsembed.ru/embed/movie?imdb={imdb}")
                url = template.replace("{imdb}", imdb_id)
                log(f"   Converted to Movie: {url}")

    if not auto_mode:
        log("\nBrowser visibility options:")
        log("1. Hidden (headless) - Runs in background")
        log("2. Visible (normal) - Shows browser window")
        choice = get_user_input("\nSelect mode [1/2] (default: 1): ").strip() or "1"
        headless = (choice == "1")
    
    finder = MasterM3U8Finder()
    # Pass global config speed if available
    if CONFIG.get('download_speed'):
        finder.set_download_speed(CONFIG['download_speed'])
        
    master_url, title, referer, status = await finder.capture(url, headless=headless)
    
    if status == "404":
        log(f"❌ FAILED - 404 Not Found: {url}")
        return "404"
    
    safe_title = finder.sanitize_filename(title)
    
    log("\n" + "="*70)
    if master_url:
        log("✅ SUCCESS!")
        log("="*70)
        log(f"\n🎬 Title: {title}")
        log(f"🔗 URL: {master_url[:80]}...")
        
        nm3u8_path = find_binary("N_m3u8DL-RE", "nm3u8dl_re_path")
        
        # Setup Temp Directory
        script_dir = get_base_dir()
        temp_dir = os.path.join(script_dir, "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)

        final_dir, filename = get_output_paths(title, url)
        txt_filename = os.path.join(temp_dir, f"{os.path.splitext(filename)[0]}.txt")
        temp_filename = os.path.join(temp_dir, filename)
        final_filename = os.path.join(final_dir, filename)
            
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"URL: {master_url}\n")
            f.write(f"Filename: {final_filename}\n")
            
            # Generate the exact manual command based on current speed settings
            cmd_url = master_url
            auto_flag = "--auto-select"
            limit_speed = CONFIG.get('download_speed', 'Unlimited')

            # Load local manifest if browser saved one
            manifest_text = None
            if getattr(finder, 'local_manifest_path', None) and os.path.exists(finder.local_manifest_path):
                try:
                    with open(finder.local_manifest_path, 'r', encoding='utf-8') as f_manifest:
                        manifest_text = f_manifest.read()
                except Exception:
                    pass

            # Parse manifest once for both speed and variant selection
            speed, variants, _ = parse_master_manifest(master_url, referer, getattr(finder, 'cookies_dict', None), fallback_text=manifest_text)
            if speed and CONFIG.get('auto_speed_by_resolution', False):
                limit_speed = speed

            preferred = CONFIG.get('preferred_resolution', 'Auto')
            if preferred != 'Auto' and variants:
                try:
                    pref_height = int(preferred.replace('p', ''))
                    if pref_height in variants:
                        cmd_url = variants[pref_height]
                        auto_flag = ""
                    else:
                        closest = min(variants.keys(), key=lambda h: abs(h - pref_height))
                        cmd_url = variants[closest]
                        auto_flag = ""
                except Exception:
                    pass

            # If using local manifest for auto-select, reflect that in the command file
            local_manifest = getattr(finder, 'local_manifest_path', None)
            base_url = getattr(finder, 'base_url', None)
            base_url_cmd = ""
            if local_manifest and base_url and auto_flag == "--auto-select":
                cmd_url = local_manifest
                base_url_cmd = f" --base-url \"{base_url}\""

            ref_header = f" --header \"Referer: {referer}\"" if referer else ""
            
            if limit_speed != "Unlimited":
                speed_flags = f"--thread-count 1 --max-speed {limit_speed} --download-retry-count 10"
            else:
                speed_flags = "--thread-count 8 --download-retry-count 10"

            f.write(f"Command: N_m3u8DL-RE \"{cmd_url}\" --save-dir \"{temp_dir}\" --save-name \"{os.path.splitext(filename)[0]}\" --header \"User-Agent: {USER_AGENT}\"{ref_header} {auto_flag} --binary-merge --del-after-done{base_url_cmd} {speed_flags}\n")
            
        log(f"\n💾 Details saved to {txt_filename}")
        
        if nm3u8_path:
            log(f"\n🛠️  N_m3u8DL-RE found: {nm3u8_path}")
            
            if os.path.exists(final_filename):
                log(f"\n⚠️  File '{final_filename}' already exists.")
                if auto_mode:
                    log("   Auto-mode: Saving as new file to avoid overwrite.")
                    base, ext = os.path.splitext(final_filename)
                    final_filename = f"{base}_new{ext}"
                else:
                    choice = get_user_input("   Overwrite? (y/n): ").lower()
                    if choice != 'y':
                        base, ext = os.path.splitext(final_filename)
                        final_filename = f"{base}_new{ext}"
                        log(f"   Will save as: {final_filename}")
            
            if auto_mode:
                choice = 'y'
            else:
                choice = get_user_input("\n🚀 Start download now? (y/n): ").lower()

            if choice == 'y':
                # Extract Season/Episode for status updates
                status_prefix = ""
                s_match = re.search(r'[?&]season=(\d+)', url)
                e_match = re.search(r'[?&]episode=(\d+)', url)
                if s_match:
                    s_num = int(s_match.group(1))
                    e_num = int(e_match.group(1)) if e_match else 0
                    status_prefix = f"S{s_num:02d}E{e_num:02d} "

                # Apply the OS-aware Download Lock
                async with DownloadLock(title):
                    success = await finder.run_nm3u8dl_re(nm3u8_path, master_url, temp_filename, referer=referer, status_prefix=status_prefix)
                
                cookie_file = os.path.join(get_log_dir(), 'cookies.txt')
                if os.path.exists(cookie_file):
                    try:
                        os.remove(cookie_file)
                    except:
                        pass
                
                # Cleanup local manifest after download attempt
                local_manifest = getattr(finder, 'local_manifest_path', None)
                if local_manifest and os.path.exists(local_manifest):
                    try:
                        os.remove(local_manifest)
                        log(f"   🧹 Cleaned up local manifest.")
                    except:
                        pass
                
                if success:
                    # Run Plugins
                    plugin_manager = PluginManager()
                    new_temp_filename = plugin_manager.run_plugins(temp_filename)
                    
                    # Check if plugin moved the file out of temp_downloads
                    # If the returned path is NOT in temp_dir, assume plugin handled the final move
                    if not os.path.abspath(new_temp_filename).startswith(os.path.abspath(temp_dir)):
                        log(f"\n✅ Plugin handled final move. File located at: {new_temp_filename}")
                        # Cleanup txt file if it exists in the default location
                        if os.path.exists(txt_filename):
                            try:
                                os.remove(txt_filename)
                            except:
                                pass
                        # Cleanup empty default directory if we created it and it's empty
                        try:
                            curr_clean = os.path.abspath(final_dir)
                            # Try cleaning up two levels (e.g., Season folder then the dotted Series folder)
                            for _ in range(2):
                                if os.path.exists(curr_clean) and os.path.isdir(curr_clean) and not os.listdir(curr_clean):
                                    # Safety: Don't delete configured base dirs or program root
                                    if curr_clean in [os.path.abspath(CONFIG.get('tv_dir', '')), 
                                                     os.path.abspath(CONFIG.get('movies_dir', '')), 
                                                     os.path.abspath(os.path.join(get_base_dir(), "TV")), 
                                                     os.path.abspath(os.path.join(get_base_dir(), "Movie")),
                                                     os.path.abspath(get_base_dir())]:
                                        break
                                    os.rmdir(curr_clean)
                                    curr_clean = os.path.dirname(curr_clean)
                                else:
                                    break
                        except:
                            pass
                        report_status("Success")
                        return new_temp_filename
                    
                    temp_filename = new_temp_filename
                    # Update final filename extension if plugin changed it
                    _, ext_temp = os.path.splitext(temp_filename)
                    base_final, ext_final = os.path.splitext(final_filename)
                    if ext_temp.lower() != ext_final.lower():
                        final_filename = f"{base_final}{ext_temp}"

                    log(f"\n🚚 Moving file to final destination...")
                    log(f"   From: {temp_filename}")
                    log(f"   To:   {final_filename}")
                    try:
                        os.makedirs(final_dir, exist_ok=True)
                        if os.path.exists(final_filename):
                            os.remove(final_filename)
                        shutil.move(temp_filename, final_filename)
                        log(f"✅ Move complete.")

                        # --- Remote SFTP Transfer ---
                        if CONFIG.get("scp_enabled"):
                            try:
                                scp_host = CONFIG.get("scp_host", "").strip()
                                scp_username = CONFIG.get("scp_username", "").strip()
                                scp_auth_type = CONFIG.get("scp_auth_type", "SSH Key")
                                scp_key_path = CONFIG.get("scp_key_path", "")
                                scp_password = CONFIG.get("scp_password", "")
                                scp_delete_local = CONFIG.get("scp_delete_local", False)
                                if scp_host and scp_username:
                                    local_movies = CONFIG.get("movies_dir", "")
                                    if not local_movies or local_movies == ".":
                                        local_movies = os.path.join(get_base_dir(), "Movies")
                                    local_tv = CONFIG.get("tv_dir", "")
                                    if not local_tv or local_tv == ".":
                                        local_tv = os.path.join(get_base_dir(), "TV")
                                    remote_movies = CONFIG.get("scp_remote_movies_dir", "")
                                    remote_tv = CONFIG.get("scp_remote_tv_dir", "")
                                    remote_base = None
                                    local_base = None
                                    norm_final = os.path.normpath(final_filename)
                                    if remote_movies and norm_final.startswith(os.path.normpath(local_movies)):
                                        remote_base = remote_movies
                                        local_base = local_movies
                                    elif remote_tv and norm_final.startswith(os.path.normpath(local_tv)):
                                        remote_base = remote_tv
                                        local_base = local_tv
                                    if remote_base and local_base:
                                        rel_path = os.path.relpath(final_filename, local_base)
                                        remote_path = remote_base.replace("\\", "/").rstrip("/") + "/" + rel_path.replace("\\", "/")
                                        scp_ok = scp_transfer(
                                            final_filename, remote_path,
                                            scp_host, scp_username,
                                            auth_type=scp_auth_type,
                                            key_path=scp_key_path,
                                            password=scp_password
                                        )
                                        if scp_ok and scp_delete_local:
                                            try:
                                                os.remove(final_filename)
                                                log(f"🗑️  Local file deleted after remote transfer.")
                                            except Exception as e:
                                                log(f"⚠️  Could not delete local file: {e}")
                                    else:
                                        log("⚠️  SCP enabled but could not map local path to remote base directory. Check remote path settings.")
                            except Exception as e:
                                log(f"⚠️  Remote transfer error (local file kept): {e}")

                        if os.path.exists(txt_filename):
                            try:
                                os.remove(txt_filename)
                            except:
                                pass
                                
                        report_status("Success")
                        return final_filename
                    except Exception as e:
                        log(f"❌ Error moving file: {e}")
                        report_status("Ready")
                        return False
                
                if not success:
                    log("\n❌ N_m3u8DL-RE download failed.")
                    report_status("Ready")
                else:
                    report_status("Success")
                return success
            else:
                report_status("Ready")
                return True
        else:
            log("\n❌ N_m3u8DL-RE not found.")
            report_status("Ready")
            return True
    else:
        if headless:
            log("\n⚠️  Headless capture failed. Retrying in visible mode to bypass Cloudflare...")
            return await process_video(url, headless=False, auto_mode=auto_mode)
        else:
            log("\n❌ Failed to capture stream.")
            report_status("Ready")
            return False

# In-memory cache for IMDB metadata
IMDB_CACHE: Dict[str, Any] = {}

def flush_imdb_cache():
    """Clear the IMDB metadata cache."""
    global IMDB_CACHE
    IMDB_CACHE.clear()
    # log("🧹 IMDB cache flushed.")

async def get_imdb_info(imdb_id: str, page=None) -> Optional[Dict[str, Any]]:
    if imdb_id in IMDB_CACHE:
        res = IMDB_CACHE[imdb_id]
        # Only return cache if it's a movie or a TV show with ALREADY fetched seasons
        # (search hints only provide 'type' and 'title')
        if res.get('type') == 'movie' or (res.get('type') == 'tv' and 'seasons' in res):
            # log(f"🚀 Using cached metadata for: {imdb_id}")
            return res
        
    url = f"https://www.imdb.com/title/{imdb_id}/"
    log(f"🕵️  Scanning IMDB: {url}")
    
    async def _extract(p):
        # Enable resource blocking for this page
        await p.route("**/*", block_resources)
        
        try:
            # Use domcontentloaded + shorter timeout for faster metadata extraction
            # IMDB is heavy with ads/tracking that cause full 'load' to timeout.
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"   ⚠️ IMDB load warning: {str(e)[:100]}")
            # We continue anyway as the title and basic meta might already be in the DOM
        
        title = await p.title()
        title = re.sub(r'\s*[-|]\s*IMDb.*', '', title).strip()
        
        # Fallback if title is empty
        if not title:
            try:
                title = await p.locator('h1').first.inner_text()
            except:
                title = "Unknown"
        
        # Extract Year / Year Range
        year = ""
        full_meta_text = ""
        try:
            # Get metadata items text (Year is usually 1st or 2nd item)
            meta_items = await p.locator('[data-testid="hero-title-block__metadata"] li').all_inner_texts()
            full_meta_text = " | ".join(meta_items).lower()
            for text in meta_items[:3]:
                match = re.search(r'\b(19|20)\d{2}\b', text)
                if match:
                    year = match.group(0)
                    break
        except:
            pass
        
        if year and year not in title:
            title = f"{title} ({year})"
        
        # Check for series markers
        is_tv = False
        if await p.locator('text=Episode Guide').count() > 0 or \
           await p.locator('a[href*="episodes"]').count() > 0 or \
           await p.locator('[data-testid="hero-subnav-bar-season-episode-picker"]').count() > 0:
            is_tv = True
        
        # Additional robust checks for keywords and year ranges
        if not is_tv:
            is_tv_kw = any(kw in full_meta_text for kw in ['tv series', 'tv mini-series', 'tv special', 'tv episode', 'tv movie', 'tv-series'])
            has_series_kw = 'series' in full_meta_text or 'episode' in full_meta_text or 'season' in full_meta_text
            has_range = re.search(r'\d{4}[–-]\d*', full_meta_text)
            
            if is_tv_kw or has_series_kw or has_range:
                is_tv = True
        
        if not is_tv:
            res = {'type': 'movie', 'title': title}
            IMDB_CACHE[imdb_id] = res
            return res
        
        total_episodes = 0
        try:
            ep_subtext = p.locator('[data-testid="episodes-header"] .ipc-title__subtext')
            if await ep_subtext.count() > 0:
                text = await ep_subtext.first.inner_text()
                if text.isdigit():
                    total_episodes = int(text)
        except:
            pass
        
        log("   📺 TV Series detected. Fetching season info...")
        await p.goto(f"https://www.imdb.com/title/{imdb_id}/episodes", wait_until="domcontentloaded", timeout=45000)
        
        # Wait for season selector to load
        try:
            await p.wait_for_selector('#bySeason, [data-testid="select-season"]', timeout=5000)
        except:
            pass

        seasons = []
        options = await p.locator('#bySeason option').all()
        if not options:
            options = await p.locator('[data-testid="select-season"] option').all()
            
        for opt in options:
            val = await opt.get_attribute('value')
            if val and val.isdigit():
                seasons.append(int(val))
        
        # Fallback: Check for season links if dropdown is missing
        if not seasons:
            links = await p.locator('a[href*="season="]').all()
            for link in links:
                href = await link.get_attribute('href')
                if href:
                    match = re.search(r'season=(\d+)', href)
                    if match:
                        seasons.append(int(match.group(1)))
        
        total_seasons = max(seasons) if seasons else 1
        res = {'type': 'tv', 'title': title, 'seasons': total_seasons, 'total_episodes': total_episodes}
        IMDB_CACHE[imdb_id] = res
        return res

    if page:
        return await _extract(page)

    # Ensure browsers are downloaded before launching
    ensure_playwright_browsers()
    
    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            exec_path = get_browser_executable("firefox")
            if not exec_path:
                return None
            browser = await p.firefox.launch(headless=True, executable_path=exec_path)
        else:
            exec_path = get_browser_executable("chromium")
            if not exec_path:
                return None
            browser = await p.chromium.launch(headless=True, executable_path=exec_path)
        
        new_page = await browser.new_page(user_agent=USER_AGENT)
        try:
            res = await _extract(new_page)
            await browser.close()
            return res
        except Exception as e:
            log(f"⚠️  IMDB Scan failed: {e}")
            await browser.close()
            return None
async def get_season_episodes(imdb_id: str, season: int, page=None) -> int:
    url = f"https://www.imdb.com/title/{imdb_id}/episodes?season={season}"
    log(f"   📖 Fetching episode count for Season {season}...")
    
    async def _extract(p):
        await p.route("**/*", block_resources)
        try:
            await p.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await p.wait_for_selector('.list_item, article.episode-item-wrapper, [data-testid="episodes-browse-episodes"]', timeout=5000)
            except:
                pass
                
            count = await p.locator('.list_item').count()
            if count == 0:
                count = await p.locator('article.episode-item-wrapper').count()
            if count == 0:
                count = await p.locator('[data-testid="episodes-browse-episodes"] .ipc-title__text').count()
            
            return count if count > 0 else 0
        except Exception as e:
            log(f"   ⚠️ Failed to load season {season}: {e}")
            return 0

    if page:
        return await _extract(page)

    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            exec_path = get_browser_executable("firefox")
            if not exec_path: return 0
            browser = await p.firefox.launch(headless=True, executable_path=exec_path)
        else:
            exec_path = get_browser_executable("chromium")
            if not exec_path: return 0
            browser = await p.chromium.launch(headless=True, executable_path=exec_path)
        
        new_page = await browser.new_page(user_agent=USER_AGENT)
        try:
            count = await _extract(new_page)
            await browser.close()
            return count
        except:
            await browser.close()
            return 0

def _kill_process_tree(pid: int):
    """Kill a process and all its descendants. Windows-aware."""
    if sys.platform == 'win32':
        try:
            # taskkill /T kills the process and all child processes
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def terminate_all_downloads():
    """Force-terminate all active N_m3u8DL-RE download processes and clean up the download lock."""
    for proc in list(_active_download_processes):
        try:
            if proc.returncode is None:
                # Try graceful terminate first, then force-kill the whole tree
                try:
                    proc.terminate()
                except Exception:
                    pass
                _kill_process_tree(proc.pid)
                log("🛑 Terminated active download process.")
        except Exception:
            pass
    _active_download_processes.clear()

    # Remove our download lock so the next session doesn't wait on a dead PID
    lock_file = os.path.join(get_log_dir(), "download.lock")
    with suppress(OSError):
        if os.path.exists(lock_file):
            with open(lock_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content.startswith(f"{os.getpid()}|"):
                os.remove(lock_file)
                log("🔒 Download lock removed.")

def clear_session(reason="", target_dir=None):
    if target_dir:
        session_dir = os.path.join(get_base_dir(), target_dir)
    else:
        session_dir = os.path.join(get_base_dir(), "browser_session")
        
    if os.path.exists(session_dir):
        message = f"\n🧹 Clearing browser session"
        if reason:
            message += f" ({reason})"
        message += "..."
        log(message)
        try:
            shutil.rmtree(session_dir)
            log("   ✅ Session cleared.")
        except Exception as e:
            log(f"   ⚠️ Failed to clear session: {e}")

def cleanup_stale_browser_session(session_dir_name: str = "browser_session"):
    """
    Deletes the browser session folder if it exists and is older than 0.5 hours (30 minutes).
    """
    full_session_path = os.path.join(get_base_dir(), session_dir_name)
    
    if os.path.exists(full_session_path):
        with suppress(Exception): # Suppress errors during cleanup to not block startup
            mtime = os.path.getmtime(full_session_path)
            modified_time = datetime.fromtimestamp(mtime)
            current_time = datetime.now()
            
            if current_time - modified_time > timedelta(minutes=30):
                log(f"\n🗑️  Stale browser session folder detected (older than 0.5 hours). Deleting: {full_session_path}")
                clear_session(reason="stale session", target_dir=session_dir_name)

def load_config():
    script_dir = get_base_dir()
    config_file = os.path.join(script_dir, "config.json")
    log_messages = []
    default_config = {
        "movies_dir": "",
        "tv_dir": "",
        "download_speed": DOWNLOAD_SPEED,
        "min_cooldown": COOLDOWN_RANGE[0],
        "max_cooldown": COOLDOWN_RANGE[1],
        "subtitle_langs": "all",
        "session_reset_count": 5,
        "movie_template": "https://vsembed.ru/embed/movie?imdb={imdb}",
        "tv_template": "https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}",
        "auto_speed_by_resolution": False,
        "speed_cap_1080": "2.5M",
        "speed_cap_720": "2M",
        "speed_cap_480": "1.5M",
        "speed_cap_360": "1M",
        "nm3u8dl_re_path": "",
        "mkvmerge_path": "",
        "preferred_resolution": "Auto",
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
                log_messages.append("⚙️  Loaded config.json")
        except Exception as e:
            log_messages.append(f"⚠️  Error loading config.json: {e}")
        
    return default_config, log_messages

def save_config(new_data):
    """
    Safely saves configuration by merging with the existing file on disk.
    This prevents overwriting manual edits (like API keys) with stale memory data.
    """
    script_dir = get_base_dir()
    config_file = os.path.join(script_dir, "config.json")
    
    # 1. Load latest data from disk
    current_disk_config = {}
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                current_disk_config = json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading config for merge: {e}")

    # 2. Merge new data into disk data
    current_disk_config.update(new_data)
    
    # 3. Write back atomically
    temp_file = config_file + ".tmp"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(current_disk_config, f, indent=4)
        # os.replace is atomic on both Windows and modern Unix systems.
        os.replace(temp_file, config_file)
        return True
    except Exception as e:
        print(f"❌ Failed to save config: {e}")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except: pass
        return False

async def search_imdb(query, filter_type='all', page=None):
    """
    Searches IMDB for a query and returns a list of candidates using Playwright.
    """
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.imdb.com/find/?q={encoded_query}"
    
    log(f"🔎 Searching IMDB for: {query} (Encoded: {encoded_query})")
    log(f"   🔗 Link: {url}")

    async def _extract(p):
        await p.route("**/*", block_resources)
        try:
            await p.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"   ⚠️ IMDB Search load warning: {str(e)[:100]}")
        
        results = []
        try:
            # Wait for results to appear
            await p.wait_for_selector('.ipc-metadata-list-summary-item', timeout=10000)
            items = await p.locator('.ipc-metadata-list-summary-item').all()
            
            for item in items:
                try:
                    link_el = item.locator('a.ipc-title-link-wrapper')
                    if await link_el.count() == 0:
                        continue
                        
                    title = await link_el.inner_text()
                    href = await link_el.get_attribute('href')
                    if not href: continue
                    
                    clean_href = href.split('?')[0]
                    link = "https://www.imdb.com" + clean_href if clean_href.startswith('/') else clean_href
                    
                    img_el = item.locator('img').first
                    img_url = await img_el.get_attribute('src') if await img_el.count() > 0 else "No Image"
                    
                    # Log in the requested format
                    log(f"{img_url}: {title} - {link}")
                    
                    match = re.search(r'(tt\d+)', link)
                    if not match: continue
                    imdb_id = match.group(1)

                    # 1. Clean Meta String for GUI Display
                    meta_texts = []
                    # Try to find all metadata items under the item
                    # Standard IMDB search result items have .ipc-inline-list__item or .cli-title-metadata-item
                    meta_texts = await item.locator('.ipc-inline-list__item').all_inner_texts()
                    if not meta_texts:
                        meta_texts = await item.locator('.cli-title-metadata-item').all_inner_texts()
                    
                    # Clean and remove title if it accidentally got in
                    meta_texts = [t.strip() for t in meta_texts if t.strip() and t.lower() != title.lower()]
                    
                    # Extract Year, Rating, and type-label
                    year_val = ""
                    rating_val = ""
                    type_label = ""
                    
                    for t in meta_texts:
                        # Year: 4 digits, possibly with range
                        if re.search(r'\d{4}', t):
                            if not year_val: year_val = t
                        # Rating: Standard IMDB rating keywords
                        elif any(r in t for r in ['TV-', 'PG', 'G', 'R', 'NC-17', 'Approved', 'U', '12', '15', '18']):
                            if not rating_val: rating_val = t
                        # Type: Series, Movie, Special, Episode, Podcast
                        elif any(kw in t.lower() for kw in ['series', 'movie', 'special', 'episode', 'podcast']):
                            if not type_label: type_label = t
                    
                    # 2. Robust Type Detection (Check ALL text in the item)
                    media_type = 'movie'
                    item_text = await item.inner_text()
                    low_text = item_text.lower()
                    
                    # Keywords and patterns for logic
                    is_tv_kw = any(kw in low_text for kw in ['tv series', 'tv mini-series', 'tv mini series', 'tv special', 'tv episode', 'tv movie', 'tv-series', 'podcast series', 'mini series'])
                    has_series_kw = 'series' in low_text or 'episode' in low_text or 'season' in low_text
                    has_range = re.search(r'\d{4}[–-]\d*', low_text)
                    
                    if is_tv_kw or has_series_kw or has_range:
                        media_type = 'tv'
                        if not type_label: 
                            if 'mini-series' in low_text or 'mini series' in low_text: type_label = "TV Mini Series"
                            else: type_label = "TV Series"
                    else:
                        if not type_label: type_label = "Movie"

                    # 3. Format for display
                    display_title = f"{title.strip()} ({year_val})" if year_val else title.strip()
                    # User wanted: rating - Type of media
                    display_meta = f"{rating_val} - {type_label}" if rating_val else type_label
                    
                    # Proactively cache type
                    IMDB_CACHE[imdb_id] = {'type': media_type, 'title': title.strip()}
                    
                    results.append({
                        'title': display_title, 
                        'url': link, 
                        'img': img_url, 
                        'id': imdb_id, 
                        'meta': display_meta, 
                        'type': media_type
                    })
                except Exception as e:
                    # log(f"   ⚠️ Error extracting item: {e}")
                    continue
                
                if len(results) >= 20:
                    break
        except Exception as e:
            log(f"❌ Error during IMDB search: {e}")
            
        if not results:
            log("❌ No results found or IMDB blocked the search.")
        else:
            log(f"✅ Found {len(results)} results.")
        return results

    if page:
        return await _extract(page)

    ensure_playwright_browsers()
    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            exec_path = get_browser_executable("firefox")
            if not exec_path: return []
            browser = await p.firefox.launch(headless=True, executable_path=exec_path)
        else:
            exec_path = get_browser_executable("chromium")
            if not exec_path: return []
            browser = await p.chromium.launch(headless=True, executable_path=exec_path)
        
        new_page = await browser.new_page(user_agent=USER_AGENT)
        try:
            res = await _extract(new_page)
            await browser.close()
            return res
        except Exception as e:
            log(f"❌ Error in Search session: {e}")
            await browser.close()
            return []

async def check_embed_availability(imdb_id: str, is_tv: bool) -> tuple[bool, str]:
    """
    Checks if a title is actually available on the embed servers by verifying the page title.
    Returns (is_available, status_message)
    """
    if is_tv:
        template = CONFIG.get('tv_template', "https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}")
        url = template.replace("{imdb}", imdb_id).replace("{s}", "1").replace("{e}", "1")
    else:
        template = CONFIG.get('movie_template', "https://vsembed.ru/embed/movie?imdb={imdb}")
        url = template.replace("{imdb}", imdb_id)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Use requests with a reasonable timeout
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return False, f"Not Found (HTTP {response.status_code})"
            
        soup = BeautifulSoup(response.content, "html.parser")
        title_tag = soup.find("title")
        if not title_tag:
            return False, "No Content Found"
            
        page_title = title_tag.get_text().strip()
        low_title = page_title.lower()
        
        # Check for explicit failure labels
        if "404" in low_title or "not found" in low_title:
            return False, "Not Found (404 Page)"
            
        # If it's just the domain name or too short, it's likely a soft failure
        if len(page_title) < 5 or low_title == "vsembed" or low_title == "vidsrc":
             return False, "Invalid Title / Soft 404"
             
        return True, f"Available: {page_title}"
    except Exception as e:
        return False, f"Check Failed: {str(e)[:50]}"

def get_title_details(url):
    """
    Fetches details (Year) from a specific IMDB title page.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.5"
    }
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            
            year = ""
            # Try to find year in metadata list
            meta_ul = soup.find('ul', attrs={'data-testid': 'hero-title-block__metadata'})
            if meta_ul:
                for li in meta_ul.find_all('li'):
                    text = li.get_text()
                    if re.search(r'\b(19|20)\d{2}\b', text):
                        year = text
                        break
            
            return {'year': year}
    except:
        pass
    return {'year': ''}

async def scrape_imdb_chart(chart_type, limit=250, page=None):
    """
    Scrapes IMDB Top 250 lists (Movies or TV).
    - Extracts links.
    - Saves them to a text file for batch processing.
    """
    if chart_type == 'movie':
        url = "https://www.imdb.com/chart/top/"
        output_file = "imdb_top_250_movies.txt"
        label = "Top 250 Movies"
    else:
        url = "https://www.imdb.com/chart/toptv/"
        output_file = "imdb_top_250_tv.txt"
        label = "Top 250 TV Shows"
    
    log(f"🚀 Starting scrape of: {label}")
    log(f"   URL: {url}")
    
    async def _extract(p):
        await p.route("**/*", block_resources)
        try:
            await p.goto(url, timeout=60000)
            try:
                await p.wait_for_selector('.ipc-metadata-list-summary-item', timeout=10000)
            except:
                pass
            
            # Infinite Scroll Support: IMDb loads in batches. Scroll until we see the target count.
            log("   Scrolling to load full list...")
            max_scroll_attempts = 15
            for attempt in range(max_scroll_attempts):
                # Press End to jump to bottom and trigger load
                await p.keyboard.press("End")
                await asyncio.sleep(1.5) # Wait for Batch to load
                
                # Check current count
                current_count = await p.locator('.ipc-metadata-list-summary-item').count()
                log(f"   🔄 Batch {attempt + 1}: Loaded {current_count} items...")
                
                if current_count >= 250:
                    log(f"   ✅ All {current_count} items loaded.")
                    break

            # Extract items to get both title and year metadata
            items = await p.locator('.ipc-metadata-list-summary-item').all()
            log(f"   Extracting details from {len(items)} items...")
            
            results = []
            if items:
                if limit and len(items) > limit:
                    items = items[:limit]
                
                for idx, item in enumerate(items):
                    try:
                        if (idx + 1) % 50 == 0:
                            log(f"   ✍️  Processing {idx + 1}/{len(items)}...")
                        link_el = item.locator('a.ipc-title-link-wrapper')
                        title = await link_el.inner_text()
                        href = await link_el.get_attribute('href')
                        
                        # Clean title (remove "1. " rank)
                        title = re.sub(r'^\d+[\.\s]+', '', title).strip()
                        
                        # Extract metadata from the metadata items
                        meta_elements = await item.locator('.cli-title-metadata-item').all()
                        year = ""
                        runtime = ""
                        rating = ""
                        
                        for m_el in meta_elements:
                            text = (await m_el.inner_text()).strip()
                            if re.search(r'^\d{4}$', text):
                                year = text
                            elif 'h' in text or 'm' in text:
                                runtime = text
                            else:
                                rating = text
                        
                        # Extract Star Rating
                        stars = ""
                        try:
                            star_el = item.locator('.ipc-rating-star--imdb')
                            star_text = await star_el.inner_text()
                            stars_match = re.search(r'(\d+\.\d+)', star_text)
                            if stars_match:
                                stars = stars_match.group(1)
                        except:
                            pass

                        # Format title: Title (Year) - [Runtime] - [Rating] - ★Stars
                        formatted_title = title
                        if year:
                            formatted_title = f"{formatted_title} ({year})"
                        if runtime:
                            formatted_title = f"{formatted_title} - [{runtime}]"
                        if rating:
                            formatted_title = f"{formatted_title} - [{rating}]"
                        if stars:
                            formatted_title = f"{formatted_title} - ★{stars}"
                        
                        if href:
                            clean_url = "https://www.imdb.com" + href.split('?')[0]
                            results.append({'title': formatted_title, 'url': clean_url})
                    except:
                        continue
                
                log(f"✅ Scraped {len(results)} items.")
                return results
            else:
                log("❌ No items found. IMDB layout might have changed.")
                return []
        except Exception as e:
            log(f"❌ Error during scrape: {e}")
            return []

    if page:
        return await _extract(page)

    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            exec_path = get_browser_executable("firefox")
            if not exec_path: return []
            browser = await p.firefox.launch(headless=True, executable_path=exec_path)
        else:
            exec_path = get_browser_executable("chromium")
            if not exec_path: return []
            browser = await p.chromium.launch(headless=True, executable_path=exec_path)
        
        new_page = await browser.new_page(user_agent=USER_AGENT)
        try:
            results = await _extract(new_page)
            await browser.close()
            return results
        except:
            await browser.close()
            return []
            
async def main():
    """
    Entry point:
    - Loads config.
    - Handles command line arguments (scraping, queue files, or single URLs).
    - Manages the queue loop and cooldowns.
    """
    global CUSTOM_SESSION_DIR, COOLDOWN_RANGE
    
    # Check for custom session directory flag
    # This needs to be done before cleanup_stale_browser_session is called
    # to ensure the correct session directory is targeted if specified.
    # However, the bug specifically refers to "browser_session" folder,
    # so we'll prioritize cleaning the default one unless a custom one is explicitly old.
    
    if "--session-dir" in sys.argv:
        try:
            idx = sys.argv.index("--session-dir")
            CUSTOM_SESSION_DIR = sys.argv[idx + 1]
        except (IndexError, ValueError):
            pass

    # --- BUG FIX: Clean up stale browser session on startup ---
    cleanup_stale_browser_session(CUSTOM_SESSION_DIR if CUSTOM_SESSION_DIR else "browser_session")

    # Load config and set global
    loaded_config, messages = load_config()
    for msg in messages:
        log(msg)
    setup_interface(config_data=loaded_config)
    COOLDOWN_RANGE = (loaded_config['min_cooldown'], loaded_config['max_cooldown'])

    # ── Unified binary check (skip if user explicitly ran -U) ──
    if not (len(sys.argv) > 1 and sys.argv[1].strip() == '-U'):
        await ensure_binaries(cli_mode=True)

    # Default settings
    url = None
    auto_mode = False
    headless = False
    queue_mode = False
    queue_file = None

    # 1. Handle Arguments
    if len(sys.argv) > 1:
        input_arg = sys.argv[1].strip()
        if input_arg == '-U':
            await update_nm3u8dl_re()
            await update_mkvtoolnix()
            await update_ffmpeg()
            return
        elif input_arg == 'scrapemovie':
            results = await scrape_imdb_chart('movie')
            # Legacy CLI support: save to file
            if results:
                with open("imdb_top_250_movies.txt", 'w', encoding='utf-8') as f:
                    for item in results:
                        f.write(f"{item['url']}\n")
                print(f"Saved to imdb_top_250_movies.txt")
                
                run_now = input(f"🚀 Start downloading Top 250 Movies now? (y/n) [default: y]: ").strip().lower() or 'y'
                if run_now == 'y':
                    if getattr(sys, 'frozen', False):
                        subprocess.run([sys.executable, "imdb_top_250_movies.txt"])
                    else:
                        subprocess.run([sys.executable, "capture_m3u8.py", "imdb_top_250_movies.txt"])
            return
        elif input_arg == 'scrapetv':
            results = await scrape_imdb_chart('tv')
            if results:
                with open("imdb_top_250_tv.txt", 'w', encoding='utf-8') as f:
                    for item in results:
                        f.write(f"{item['url']}\n")
                print(f"Saved to imdb_top_250_tv.txt")
                
                run_now = input(f"🚀 Start downloading Top 250 TV Shows now? (y/n) [default: y]: ").strip().lower() or 'y'
                if run_now == 'y':
                    if getattr(sys, 'frozen', False):
                        subprocess.run([sys.executable, "imdb_top_250_tv.txt"])
                    else:
                        subprocess.run([sys.executable, "capture_m3u8.py", "imdb_top_250_tv.txt"])
            return
        elif input_arg.endswith('.txt'):
            queue_mode = True
            queue_file = input_arg
            auto_mode = True
            headless = True
        else:
            url = input_arg
            auto_mode = True
            headless = True
            print(f"🚀 Auto-starting with URL: {url}")
    else:
        # 2. Interactive Input
        input_arg = input("Enter URL or path to queue.txt: ").strip()
        if input_arg.endswith('.txt'):
            queue_mode = True
            queue_file = input_arg
            auto_mode = True
            headless = True
        else:
            url = input_arg
            auto_mode = False

    # 3. Execution
    if queue_mode:
        if not os.path.exists(queue_file):
            print(f"❌ File not found: {queue_file}")
            return

        print(f"📂 Loading queue from: {queue_file}")
        base_dir = os.path.dirname(queue_file)
        
        with open(queue_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        print(f"📊 Found {len(urls)} items in queue.")
        
        # Global completed.log
        completed_log = os.path.join(get_log_dir(), "completed.log")
        completed_urls = set()
        completed_keys = set() # (imdb_id, season, episode)

        if os.path.exists(completed_log):
            with open(completed_log, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    completed_urls.add(line)
                    
                    # Smart matching extraction
                    imdb_m = re.search(r'imdb=(tt\d+)', line)
                    s_m = re.search(r'[?&]season=(\d+)', line)
                    e_m = re.search(r'[?&]episode=(\d+)', line)
                    if imdb_m and s_m and e_m:
                        completed_keys.add((imdb_m.group(1), int(s_m.group(1)), int(e_m.group(1))))
        
        if os.path.exists(completed_log):
            print(f"\n📂 Found resume log with {len(completed_urls)} entries. Will skip completed items.")

        session_count = 0
        not_found_report = []

        # Flush cache before starting the batch/queue
        flush_imdb_cache()
        
        for i, queue_url in enumerate(urls):
            print(f"\n{'='*20} Processing {i+1}/{len(urls)} {'='*20}")
            
            is_completed = False
            if queue_url in completed_urls:
                is_completed = True
            else:
                imdb_m = re.search(r'imdb=(tt\d+)', queue_url)
                s_m = re.search(r'[?&]season=(\d+)', queue_url)
                e_m = re.search(r'[?&]episode=(\d+)', queue_url)
                if imdb_m and s_m and e_m:
                    if (imdb_m.group(1), int(s_m.group(1)), int(e_m.group(1))) in completed_keys:
                        is_completed = True
            
            # File existence check (self-healing)
            if not is_completed:
                s_m = re.search(r'[?&]season=(\d+)', queue_url)
                e_m = re.search(r'[?&]episode=(\d+)', queue_url)
                if s_m and e_m:
                    s_num = int(s_m.group(1))
                    e_num = int(e_m.group(1))
                    
                    season_dir = os.path.join(base_dir, f"Season {s_num:02d}")
                    if os.path.exists(season_dir):
                        for f_name in os.listdir(season_dir):
                            if f_name.endswith(".mkv") and f"S{s_num:02d}E{e_num:02d}" in f_name:
                                print(f"⏭️  Skipping (file exists): {f_name}")
                                is_completed = True
                                try:
                                    with open(completed_log, 'a', encoding='utf-8') as f_log:
                                        f_log.write(f"{queue_url}\n")
                                    completed_urls.add(queue_url)
                                except Exception as log_e:
                                    print(f"   ⚠️ Could not self-heal completed.log: {log_e}")
                                break

            if is_completed:
                print(f"⏭️  Skipping (already completed): {queue_url}")
                continue
            
            try:
                result = await process_video(queue_url, headless=True, auto_mode=True)
                
                if isinstance(result, str) and result != "404":
                    if os.path.exists(result) and os.path.getsize(result) > 5 * 1024 * 1024:
                        with open(completed_log, 'a', encoding='utf-8') as f:
                            f.write(f"{queue_url}\n")
                        print(f"✅ Marked as complete.")
                    else:
                        print(f"⚠️ File missing or too small after processing. Not marking complete.")
                elif result == "404":
                    print(f"⏭️  Skipping 404 item...")
                    
                    # Critical Failure Check: If S01E01 is missing, likely the whole series is gone.
                    if "season=1" in queue_url and "episode=1" in queue_url:
                        print("🛑 Critical Failure: Season 1 Episode 1 is 404. Aborting series download.")
                        return

                    not_found_report.append(queue_url)
                    # Do not terminate, continue to next item
                else:
                    print(f"\n❌ Failed downloading: {queue_url}")
                    print("🛑 Script terminating as requested to preserve queue state.")
                    print(f"ℹ️  To resume, run: python capture_m3u8.py \"{queue_file}\"")
                    return
                
                # Session Reset Logic
                session_count += 1
                if CONFIG['session_reset_count'] > 0 and session_count % CONFIG['session_reset_count'] == 0:
                    clear_session(reason=f"periodic reset after {session_count} items")
                    
            except Exception as e:
                print(f"❌ Error in queue loop: {e}")
            
            if i < len(urls) - 1:
                wait_time = random.randint(COOLDOWN_RANGE[0], COOLDOWN_RANGE[1])
                log(f"⏳ Cooling down ({wait_time}s)...")
                await asyncio.sleep(wait_time)
        
        # Auto-delete queue file if it was a generated list and completed successfully
        try:
            if queue_file and os.path.exists(queue_file):
                q_name = os.path.basename(queue_file)
                q_dir_name = os.path.basename(os.path.dirname(os.path.abspath(queue_file)))
                
                # Delete if it's a Top 250 list OR a Series list (filename matches folder name)
                if q_name in ["imdb_top_250_movies.txt", "imdb_top_250_tv.txt"] or \
                   (os.path.splitext(q_name)[0] == q_dir_name):
                    os.remove(queue_file)
                    print(f"\n🗑️  Auto-deleted completed queue file: {q_name}")
        except:
            pass
        
        if not_found_report:
            print(f"\n{'='*20} Summary of 404 Not Found Items {'='*20}")
            for item in not_found_report:
                print(f"❌ {item}")
            print("="*60)

    else:
        if url and "imdb.com/title/" in url:
            match = re.search(r'(tt\d+)', url)
            if match:
                imdb_id = match.group(1)
                meta = await get_imdb_info(imdb_id)
                
                if meta and meta['type'] == 'tv':
                    print(f"\n📺 Series: {meta['title']}")
                    print(f"   Total Seasons: {meta['seasons']:02d} | Total Episodes: {meta['total_episodes']}")
                    
                    season_input = input(f"Select Season (1-{meta['seasons']}) or 'all' [default: 1]: ").strip().lower() or "1"
                    
                    queue_list = []
                    
                    if season_input == 'all':
                        for s in range(1, meta['seasons'] + 1):
                            ep_count = await get_season_episodes(imdb_id, s)
                            print(f"   Season {s}: {ep_count} episodes")
                            for e in range(1, ep_count + 1):
                                link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                                queue_list.append(link)
                    else:
                        try:
                            s = int(season_input)
                            ep_count = await get_season_episodes(imdb_id, s)
                            print(f"\nSeason {s} has {ep_count} episodes.")
                            
                            ep_input = input("Select Episodes ('all', '1-5', '5-') [default: all]: ").strip().lower() or "all"
                            
                            start_ep = 1
                            end_ep = ep_count
                            
                            if ep_input == 'all':
                                pass
                            elif '-' in ep_input:
                                parts = ep_input.split('-')
                                if parts[0].strip():
                                    start_ep = int(parts[0].strip())
                                if len(parts) > 1 and parts[1].strip():
                                    end_ep = int(parts[1].strip())
                                else:
                                    end_ep = ep_count
                            elif ep_input.isdigit():
                                start_ep = int(ep_input)
                                end_ep = int(ep_input)
                            
                            for e in range(start_ep, end_ep + 1):
                                link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                                queue_list.append(link)
                                
                        except ValueError:
                            print("❌ Invalid input")
                            return

                    # Save Queue
                    finder = MasterM3U8Finder()
                    safe_title = finder.sanitize_filename(meta['title'])

                    # We still need series_dir to check the library for existing files
                    tv_dir = CONFIG.get('tv_dir') or os.path.join(get_base_dir(), "TV")
                    series_dir = os.path.join(tv_dir, safe_title)
                    
                    # Use temp folder for the queue file
                    temp_dir = os.path.join(get_base_dir(), "temp_downloads")
                    os.makedirs(temp_dir, exist_ok=True)
                    queue_filename = os.path.join(temp_dir, f"{safe_title}.quu")
                    
                    # Global completed.log
                    completed_log = os.path.join(get_log_dir(), "completed.log")
                    skipped_count = 0
                    resume_found = False
                    existing_count = 0
                    
                    if os.path.exists(completed_log):
                        try:
                            resume_found = True
                            existing_urls = set()
                            existing_keys = set()
                            with open(completed_log, 'r', encoding='utf-8') as f:
                                for line in f:
                                    line = line.strip()
                                    if not line: continue
                                    existing_urls.add(line)
                                    imdb_m = re.search(r'imdb=(tt\d+)', line)
                                    s_m = re.search(r'[?&]season=(\d+)', line)
                                    e_m = re.search(r'[?&]episode=(\d+)', line)
                                    if imdb_m and s_m and e_m:
                                        existing_keys.add((imdb_m.group(1), int(s_m.group(1)), int(e_m.group(1))))
                            existing_count = len(existing_urls)
                            
                            for link in queue_list:
                                is_skipped = False
                                if link in existing_urls:
                                    is_skipped = True
                                
                                imdb_m = re.search(r'imdb=(tt\d+)', link)
                                s_m = re.search(r'[?&]season=(\d+)', link)
                                e_m = re.search(r'[?&]episode=(\d+)', link)
                                if not is_skipped and imdb_m and s_m and e_m:
                                    s_num, e_num = int(s_m.group(1)), int(e_m.group(1))
                                    if (imdb_m.group(1), s_num, e_num) in existing_keys:
                                        is_skipped = True
                                    else:
                                        season_dir_check = os.path.join(series_dir, f"Season {s_num:02d}")
                                        if os.path.exists(season_dir_check):
                                            for f_name in os.listdir(season_dir_check):
                                                if f_name.endswith(".mkv") and f"S{s_num:02d}E{e_num:02d}" in f_name:
                                                    is_skipped = True
                                                    break
                                if is_skipped:
                                    skipped_count += 1
                        except Exception as e:
                            print(f"   ⚠️ Could not read resume data: {e}")

                    with open(queue_filename, 'w', encoding='utf-8') as f:
                        for link in queue_list:
                            f.write(f"{link}\n")
                            
                    print(f"\n✅ Queue saved to: {queue_filename}")
                    print(f"   Contains {len(queue_list)} items.")
                    
                    if resume_found:
                        print(f"   📂 Found resume log with {existing_count} entries.")
                        if skipped_count > 0:
                            print(f"   ℹ️  {skipped_count} items are already in completed.log and will be skipped.")
                    
                    run_now = input("🚀 Start processing this queue now? (y/n) [default: y]: ").strip().lower() or 'y'
                    if run_now == 'y':
                        print(f"\n🚀 Starting Batch Process for {queue_filename}...")
                        # Restart script with the new queue file
                        if getattr(sys, 'frozen', False):
                            subprocess.run([sys.executable, queue_filename])
                        else:
                            subprocess.run([sys.executable, "capture_m3u8.py", queue_filename])
                        return
                    print("\n👋 Exiting. You can run the queue file later.")
                    return

        if url:
            # Single movie download - flush cache before start
            flush_imdb_cache()
            result = await process_video(url, headless=headless, auto_mode=auto_mode)
            
            # Log successful single downloads to completed.log just like queue mode
            completed_log = os.path.join(get_log_dir(), "completed.log")
            if isinstance(result, str) and result != "404":
                if os.path.exists(result) and os.path.getsize(result) > 5 * 1024 * 1024:
                    with open(completed_log, 'a', encoding='utf-8') as f:
                        f.write(f"{url}\n")
                    print("✅ Marked as complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    finally:
        clear_session(reason="shutdown", target_dir=CUSTOM_SESSION_DIR)
