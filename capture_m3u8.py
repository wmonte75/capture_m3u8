import os
import sys
import asyncio
import re
import shutil
import subprocess
import json
import random
import importlib.util
import io
import urllib.parse
from contextlib import redirect_stdout

# Dependency Check
try:
    from playwright.async_api import async_playwright
    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    missing_module = str(e).split("'")[1] if "'" in str(e) else str(e)
    print(f"\n❌ Missing required Python library: {missing_module}")
    print("\nPlease install the missing requirements to run this script.")
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        print("\nRun this command in your terminal:")
        print("    python3 -m pip install -r requirements.txt\n")
    else:
        print("\nRun this command in your command prompt/terminal:")
        print("    pip install -r requirements.txt\n")
    sys.exit(1)

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Set Playwright to download and look for browsers in the local directory
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(get_base_dir(), "playwright_browsers")

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
    USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
elif sys.platform == 'darwin':
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
else:
    USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Download speed limit to avoid 429 "Too Many Requests" errors (e.g., '5M', '10M', '15M', '20M')
DOWNLOAD_SPEED = '6M'

# Random cooldown range between queue items (min_seconds, max_seconds)
COOLDOWN_RANGE = (10, 25)

# --- GUI / EXTERNAL INTERFACE HELPERS ---
LOG_CALLBACK = None
INPUT_CALLBACK = None
STATUS_CALLBACK = None
STOP_CALLBACK = None
CONFIG = {}

def setup_interface(config_data=None, log_cb=None, input_cb=None, status_cb=None, stop_cb=None):
    global CONFIG, LOG_CALLBACK, INPUT_CALLBACK, STATUS_CALLBACK, STOP_CALLBACK
    if config_data: CONFIG.update(config_data)
    if log_cb: LOG_CALLBACK = log_cb
    if input_cb: INPUT_CALLBACK = input_cb
    if status_cb: STATUS_CALLBACK = status_cb
    if stop_cb: STOP_CALLBACK = stop_cb

def log(msg, end="\n"):
    if LOG_CALLBACK: LOG_CALLBACK(str(msg) + end)
    else: print(msg, end=end)

def get_user_input(prompt):
    if INPUT_CALLBACK: return INPUT_CALLBACK(prompt)
    return input(prompt)

def report_status(msg):
    if STATUS_CALLBACK: STATUS_CALLBACK(msg)

def check_stop():
    if STOP_CALLBACK and STOP_CALLBACK():
        raise Exception("Stopped by user")

class PluginManager:
    def __init__(self):
        self.plugins_dir = os.path.join(get_base_dir(), "plugins")

    def run_plugins(self, file_path):
        """
        Scans 'plugins' folder and executes .py files sequentially.
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
            plugin_path = os.path.join(self.plugins_dir, filename)
            try:
                spec = importlib.util.spec_from_file_location(filename[:-3], plugin_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "process"):
                        # Capture stdout to a buffer
                        output_buffer = io.StringIO()
                        new_path = None
                        
                        try:
                            with redirect_stdout(output_buffer):
                                new_path = module.process(current_path)
                        except Exception as e:
                            # If plugin fails during execution, log everything
                            log(f"   ❌ Plugin {filename} failed during execution:")
                            # Log any output it produced before crashing
                            captured_output = output_buffer.getvalue()
                            if captured_output:
                                log(captured_output, end="")
                            log(f"      Error: {e}")
                            continue # Move to the next plugin

                        # Check if the plugin did something (path changed)
                        if new_path and new_path != current_path and os.path.exists(new_path):
                            log(f"   Running plugin: {filename}...")
                            # Log the captured output from the successful plugin
                            captured_output = output_buffer.getvalue()
                            if captured_output:
                                # We use print() inside plugins, so we need to pass the whole block to log()
                                log(captured_output, end="")
                            current_path = new_path
                        # If the path is the same, the plugin skipped, and we silently discard its output.
                    else:
                        log(f"   ⚠️  Skipping {filename}: No 'process' function found.")
            except Exception as e:
                log(f"   ❌ Plugin {filename} failed to load: {e}")
        
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
        self.master_url = None
        self.candidates = []
        self.bad_candidates = set()
        self.title = "Unknown"
        
    def find_ytdlp(self):
        """Check if yt-dlp exists in common locations"""
        for name in ["yt-dlp.exe", "yt-dlp"]:
            if os.path.exists(name):
                return os.path.abspath(name)
        
        ytdlp_path = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if ytdlp_path:
            return ytdlp_path
            
        common_paths = [
            r"C:\tools\yt-dlp.exe",
            os.path.expanduser(r"~\Downloads\yt-dlp.exe"),
            os.path.expanduser(r"~\yt-dlp\yt-dlp.exe"),
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
                
        return None
    
    async def extract_title(self, page):
        """Extract video title from page with multiple fallback strategies"""
        try:
            og_title = await page.locator('meta[property="og:title"]').get_attribute('content')
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
            h1 = await page.locator('h1').first.inner_text()
            if h1 and len(h1) > 2:
                return h1.strip()
        except:
            pass
            
        try:
            json_scripts = await page.locator('script[type="application/ld+json"]').all_inner_texts()
            for script in json_scripts:
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
        safe = safe.replace(' ', '.')
        safe = re.sub(r'\.+', '.', safe)
        if len(safe) > 50:
            safe = safe[:50]
        return safe.strip('.')

    async def save_cookies(self, context):
        """Save session cookies to Netscape format for yt-dlp"""
        try:
            cookie_file = os.path.join(get_base_dir(), 'cookies.txt')
            cookies = await context.cookies()
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

    async def get_working_url(self, context):
        """Test candidates and return the first working one"""
        for url in self.candidates:
            if url in self.bad_candidates:
                continue

            # Skip template placeholder URLs like https://tmstr3.{v1}/...
            # These are unresolved JS variables found in raw page source — not real hostnames.
            if '{' in url or '}' in url:
                self.bad_candidates.add(url)
                continue

            if url == self.master_url:
                return url

            log(f"   🧪 Testing candidate: {url[:80]}...")
            try:
                # Use Playwright's APIRequestContext to test the link
                response = await context.request.get(url, timeout=5000)
                if response.ok:
                    log(f"   ✅ Verified working: {url[:80]}")
                    return url
                else:
                    log(f"   ❌ Failed ({response.status}): {url[:80]}")
                    self.bad_candidates.add(url)
            except Exception as e:
                log(f"   ❌ Error testing candidate: {str(e)[:50]}")
                self.bad_candidates.add(url)
        return None

    async def run_ytdlp(self, ytdlp_path, master_url, output_file, use_cookies=False, status_prefix=""):
        """Execute yt-dlp download internally"""
        creation_flags = 0
        if sys.platform == 'win32':
            creation_flags = subprocess.CREATE_NO_WINDOW

        check_stop()
        if not output_file.endswith('.mkv'):
            output_file += '.mkv'
        
        # Base arguments with Cloudflare bypass
        cmd = [
            ytdlp_path,
            '--ignore-errors',
            '--no-warnings',
            '--fixup', 'detect_or_warn',
            '--fragment-retries', '10',
            '--retry-sleep', 'fragment:5',
            '--hls-prefer-native',
            '--limit-rate', self.download_speed if hasattr(self, 'download_speed') else DOWNLOAD_SPEED,
            '--write-subs',
            '--all-subs',
            '--sub-langs', CONFIG['subtitle_langs'] if 'CONFIG' in globals() and 'subtitle_langs' in CONFIG else 'all',
            '--fragment-retries', '10',  # Don't retry forever if the stream is dead
            '--skip-unavailable-fragments', # Skip segments that return no data blocks
            '-o', output_file,
        ]
        
        # Optional: Use cookies from browser if available (helps with some sites)
        if use_cookies:
            cmd.extend(['--user-agent', USER_AGENT])
            cookie_file = os.path.join(get_base_dir(), 'cookies.txt')
            if os.path.exists(cookie_file):
                log("   🍪 Using captured browser cookies...")
                cmd.extend(['--cookies', cookie_file])
        
        cmd.append(master_url)
        
        # Check if we need to capture output for GUI
        capture_output = (LOG_CALLBACK is not None)
        if capture_output:
            cmd.insert(1, '--newline')

        report_status(f"{status_prefix}Downloading...")
        log(f"\n⬇️  Starting download with yt-dlp...")
        log(f"   Output: {output_file}")
        log(f"   Anti-bot: Enabled")
        # log(f"   DEBUG Command: {cmd}")
        
        try:
            # Run internally using asyncio subprocess
            if capture_output:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    creationflags=creation_flags
                )
                
                while True:
                    check_stop()
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=0.1)
                        if not line: break
                        text = line.decode('utf-8', errors='replace').strip()
                        if text:
                            if '[download]' in text and 'ETA' in text:
                                match = re.search(r'(\d+\.?\d*)%', text)
                                if match:
                                    report_status(f"{status_prefix}Downloading {match.group(1)}%")
                            elif "HTTP Error 429" in text:
                                pass
                            elif "Downloading fragment" in text:
                                pass
                            else:
                                log(text)
                    except asyncio.TimeoutError:
                        if process.returncode is not None: break
                        continue
                
                await process.wait()
            else:
                process = await asyncio.create_subprocess_exec(*cmd, creationflags=creation_flags)
                try:
                    # Poll for stop signal while waiting for process
                    while process.returncode is None:
                        check_stop()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                    
                    # Check return code after wait
                    if process.returncode != 0 and process.returncode is not None:
                        # If we captured output, the error is already logged. 
                        # If not, it might be on stderr which we didn't capture in CLI mode (inherited).
                        pass
                except Exception as e:
                    if "Stopped by user" in str(e):
                        log("\n🛑 Process stopped by user.")
                        process.terminate()
                        await process.wait()
                    raise e # Re-raise to be handled by the calling function
                except asyncio.CancelledError:
                    log("\n🛑 Stopping download process...")
                    process.terminate()
                    await process.wait()
                    raise

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                report_status(f"{status_prefix}Downloading 100.0%")
                log(f"\n✅ Download complete: {output_file}")
                size = os.path.getsize(output_file) / (1024*1024)
                log(f"   File size: {size:.1f} MB")
                return True
            else:
                log(f"\n❌ Download failed (File not found). Exit code: {process.returncode}")
                return False
        except Exception as e:
            log(f"\n❌ Error running yt-dlp: {e}")
            return False

    async def capture(self, start_url, headless=False):
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
        
        # Use a persistent user data directory to save cookies/session
        # Use get_base_dir() so the session folder lives next to the .exe, not in CWD
        user_data_dir = os.path.join(get_base_dir(), "browser_session")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        # Ensure browsers are downloaded before launching
        ensure_playwright_browsers()

        async with async_playwright() as p:
            if sys.platform.startswith('linux'):
                # Use Firefox on Linux — different TLS/browser fingerprint bypasses
                # Cloudflare bot detection that blocks Chromium headless on Linux.
                # Windows/Mac continue to use Chromium (proven working, unchanged).
                context = await p.firefox.launch_persistent_context(
                    user_data_dir,
                    headless=headless,
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
                # Chromium for Windows / Mac — proven working, unchanged
                context = await p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=headless,
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

            # Block unpkg.com across all pages/iframes in this context
            async def block_unpkg(route):
                await route.abort()
            await context.route("**/*unpkg.com*", block_unpkg)

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

            # Inject safe stealth overrides. Only the 4 known-safe properties —
            # permissions.query and navigator.platform overrides were found to
            # interfere with cloudnestra's player JavaScript on Windows.
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin' },
                        { name: 'Chrome PDF Viewer' },
                        { name: 'Native Client' }
                    ]
                });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {} };

                // Fix HeadlessChrome in userAgent without recursion (Linux headless)
                try {
                    const _origUA = Object.getOwnPropertyDescriptor(Navigator.prototype, 'userAgent').get.call(navigator);
                    Object.defineProperty(navigator, 'userAgent', {
                        get: () => _origUA.replace('HeadlessChrome', 'Chrome')
                    });
                } catch(e) {}
            """)
            
            log("Step 1: Loading main page...")
            try:
                await page.goto(start_url, wait_until="commit", timeout=60000)
            except Exception as e:
                log(f"   ⚠️ Page load warning: {str(e)[:100]}")
                log("   Continuing scan...")
            
            # Smart wait: Check for master URL immediately, max 15s wait
            for _ in range(150):
                check_stop()
                verified = await self.get_working_url(context)
                if verified:
                    self.master_url = verified
                    break
                await asyncio.sleep(0.1)

            # If no m3u8 yet, try clicking the iframe element on the main page
            # to activate / wake up the embedded video player.
            # Firefox headless requires this — the iframe stays on its loading
            # spinner until it receives a user interaction event.
            if not self.master_url:
                try:
                    iframes = page.locator('iframe')
                    count = await iframes.count()
                    for i in range(count):
                        try:
                            await iframes.nth(i).click(timeout=1000)
                            break  # One click is enough to wake the player
                        except:
                            continue
                except:
                    pass

                # Extended wait after click — give the now-activated iframe time
                # to load the video player and make its m3u8 network request.
                for _ in range(300):  # 30s max
                    check_stop()
                    verified = await self.get_working_url(context)
                    if verified:
                        self.master_url = verified
                        break
                    await asyncio.sleep(0.1)
            
            if self.master_url:
                # Wait for the page title to become meaningful before extracting.
                # On Linux, Chromium loads slower so the DOM may still be blank
                # at this point even though the network stream was found.
                for _ in range(12):  # poll up to 3s (12 x 250ms)
                    try:
                        t = await page.title()
                        if t and t.strip() and t.lower() not in ("", "loading...", "untitled"):
                            break
                    except:
                        pass
                    await asyncio.sleep(0.25)

                if self.title == "Unknown":
                    self.title = await self.extract_title(page)
                log(f"   ⚡ Master URL found early. Skipping iframe scan.")
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
            
            for frame in frames:
                check_stop()
                try:
                    url = frame.url
                    if url and url != start_url and 'about:blank' not in url:
                        # Skip known bot/captcha/tracking/ad domains
                        # Firefox doesn't block these by default, so they show as iframes
                        skip_domains = [
                            'cloudflare', 'turnstile', 'recaptcha',
                            'dtscout.com', 'lijit.com', 'sharethis.com',
                            'crwdcntrl.net', 'intentiq.com', 'doubleclick.net',
                            'googlesyndication.com', 'amazon-adsystem.com',
                            'facebook.com/tr', 'google-analytics.com',
                            'scorecardresearch.com', 'quantserve.com',
                            'adnxs.com', 'rubiconproject.com', 'pubmatic.com',
                        ]
                        if any(x in url.lower() for x in skip_domains):
                            continue

                        # Only keep iframes that look like video embeds
                        video_patterns = [
                            'cloudnestra', 'vidsrc', '/embed/', '/rcp/', '/prorcp/',
                            'streamtape', 'doodstream', 'filemoon', 'mixdrop',
                            'upstream', 'vidplay', 'mycloud', 'mp4upload',
                        ]
                        if not any(x in url.lower() for x in video_patterns):
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

                        # JS evaluate click — primary method (works on Windows + non-Linux)
                        try:
                            await page.evaluate("""() => {
                                const video = document.querySelector('video');
                                if (video) { video.muted = true; video.play().catch(e => {}); }
                                const btn = document.querySelector('.vjs-big-play-button, .play-button, [class*="play"]');
                                if (btn) btn.click();
                            }""")
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
            
            await self.save_cookies(context)
            await context.close()
            
            return self.master_url, self.title, start_url, "success"

    def set_download_speed(self, speed):
        self.download_speed = speed

def get_output_paths(title, url):
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
        clean_title = re.sub(r'\.S\d+E\d+.*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'\.S\d+\.?$', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'\.Season\.\d+.*', '', clean_title, flags=re.IGNORECASE)
        clean_title = clean_title.strip('.')
        
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

async def process_video(url, headless=True, auto_mode=True):
    """
    Orchestrates the download process for a single URL:
    1. Converts IMDB URLs if needed.
    2. Runs MasterM3U8Finder to get the stream.
    3. Saves metadata to a .txt file.
    4. Runs yt-dlp to download.
    5. Moves the file to the final destination on success.
    """
    check_stop()
    report_status("Analyzing...")
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Check for IMDB URL and convert to vsembed
    if "imdb.com/title/" in url:
        match = re.search(r'(tt\d+)', url)
        if match:
            imdb_id = match.group(1)
            log(f"\nℹ️  Detected IMDB URL. ID: {imdb_id}")
            url = f"https://vsembed.ru/embed/movie?imdb={imdb_id}"
            log(f"   Converted to: {url}")

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
        
        ytdlp_path = finder.find_ytdlp()
        
        final_dir, filename = get_output_paths(title, url)
        os.makedirs(final_dir, exist_ok=True)
        
        txt_filename = os.path.join(final_dir, f"{safe_title}.txt")
        final_filename = os.path.join(final_dir, filename)
            
        # Setup Temp Directory
        script_dir = get_base_dir()
        temp_dir = os.path.join(script_dir, "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = os.path.join(temp_dir, f"{safe_title}.mkv")
            
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"URL: {master_url}\n")
            f.write(f"Filename: {final_filename}\n")
            f.write(f"Command: yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG.get('download_speed', DOWNLOAD_SPEED)} --user-agent \"{USER_AGENT}\" -o \"{final_filename}\" \"{master_url}\"\n")
        log(f"\n💾 Details saved to {txt_filename}")
        
        if ytdlp_path:
            log(f"\n🛠️  yt-dlp found: {ytdlp_path}")
            
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

                # Download to temp file first
                success = await finder.run_ytdlp(ytdlp_path, master_url, temp_filename, status_prefix=status_prefix)
                
                if not success:
                    log("\n⚠️  First attempt failed. Trying with browser cookies...")
                    success = await finder.run_ytdlp(ytdlp_path, master_url, temp_filename, use_cookies=True, status_prefix=status_prefix)
                
                cookie_file = os.path.join(get_base_dir(), 'cookies.txt')
                if os.path.exists(cookie_file):
                    try:
                        os.remove(cookie_file)
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
                            if os.path.exists(final_dir) and not os.listdir(final_dir):
                                os.rmdir(final_dir)
                        except:
                            pass
                        return True
                    
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
                        if os.path.exists(final_filename):
                            os.remove(final_filename)
                        shutil.move(temp_filename, final_filename)
                        log(f"✅ Move complete.")
                        
                        if os.path.exists(txt_filename):
                            try:
                                os.remove(txt_filename)
                            except:
                                pass
                                
                        return True
                    except Exception as e:
                        log(f"❌ Error moving file: {e}")
                        return False
                
                if not success:
                    log("\n📋 Manual command (try running this in terminal):")
                    log(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG.get("download_speed", DOWNLOAD_SPEED)} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
                return success
            else:
                log(f"\n📋 Manual command:")
                log(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG.get("download_speed", DOWNLOAD_SPEED)} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
                return True
        else:
            log("\n❌ yt-dlp not found")
            log(f"\n📋 Save this command:")
            log(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG.get("download_speed", DOWNLOAD_SPEED)} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
            return True
        
    else:
        if headless:
            log("\n⚠️  Headless capture failed. Retrying in visible mode to bypass Cloudflare...")
            return await process_video(url, headless=False, auto_mode=auto_mode)
            
        log("❌ FAILED - No master.m3u8 found")
        return False

async def get_imdb_info(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    log(f"🕵️  Scanning IMDB: {url}")
    
    # Ensure browsers are downloaded before launching
    ensure_playwright_browsers()
    
    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            browser = await p.firefox.launch(headless=True)
        else:
            browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            try:
                # Use domcontentloaded + shorter timeout for faster metadata extraction
                # IMDB is heavy with ads/tracking that cause full 'load' to timeout.
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                log(f"   ⚠️ IMDB load warning: {str(e)[:100]}")
                # We continue anyway as the title and basic meta might already be in the DOM
            
            title = await page.title()
            title = re.sub(r'\s*[-|]\s*IMDb.*', '', title).strip()
            
            # Fallback if title is empty
            if not title:
                try:
                    title = await page.locator('h1').first.inner_text()
                except:
                    title = "Unknown"
            
            # Extract Year
            year = ""
            try:
                # Get metadata items text (Year is usually 1st or 2nd item)
                meta_items = await page.locator('[data-testid="hero-title-block__metadata"] li').all_inner_texts()
                for text in meta_items[:3]:
                    match = re.search(r'\b(19|20)\d{2}\b', text)
                    if match:
                        year = match.group(0)
                        break
            except:
                pass
            
            if year and year not in title:
                title = f"{title} ({year})"
            
            is_tv = False
            
            # Check for series markers
            if await page.locator('text=Episode Guide').count() > 0 or \
               await page.locator('a[href*="episodes"]').count() > 0 or \
               await page.locator('[data-testid="hero-subnav-bar-season-episode-picker"]').count() > 0:
                is_tv = True
            
            if not is_tv:
                await browser.close()
                return {'type': 'movie', 'title': title}
            
            total_episodes = 0
            try:
                ep_subtext = page.locator('[data-testid="episodes-header"] .ipc-title__subtext')
                if await ep_subtext.count() > 0:
                    text = await ep_subtext.first.inner_text()
                    if text.isdigit():
                        total_episodes = int(text)
            except:
                pass
            
            log("   📺 TV Series detected. Fetching season info...")
            await page.goto(f"https://www.imdb.com/title/{imdb_id}/episodes", wait_until="domcontentloaded", timeout=45000)
            
            # Wait for season selector to load
            try:
                await page.wait_for_selector('#bySeason, [data-testid="select-season"]', timeout=5000)
            except:
                pass

            seasons = []
            options = await page.locator('#bySeason option').all()
            if not options:
                options = await page.locator('[data-testid="select-season"] option').all()
                
            for opt in options:
                val = await opt.get_attribute('value')
                if val and val.isdigit():
                    seasons.append(int(val))
            
            # Fallback: Check for season links if dropdown is missing
            if not seasons:
                links = await page.locator('a[href*="season="]').all()
                for link in links:
                    href = await link.get_attribute('href')
                    if href:
                        match = re.search(r'season=(\d+)', href)
                        if match:
                            seasons.append(int(match.group(1)))
            
            total_seasons = max(seasons) if seasons else 1
            await browser.close()
            return {'type': 'tv', 'title': title, 'seasons': total_seasons, 'total_episodes': total_episodes}
            
        except Exception as e:
            log(f"⚠️  IMDB Scan failed: {e}")
            await browser.close()
            return None

async def get_season_episodes(imdb_id, season):
    url = f"https://www.imdb.com/title/{imdb_id}/episodes?season={season}"
    log(f"   📖 Fetching episode count for Season {season}...")
    
    async with async_playwright() as p:
        if sys.platform.startswith('linux'):
            browser = await p.firefox.launch(headless=True)
        else:
            browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_selector('.list_item, article.episode-item-wrapper, [data-testid="episodes-browse-episodes"]', timeout=5000)
            except:
                pass
                
            count = await page.locator('.list_item').count()
            if count == 0:
                count = await page.locator('article.episode-item-wrapper').count()
            if count == 0:
                count = await page.locator('[data-testid="episodes-browse-episodes"] .ipc-title__text').count()
            
            await browser.close()
            return count if count > 0 else 0
        except:
            await browser.close()
            return 0

def clear_session(reason=""):
    if os.path.exists("browser_session"):
        message = f"\n🧹 Clearing browser session"
        if reason:
            message += f" ({reason})"
        message += "..."
        log(message)
        try:
            shutil.rmtree("browser_session")
            log("   ✅ Session cleared.")
        except Exception as e:
            log(f"   ⚠️ Failed to clear session: {e}")

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
        "session_reset_count": 5
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
                log_messages.append("⚙️  Loaded config.json")
        except Exception as e:
            log_messages.append(f"⚠️  Error loading config.json: {e}")
        
    return default_config, log_messages

async def search_imdb(query, filter_type='all'):
    """
    Searches IMDB for a query and returns a list of candidates.
    """
    encoded_query = urllib.parse.quote(query)
    # Exact URL format as requested
    url = f"https://www.imdb.com/find/?q={encoded_query}"
    
    log(f"🔎 Searching IMDB for: {query} (Encoded: {encoded_query})")
    log(f"   🔗 Link: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        results = []
        
        # Target the 'li' items first to ensure we have the container
        items = soup.find_all('li', class_='ipc-metadata-list-summary-item')

        for item in items:
            try:
                # Look for the title link specifically
                link_tag = item.find('a', class_='ipc-title-link-wrapper')
                if not link_tag:
                    for a in item.find_all('a'):
                        if 'title' in a.get('href', '') and a.get_text().strip():
                            link_tag = a
                            break
                            
                img_tag = item.find('img')
                
                if link_tag and 'title' in link_tag.get('href', ''):
                    title = link_tag.get_text().strip()
                    href = link_tag.get('href').split('?')[0]
                    
                    if href.startswith('/'):
                        link = "https://www.imdb.com" + href
                    else:
                        link = href
                    
                    img_url = img_tag.get('src') if img_tag else "No Image"
                    
                    # Log in the requested format
                    log(f"{img_url}: {title} - {link}")
                    
                    match = re.search(r'(tt\d+)', link)
                    if not match: continue
                    imdb_id = match.group(1)

                    # Get metadata (dates, etc.)
                    meta_elements = item.find_all(lambda tag: tag.name in ['li', 'span'] and tag.get('class') and any(c in tag.get('class') for c in ['ipc-inline-list__item', 'ipc-metadata-list-summary-item__li', 'cli-title-metadata-item', 'cli-title-type-data']))
                    meta_str = " | ".join([m.get_text().strip() for m in meta_elements]) if meta_elements else ""

                    results.append({'title': title.strip(), 'meta': meta_str, 'url': link, 'id': imdb_id, 'img': img_url})
                    
                    if len(results) >= 20:
                        break
            except:
                continue
        
        return results

    except Exception as e:
        log(f"❌ Search error: {e}")
        return []

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

async def scrape_imdb_chart(chart_type, limit=250):
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
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            await page.goto(url, timeout=60000)
            log("   Page loaded. Scanning list...")
            
            try:
                await page.wait_for_selector('.ipc-metadata-list-summary-item', timeout=10000)
            except:
                pass
            
            # Extract links
            links = await page.locator('.ipc-metadata-list-summary-item a.ipc-title-link-wrapper').all()
            count = len(links)
            log(f"   Found {count} items.")
            
            results = []
            if count > 0:
                if limit and count > limit:
                    links = links[:limit]
                
                for link in links:
                    href = await link.get_attribute('href')
                    title = await link.inner_text()
                    # Clean title (remove "1. " rank)
                    title = re.sub(r'^\d+\.\s+', '', title)
                    
                    if href:
                        clean_url = "https://www.imdb.com" + href.split('?')[0]
                        results.append({'title': title, 'url': clean_url})
                
                log(f"✅ Scraped {len(results)} items.")
                return results
            else:
                log("❌ No items found. IMDB layout might have changed.")
                return []
                
        except Exception as e:
            log(f"❌ Error during scrape: {e}")
            return []
        finally:
            await browser.close()

async def main():
    """
    Entry point:
    - Loads config.
    - Handles command line arguments (scraping, queue files, or single URLs).
    - Manages the queue loop and cooldowns.
    """
    # Load config and set global
    loaded_config, messages = load_config()
    for msg in messages:
        log(msg)
    setup_interface(config_data=loaded_config)
    global COOLDOWN_RANGE
    COOLDOWN_RANGE = (loaded_config['min_cooldown'], loaded_config['max_cooldown'])

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
            print("🔄 Checking for yt-dlp updates...")
            finder = MasterM3U8Finder()
            ytdlp_path = finder.find_ytdlp()
            if ytdlp_path:
                print(f"   Found yt-dlp at: {ytdlp_path}")
                subprocess.run([ytdlp_path, '-U'])
            else:
                print("❌ yt-dlp executable not found.")
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
        script_dir = get_base_dir()
        completed_log = os.path.join(script_dir, "completed.log")
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
                
                if result is True:
                    with open(completed_log, 'a', encoding='utf-8') as f:
                        f.write(f"{queue_url}\n")
                    print(f"✅ Marked as complete.")
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
                print(f"⏳ Cooling down ({wait_time}s)...")
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

                    # Create Series Folder
                    tv_dir = CONFIG.get('tv_dir')
                    if not tv_dir or tv_dir == ".":
                        tv_dir = os.path.join(get_base_dir(), "TV")
                    
                    series_dir = os.path.join(tv_dir, safe_title)
                        
                    os.makedirs(series_dir, exist_ok=True)
                    
                    # Global completed.log
                    script_dir = get_base_dir()
                    completed_log = os.path.join(script_dir, "completed.log")
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

                    queue_filename = os.path.join(series_dir, f"{safe_title}.txt")
                    
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
                        subprocess.run([sys.executable, "capture_m3u8.py", queue_filename])
                        return
                    print("\n👋 Exiting. You can run the queue file later.")
                    return

        if url:
            # Single movie download
            await process_video(url, headless=headless, auto_mode=auto_mode)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    finally:
        clear_session(reason="shutdown")
