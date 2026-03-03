import asyncio
from playwright.async_api import async_playwright
import re
import os
import sys
import shutil
import subprocess
import json
import random

# Define common User-Agent to match browser and yt-dlp to avoid 403/429 errors
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Download speed limit to avoid 429 "Too Many Requests" errors (e.g., '5M', '10M', '15M', '20M')
DOWNLOAD_SPEED = '6M'

# Random cooldown range between queue items (min_seconds, max_seconds)
COOLDOWN_RANGE = (10, 25)

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
            cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
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
            print(f"   ⚠️ Failed to save cookies: {e}")

    async def get_working_url(self, context):
        """Test candidates and return the first working one"""
        for url in self.candidates:
            if url in self.bad_candidates:
                continue
            
            if url == self.master_url:
                return url

            print(f"   🧪 Testing candidate: {url[:80]}...")
            try:
                # Use Playwright's APIRequestContext to test the link
                response = await context.request.get(url, timeout=5000)
                if response.ok:
                    print(f"   ✅ Verified working: {url[:80]}")
                    return url
                else:
                    print(f"   ❌ Failed ({response.status}): {url[:80]}")
                    self.bad_candidates.add(url)
            except Exception as e:
                print(f"   ❌ Error testing candidate: {str(e)[:50]}")
                self.bad_candidates.add(url)
        return None

    async def run_ytdlp(self, ytdlp_path, master_url, output_file, use_cookies=False):
        """Execute yt-dlp download internally"""
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
            '-o', output_file,
        ]
        
        # Optional: Use cookies from browser if available (helps with some sites)
        if use_cookies:
            cmd.extend(['--user-agent', USER_AGENT])
            cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
            if os.path.exists(cookie_file):
                print("   🍪 Using captured browser cookies...")
                cmd.extend(['--cookies', cookie_file])
        
        cmd.append(master_url)
        
        print(f"\n⬇️  Starting download with yt-dlp...")
        print(f"   Output: {output_file}")
        print(f"   Anti-bot: Enabled")
        # print(f"   DEBUG Command: {cmd}")
        
        try:
            # Run internally using asyncio subprocess
            process = await asyncio.create_subprocess_exec(*cmd)
            
            try:
                await process.wait()
            except asyncio.CancelledError:
                print("\n🛑 Stopping download process...")
                process.terminate()
                await process.wait()
                raise

            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print(f"\n✅ Download complete: {output_file}")
                size = os.path.getsize(output_file) / (1024*1024)
                print(f"   File size: {size:.1f} MB")
                return True
            else:
                print(f"\n❌ Download failed (File not found). Exit code: {process.returncode}")
                return False
        except Exception as e:
            print(f"\n❌ Error running yt-dlp: {e}")
            return False

    async def capture(self, start_url, headless=False):
        """
        The core logic:
        - Opens the URL.
        - Listens for network traffic matching .m3u8.
        - Scans iframes if not found immediately.
        - Returns the master URL and page title.
        """
        print(f"🔍 Hunting for master.m3u8 at: {start_url}")
        mode = "hidden" if headless else "visible"
        print(f"🖥️  Browser mode: {mode}\n")
        
        # Use a persistent user data directory to save cookies/session
        user_data_dir = os.path.abspath("browser_session")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        async with async_playwright() as p:
            # Use launch_persistent_context to maintain state and avoid detection
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
                    '--start-minimized',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-background-timer-throttling',
                ],
                ignore_default_args=["--enable-automation"]
            )
            
            page = context.pages[0] if context.pages else await context.new_page()

            title_found = False
            
            async def handle_route(route, request):
                url = request.url
                if 'master.m3u8' in url.lower():
                    if url not in self.candidates:
                        print(f"   🔎 Candidate found: {url[:80]}")
                        self.candidates.append(url)
                    
                    nonlocal title_found
                    if not title_found:
                        try:
                            self.title = await self.extract_title(page)
                            title_found = True
                            print(f"📝 Title identified: {self.title}")
                        except:
                            pass
                            
                await route.continue_()
            
            await page.route("**/*", handle_route)
            
            print("Step 1: Loading main page...")
            try:
                await page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"   ⚠️ Page load warning: {str(e)[:100]}")
                print("   Continuing scan...")
            
            # Smart wait: Check for master URL immediately, max 2s wait
            for _ in range(20):
                verified = await self.get_working_url(context)
                if verified:
                    self.master_url = verified
                    break
                await asyncio.sleep(0.1)
            
            if self.master_url:
                if self.title == "Unknown":
                    self.title = await self.extract_title(page)
                print(f"   ⚡ Master URL found early. Skipping iframe scan.")
                await self.save_cookies(context)
                await context.close()
                return self.master_url, self.title, start_url, "success"
            
            self.title = await self.extract_title(page)
            title_found = True
            print(f"📝 Page Title: {self.title}")
            
            if "404" in self.title or "Not Found" in self.title:
                print("   ❌ 404 Not Found detected.")
                await context.close()
                return None, self.title, start_url, "404"
            
            await asyncio.sleep(1)
            
            print("Step 2: Scanning for video iframes...")
            frames = page.frames
            iframe_urls = []
            
            for frame in frames:
                try:
                    url = frame.url
                    if url and url != start_url and 'about:blank' not in url:
                        # Filter out Cloudflare/Turnstile/Captcha iframes
                        if any(x in url.lower() for x in ['cloudflare', 'turnstile', 'recaptcha']):
                            continue
                            
                        print(f"   Found iframe: {url[:80]}")
                        iframe_urls.append(url)
                except:
                    pass
            
            if not self.master_url and iframe_urls:
                print(f"\nStep 3: Checking {len(iframe_urls)} iframe(s)...")
                
                if len(iframe_urls) > 1:
                    if headless:
                        print(f"⚠️  Multiple sources detected ({len(iframe_urls)}) in headless mode. Switching to visible...")
                        await context.close()
                        return None, self.title, start_url, "retry"

                    print(f"\n⚠️  Multiple sources detected ({len(iframe_urls)}). Needs human input.")
                    for i, url in enumerate(iframe_urls):
                        print(f"   {i+1}: {url}")
                    
                    choice = input(f"\nSelect source (1-{len(iframe_urls)}) or Press Enter to scan all: ").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(iframe_urls):
                            iframe_urls = [iframe_urls[idx]]
                            print(f"   ✅ Selected: {iframe_urls[0]}")

                for iframe_url in iframe_urls:
                    if self.master_url:
                        break
                        
                    print(f"   Navigating to: {iframe_url[:80]}...")
                    try:
                        # Set Referer to bypass hotlink protection
                        await page.set_extra_http_headers({'Referer': start_url})
                        timeout = 10000 if headless else 15000
                        await page.goto(iframe_url, wait_until="networkidle", timeout=timeout)
                        
                        if headless and self.master_url:
                            break
                        
                        iframe_title = await self.extract_title(page)
                        if iframe_title != "Unknown" and self.title == "Unknown":
                            self.title = iframe_title
                            print(f"   📝 Iframe Title: {self.title}")
                        
                        await page.evaluate("""() => {
                            const video = document.querySelector('video');
                            if (video) {
                                video.muted = true;
                                video.play().catch(e => {});
                            }
                            const btn = document.querySelector('.vjs-big-play-button, .play-button, [class*="play"]');
                            if (btn) btn.click();
                        }""")
                        
                        if headless:
                            for _ in range(20): # Max 2s wait, check every 0.1s
                                verified = await self.get_working_url(context)
                                if verified:
                                    self.master_url = verified
                                    break
                                await asyncio.sleep(0.1)
                        else:
                            await asyncio.sleep(5)
                        
                    except Exception as e:
                        print(f"      Error: {str(e)[:60]}")
                        continue
            
            if not self.master_url:
                print("Step 4: Checking page source...")
                content = await page.content()
                matches = re.findall(r'https?://[^\s"\']+master\.m3u8[^\s"\']*', content, re.IGNORECASE)
                for match in matches:
                    if match not in self.candidates:
                        print(f"   Found in HTML: {match}")
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
        base_dir = CONFIG['tv_dir'] if 'CONFIG' in globals() and CONFIG['tv_dir'] else "."
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
        base_dir = CONFIG['movies_dir'] if 'CONFIG' in globals() and CONFIG['movies_dir'] else "."
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
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Check for IMDB URL and convert to vsembed
    if "imdb.com/title/" in url:
        match = re.search(r'(tt\d+)', url)
        if match:
            imdb_id = match.group(1)
            print(f"\nℹ️  Detected IMDB URL. ID: {imdb_id}")
            url = f"https://vsembed.ru/embed/movie?imdb={imdb_id}"
            print(f"   Converted to: {url}")

    if not auto_mode:
        print("\nBrowser visibility options:")
        print("1. Hidden (headless) - Runs in background")
        print("2. Visible (normal) - Shows browser window")
        choice = input("\nSelect mode [1/2] (default: 1): ").strip() or "1"
        headless = (choice == "1")
    
    finder = MasterM3U8Finder()
    # Pass global config speed if available
    if 'CONFIG' in globals() and 'download_speed' in CONFIG:
        finder.set_download_speed(CONFIG['download_speed'])
        
    master_url, title, referer, status = await finder.capture(url, headless=headless)
    
    if status == "404":
        print(f"❌ FAILED - 404 Not Found: {url}")
        return "404"
    
    safe_title = finder.sanitize_filename(title)
    
    print("\n" + "="*70)
    if master_url:
        print("✅ SUCCESS!")
        print("="*70)
        print(f"\n🎬 Title: {title}")
        print(f"🔗 URL: {master_url[:80]}...")
        
        ytdlp_path = finder.find_ytdlp()
        
        final_dir, filename = get_output_paths(title, url)
        os.makedirs(final_dir, exist_ok=True)
        
        txt_filename = os.path.join(final_dir, f"{safe_title}.txt")
        final_filename = os.path.join(final_dir, filename)
            
        # Setup Temp Directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        temp_dir = os.path.join(script_dir, "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = os.path.join(temp_dir, f"{safe_title}.mkv")
            
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"URL: {master_url}\n")
            f.write(f"Filename: {final_filename}\n")
            f.write(f"Command: yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG['download_speed'] if 'CONFIG' in globals() else DOWNLOAD_SPEED} --user-agent \"{USER_AGENT}\" -o \"{final_filename}\" \"{master_url}\"\n")
        print(f"\n💾 Details saved to {txt_filename}")
        
        if ytdlp_path:
            print(f"\n🛠️  yt-dlp found: {ytdlp_path}")
            
            if os.path.exists(final_filename):
                print(f"\n⚠️  File '{final_filename}' already exists.")
                if auto_mode:
                    print("   Auto-mode: Saving as new file to avoid overwrite.")
                    base, ext = os.path.splitext(final_filename)
                    final_filename = f"{base}_new{ext}"
                else:
                    choice = input("   Overwrite? (y/n): ").lower()
                    if choice != 'y':
                        base, ext = os.path.splitext(final_filename)
                        final_filename = f"{base}_new{ext}"
                        print(f"   Will save as: {final_filename}")
            
            if auto_mode:
                choice = 'y'
            else:
                choice = input("\n🚀 Start download now? (y/n): ").lower()

            if choice == 'y':
                # Download to temp file first
                success = await finder.run_ytdlp(ytdlp_path, master_url, temp_filename)
                
                if not success:
                    print("\n⚠️  First attempt failed. Trying with browser cookies...")
                    success = await finder.run_ytdlp(ytdlp_path, master_url, temp_filename, use_cookies=True)
                
                cookie_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')
                if os.path.exists(cookie_file):
                    try:
                        os.remove(cookie_file)
                    except:
                        pass
                
                if success:
                    print(f"\n🚚 Moving file to final destination...")
                    print(f"   From: {temp_filename}")
                    print(f"   To:   {final_filename}")
                    try:
                        if os.path.exists(final_filename):
                            os.remove(final_filename)
                        shutil.move(temp_filename, final_filename)
                        print(f"✅ Move complete.")
                        
                        if os.path.exists(txt_filename):
                            try:
                                os.remove(txt_filename)
                            except:
                                pass
                                
                        return True
                    except Exception as e:
                        print(f"❌ Error moving file: {e}")
                        return False
                
                if not success:
                    print("\n📋 Manual command (try running this in terminal):")
                    print(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG["download_speed"] if "CONFIG" in globals() else DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
                return success
            else:
                print(f"\n📋 Manual command:")
                print(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG["download_speed"] if "CONFIG" in globals() else DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
                return True
        else:
            print("\n❌ yt-dlp not found")
            print(f"\n📋 Save this command:")
            print(f'yt-dlp --ignore-errors --no-warnings --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {CONFIG["download_speed"] if "CONFIG" in globals() else DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{final_filename}" "{master_url}"')
            return True
        
    else:
        if headless:
            print("\n⚠️  Headless capture failed. Retrying in visible mode to bypass Cloudflare...")
            return await process_video(url, headless=False, auto_mode=auto_mode)
            
        print("❌ FAILED - No master.m3u8 found")
        return False

async def get_imdb_info(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    print(f"🕵️  Scanning IMDB: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            await page.goto(url, timeout=30000)
            title = await page.title()
            title = re.sub(r'\s*[-|]\s*IMDb.*', '', title).strip()
            
            # Fallback if title is empty
            if not title:
                title = await page.locator('h1').first.inner_text()
            
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
            # Wait for potential dynamic content
            try:
                await page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass

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
            
            print("   📺 TV Series detected. Fetching season info...")
            await page.goto(f"https://www.imdb.com/title/{imdb_id}/episodes", timeout=30000)
            
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
            print(f"⚠️  IMDB Scan failed: {e}")
            await browser.close()
            return None

async def get_season_episodes(imdb_id, season):
    url = f"https://www.imdb.com/title/{imdb_id}/episodes?season={season}"
    print(f"   📖 Fetching episode count for Season {season}...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            await page.goto(url, timeout=30000)
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
        print(message)
        try:
            shutil.rmtree("browser_session")
            print("   ✅ Session cleared.")
        except Exception as e:
            print(f"   ⚠️ Failed to clear session: {e}")

def load_config():
    config_file = "config.json"
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
                print("⚙️  Loaded config.json")
        except Exception as e:
            print(f"⚠️  Error loading config.json: {e}")
    else:
        # Optional: Create default config if missing
        # with open(config_file, 'w') as f:
        #     json.dump(default_config, f, indent=4)
        pass
        
    return default_config

async def scrape_imdb_chart(chart_type):
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
    
    print(f"🚀 Starting scrape of: {label}")
    print(f"   URL: {url}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        
        try:
            await page.goto(url, timeout=60000)
            print("   Page loaded. Scanning list...")
            
            try:
                await page.wait_for_selector('.ipc-metadata-list-summary-item', timeout=10000)
            except:
                pass
            
            # Extract links
            links = await page.locator('.ipc-metadata-list-summary-item a.ipc-title-link-wrapper').all()
            count = len(links)
            print(f"   Found {count} items.")
            
            if count > 0:
                limit_input = input(f"   How many items to scrape? (1-{count}) [default: 10]: ").strip()
                limit = int(limit_input) if limit_input.isdigit() else 10
                
                links = links[:limit]
                
                urls = []
                for link in links:
                    href = await link.get_attribute('href')
                    if href:
                        clean_url = "https://www.imdb.com" + href.split('?')[0]
                        urls.append(clean_url)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    for u in urls:
                        f.write(f"{u}\n")
                
                print(f"✅ Saved {len(urls)} links to {output_file}")
                
                run_now = input(f"🚀 Start downloading {label} now? (y/n) [default: y]: ").strip().lower() or 'y'
                if run_now == 'y':
                    subprocess.run([sys.executable, "capture_m3u8.py", output_file])
            else:
                print("❌ No items found. IMDB layout might have changed.")
                
        except Exception as e:
            print(f"❌ Error during scrape: {e}")
        finally:
            await browser.close()

async def main():
    """
    Entry point:
    - Loads config.
    - Handles command line arguments (scraping, queue files, or single URLs).
    - Manages the queue loop and cooldowns.
    """
    global CONFIG
    CONFIG = load_config()
    global COOLDOWN_RANGE
    COOLDOWN_RANGE = (CONFIG['min_cooldown'], CONFIG['max_cooldown'])

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
            await scrape_imdb_chart('movie')
            return
        elif input_arg == 'scrapetv':
            await scrape_imdb_chart('tv')
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
        
        print(f"📊 Found {len(urls)} items.")
        
        completed_log = os.path.join(base_dir, "completed.log") if base_dir else "completed.log"
        completed = set()
        if os.path.exists(completed_log):
            with open(completed_log, 'r', encoding='utf-8') as f:
                completed = set(line.strip() for line in f)

        # Check for resume state
        first_pending_idx = -1
        for idx, u in enumerate(urls):
            if u not in completed:
                first_pending_idx = idx
                break
        
        if first_pending_idx > 0:
            print(f"\n⚠️  Found progress in completed.log ({first_pending_idx} items done).")
            print(f"   Last file did not download: {urls[first_pending_idx]}")
            if (input("   Would you like to continue where we left off? (y/n) [default: y]: ").strip().lower() or 'y') != 'y':
                print("👋 Exiting.")
                return

        session_count = 0
        not_found_report = []

        for i, queue_url in enumerate(urls):
            print(f"\n{'='*20} Processing {i+1}/{len(urls)} {'='*20}")
            
            if queue_url in completed:
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
                            
                            ep_input = input("Select Episodes ('all', '1-5', 'start: 3, end: 8') [default: all]: ").strip().lower() or "all"
                            
                            start_ep = 1
                            end_ep = ep_count
                            
                            if ep_input == 'all':
                                pass
                            elif '-' in ep_input:
                                parts = ep_input.split('-')
                                start_ep = int(parts[0].strip())
                                end_ep = int(parts[1].strip())
                            elif 'start' in ep_input:
                                nums = re.findall(r'\d+', ep_input)
                                if len(nums) >= 2:
                                    start_ep = int(nums[0])
                                    end_ep = int(nums[1])
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
                    if CONFIG['tv_dir']:
                        series_dir = os.path.join(CONFIG['tv_dir'], safe_title)
                    else:
                        series_dir = safe_title
                        
                    os.makedirs(series_dir, exist_ok=True)
                    queue_filename = os.path.join(series_dir, f"{safe_title}.txt")
                    
                    with open(queue_filename, 'w', encoding='utf-8') as f:
                        for link in queue_list:
                            f.write(f"{link}\n")
                            
                    print(f"\n✅ Queue saved to: {queue_filename}")
                    print(f"   Contains {len(queue_list)} items.")
                    
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
