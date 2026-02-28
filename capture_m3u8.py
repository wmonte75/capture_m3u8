import asyncio
from playwright.async_api import async_playwright
import re
import os
import sys
import shutil
import subprocess

# Define common User-Agent to match browser and yt-dlp to avoid 403/429 errors
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Download speed limit to avoid 429 "Too Many Requests" errors (e.g., '10M', '15M', '20M')
DOWNLOAD_SPEED = '15M'

class MasterM3U8Finder:
    def __init__(self):
        self.master_url = None
        self.candidates = []
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

    async def run_ytdlp(self, ytdlp_path, master_url, output_file, use_cookies=False):
        """Execute yt-dlp download internally"""
        if not output_file.endswith('.mp4'):
            output_file += '.mp4'
        
        # Base arguments with Cloudflare bypass
        cmd = [
            ytdlp_path,
            '--ignore-errors',
            '--fixup', 'detect_or_warn',
            '--fragment-retries', '10',
            '--retry-sleep', 'fragment:5',
            '--hls-prefer-native',
            '--limit-rate', DOWNLOAD_SPEED,  # Limit speed to avoid 429 Too Many Requests
            '--user-agent', USER_AGENT,
            '-o', output_file,
        ]
        
        # Optional: Use cookies from browser if available (helps with some sites)
        if use_cookies:
            print("   🍪 Trying with browser cookies...")
            cmd.extend(['--cookies-from-browser', 'chrome'])
        
        cmd.append(master_url)
        
        print(f"\n⬇️  Starting download with yt-dlp...")
        print(f"   Output: {output_file}")
        print(f"   Anti-bot: Enabled")
        print(f"   DEBUG Command: {cmd}")
        
        try:
            # Run internally using asyncio subprocess
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()

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
        print(f"🔍 Hunting for master.m3u8 at: {start_url}")
        mode = "hidden" if headless else "visible"
        print(f"🖥️  Browser mode: {mode}\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--autoplay-policy=no-user-gesture-required',
                    '--disable-blink-features=AutomationControlled',
                ] if not headless else [
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--autoplay-policy=no-user-gesture-required',
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080} if not headless else {'width': 1280, 'height': 720},
                user_agent=USER_AGENT,
                bypass_csp=True
            )
            
            page = await context.new_page()

            # Clear browser cache and cookies via CDP to ensure fresh session
            try:
                client = await context.new_cdp_session(page)
                await client.send("Network.clearBrowserCache")
                await client.send("Network.clearBrowserCookies")
            except Exception:
                pass

            title_found = False
            
            async def handle_route(route, request):
                url = request.url
                if 'master.m3u8' in url.lower():
                    print(f"🎯 MASTER FOUND: {url}")
                    self.master_url = url
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
                await page.goto(start_url, wait_until="load", timeout=60000)
            except Exception as e:
                print(f"   ⚠️ Page load warning: {str(e)[:100]}")
                print("   Continuing scan...")
            
            self.title = await self.extract_title(page)
            title_found = True
            print(f"📝 Page Title: {self.title}")
            
            await asyncio.sleep(1)
            
            print("Step 2: Scanning for video iframes...")
            frames = page.frames
            iframe_urls = []
            
            for frame in frames:
                try:
                    url = frame.url
                    if url and url != start_url and 'about:blank' not in url:
                        print(f"   Found iframe: {url[:80]}")
                        iframe_urls.append(url)
                except:
                    pass
            
            if not self.master_url and iframe_urls:
                print(f"\nStep 3: Checking {len(iframe_urls)} iframe(s)...")
                
                for iframe_url in iframe_urls:
                    if self.master_url:
                        break
                        
                    print(f"   Navigating to: {iframe_url[:80]}...")
                    try:
                        await page.goto(iframe_url, wait_until="networkidle", timeout=15000)
                        
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
                        
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        print(f"      Error: {str(e)[:60]}")
                        continue
            
            if not self.master_url:
                print("Step 4: Checking page source...")
                content = await page.content()
                matches = re.findall(r'https?://[^\s"\']+master\.m3u8[^\s"\']*', content, re.IGNORECASE)
                for match in matches:
                    print(f"   Found in HTML: {match}")
                    self.candidates.append(match)
                    self.master_url = match
            
            await browser.close()
            
            return self.master_url, self.title, start_url

async def main():
    if len(sys.argv) > 1:
        url = sys.argv[1].strip()
        auto_mode = True
        print(f"🚀 Auto-starting with URL: {url}")
        headless = True
    else:
        url = input("Enter URL: ").strip()
        auto_mode = False

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
    master_url, title, referer = await finder.capture(url, headless=headless)
    
    safe_title = finder.sanitize_filename(title)
    
    print("\n" + "="*70)
    if master_url:
        print("✅ SUCCESS!")
        print("="*70)
        print(f"\n🎬 Title: {title}")
        print(f"🔗 URL: {master_url[:80]}...")
        
        ytdlp_path = finder.find_ytdlp()
        
        if ytdlp_path:
            print(f"\n🛠️  yt-dlp found: {ytdlp_path}")
            filename = f"{safe_title}.mp4"
            
            if os.path.exists(filename):
                print(f"\n⚠️  File '{filename}' already exists.")
                if auto_mode:
                    print("   Auto-mode: Saving as new file to avoid overwrite.")
                    filename = f"{safe_title}_new.mp4"
                else:
                    choice = input("   Overwrite? (y/n): ").lower()
                    if choice != 'y':
                        filename = f"{safe_title}_new.mp4"
                        print(f"   Will save as: {filename}")
            
            if auto_mode:
                choice = 'y'
            else:
                choice = input("\n🚀 Start download now? (y/n): ").lower()

            if choice == 'y':
                success = await finder.run_ytdlp(ytdlp_path, master_url, filename)
                
                if not success:
                    print("\n⚠️  First attempt failed. Trying with browser cookies...")
                    success = await finder.run_ytdlp(ytdlp_path, master_url, filename, use_cookies=True)
                
                if not success:
                    print("\n📋 Manual command (try running this in terminal):")
                    print(f'yt-dlp --ignore-errors --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{filename}" "{master_url}"')
            else:
                print(f"\n📋 Manual command:")
                print(f'yt-dlp --ignore-errors --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{filename}" "{master_url}"')
        else:
            print("\n❌ yt-dlp not found")
            filename = f"{safe_title}.mp4"
            print(f"\n📋 Save this command:")
            print(f'yt-dlp --ignore-errors --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {DOWNLOAD_SPEED} --user-agent "{USER_AGENT}" -o "{filename}" "{master_url}"')
        
        txt_filename = f"{safe_title}.txt"
        with open(txt_filename, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"URL: {master_url}\n")
            f.write(f"Filename: {safe_title}.mp4\n")
            f.write(f"Command: yt-dlp --ignore-errors --fixup detect_or_warn --fragment-retries 10 --retry-sleep fragment:5 --hls-prefer-native --limit-rate {DOWNLOAD_SPEED} --user-agent \"{USER_AGENT}\" -o \"{safe_title}.mp4\" \"{master_url}\"\n")
        print(f"\n💾 Details saved to {txt_filename}")
        
    else:
        print("❌ FAILED - No master.m3u8 found")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
