import customtkinter as ctk
import threading
import queue
import asyncio
import json
import os
import time
import random
import re
import ctypes
import tkinter
from tkinter import filedialog, messagebox, Menu
from PIL import Image
import requests
import io
import concurrent.futures

# Import the core logic
import capture_m3u8

# Configuration
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def schedule(self, event=None):
        self.unschedule()
        self.id = self.widget.after(500, self.show)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tkinter.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tkinter.Label(tw, text=self.text, justify=tkinter.LEFT,
                              background="#ffffe0", relief=tkinter.SOLID, borderwidth=1,
                              font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide(self, event=None):
        self.unschedule()
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

class M3U8DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Set AppUserModelID so the taskbar icon matches the window icon
        try:
            myappid = 'ytlink.m3u8hunter.gui.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.title("M3U8 Hunter & Downloader - Beta")
        
        # Load geometry if available, otherwise default
        # We need to load config first to get geometry, but config loading happens later in __init__
        # So we'll set a default here and update it after config load
        self.geometry("1006x700") 
        
        # Handle window closing event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # State variables
        self.is_running = False
        self.log_queue = queue.Queue()
        self.input_event = threading.Event()
        self.input_value = None
        self.stop_event = threading.Event()
        
        # --- CRITICAL CHANGE: Setup callbacks BEFORE loading config ---
        # This ensures 'load_config' messages are captured by the GUI log.
        capture_m3u8.setup_interface(
            log_cb=self.log_callback,
            input_cb=self.input_callback,
            status_cb=self.status_callback,
            stop_cb=self.check_stop_callback
        )
        
        self.config, messages = capture_m3u8.load_config()
        # Explicitly log messages returned from load_config
        for msg in messages:
            self.log_callback(msg + '\n')

        # Re-apply config to the core module after loading
        capture_m3u8.setup_interface(config_data=self.config)

        # Restore window position if saved
        if "window_geometry" in self.config:
            self.geometry(self.config["window_geometry"])

        # Setup Interface
        self.create_widgets()
        self.load_settings()
        
        # Start Log Monitor
        self.after(100, self.process_log_queue)

    def create_widgets(self):
        # --- Top Section: Input ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=10, fill="x")
        
        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="URL, IMDB Link, or Search Query...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.add_context_menu(self.url_entry)
        ToolTip(self.url_entry, "Paste a direct video link, an IMDB URL (tt1234567),\nor type a movie/series name and press Enter to search IMDB.")
        
        self.start_btn = ctk.CTkButton(self.input_frame, text="Start / Analyze", command=self.start_process, fg_color="green")
        self.start_btn.pack(side="right", padx=10)

        self.stop_btn = ctk.CTkButton(self.input_frame, text="Stop", command=self.stop_process, fg_color="red", width=60)
        self.stop_btn.pack(side="right", padx=5)

        self.top250_btn = ctk.CTkButton(self.input_frame, text="Top 250 Movies", command=self.open_top250, fg_color="blue", width=120)
        self.top250_btn.pack(side="right", padx=5)

        self.queue_btn = ctk.CTkButton(self.input_frame, text="Load Queue", command=self.load_queue, fg_color="purple", width=100)
        self.queue_btn.pack(side="right", padx=5)

        self.check_btn = ctk.CTkButton(self.input_frame, text="Check Availability", command=self.check_availability, fg_color="orange", width=120)
        self.check_btn.pack(side="right", padx=5)

        # Bind Enter key to search
        self.url_entry.bind("<Return>", lambda e: self.search_content())

        # --- Middle Section: Settings ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=5, padx=10, fill="x")
        
        # Grid Layout for Settings
        self.settings_frame.grid_columnconfigure(1, weight=1)
        
        # Row 0: Movies Dir
        ctk.CTkLabel(self.settings_frame, text="Movies Folder:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
        self.movie_dir_entry = ctk.CTkEntry(self.settings_frame)
        self.movie_dir_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.add_context_menu(self.movie_dir_entry)
        ctk.CTkButton(self.settings_frame, text="Browse", width=60, command=lambda: self.browse_folder(self.movie_dir_entry)).grid(row=0, column=2, padx=10, pady=5)
        
        # Row 1: TV Dir
        ctk.CTkLabel(self.settings_frame, text="TV Shows Folder:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
        self.tv_dir_entry = ctk.CTkEntry(self.settings_frame)
        self.tv_dir_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.add_context_menu(self.tv_dir_entry)
        ctk.CTkButton(self.settings_frame, text="Browse", width=60, command=lambda: self.browse_folder(self.tv_dir_entry)).grid(row=1, column=2, padx=10, pady=5)
        
        # Row 2: Cooldowns & Speed
        self.opts_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.opts_frame.grid(row=2, column=0, columnspan=3, sticky="ew", padx=5, pady=5)
        
        ctk.CTkLabel(self.opts_frame, text="Cooldown (s):").pack(side="left", padx=5)
        self.min_cool = ctk.CTkEntry(self.opts_frame, width=50)
        self.min_cool.pack(side="left", padx=2)
        self.add_context_menu(self.min_cool)
        self.min_cool.bind("<FocusOut>", lambda _: self.save_settings())
        self.min_cool.bind("<Return>", lambda _: self.save_settings())
        
        ctk.CTkLabel(self.opts_frame, text="to").pack(side="left", padx=2)
        self.max_cool = ctk.CTkEntry(self.opts_frame, width=50)
        self.max_cool.pack(side="left", padx=2)
        self.add_context_menu(self.max_cool)
        self.max_cool.bind("<FocusOut>", lambda _: self.save_settings())
        self.max_cool.bind("<Return>", lambda _: self.save_settings())
        
        ctk.CTkLabel(self.opts_frame, text="Speed:").pack(side="left", padx=(20, 5))
        self.speed_opt = ctk.CTkOptionMenu(self.opts_frame, values=["Unlimited", "25M", "10M", "6.5M", "6M", "5.5M", "5M", "4.5M", "4M", "3.5M", "3M", "2.5M", "2M", "1.5M", "1M"], command=lambda _: self.save_settings())
        self.speed_opt.pack(side="left", padx=5)
        
        self.progress_lbl = ctk.CTkLabel(self.opts_frame, text="Status: Idle", text_color="cyan")
        self.progress_lbl.pack(side="left", padx=15)
        
        self.headless_chk = ctk.CTkCheckBox(self.opts_frame, text="Headless Mode")
        self.headless_chk.pack(side="right", padx=10)
        self.headless_chk.select()

        # --- Bottom Section: Logs ---
        self.log_box = ctk.CTkTextbox(self, font=("Consolas", 12))
        self.log_box.pack(pady=10, padx=10, fill="both", expand=True)
        self.log_box.configure(state="disabled")

    def add_context_menu(self, widget):
        menu = Menu(widget, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget._entry.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget._entry.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget._entry.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: widget._entry.select_range(0, 'end'))

        def show_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_menu)
        if hasattr(widget, "_entry"):
            widget._entry.bind("<Button-3>", show_menu)

    def load_settings(self):
        self.movie_dir_entry.insert(0, self.config.get("movies_dir", ""))
        self.tv_dir_entry.insert(0, self.config.get("tv_dir", ""))
        self.min_cool.insert(0, str(self.config.get("min_cooldown", 10)))
        self.max_cool.insert(0, str(self.config.get("max_cooldown", 25)))
        
        speed = self.config.get("download_speed", "6M")
        if speed in self.speed_opt._values:
            self.speed_opt.set(speed)
        else:
            self.speed_opt.set("6M")

    def save_settings(self):
        self.config["movies_dir"] = self.movie_dir_entry.get()
        self.config["tv_dir"] = self.tv_dir_entry.get()
        try:
            self.config["min_cooldown"] = int(self.min_cool.get())
            self.config["max_cooldown"] = int(self.max_cool.get())
        except:
            pass
        self.config["download_speed"] = self.speed_opt.get()
        
        self.config["window_geometry"] = self.geometry()
        # Update core config
        capture_m3u8.setup_interface(config_data=self.config)
        
        # Save to file
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_file = os.path.join(script_dir, "config.json")
            with open(config_file, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log_callback(f"Failed to save config: {e}")

    def browse_folder(self, entry_widget):
        folder = filedialog.askdirectory()
        if folder:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, folder)

    def log_callback(self, message):
        print(message, end="")
        self.log_queue.put(message)

    def status_callback(self, message):
        self.after(0, lambda: self.start_btn.configure(text=message))

    def check_stop_callback(self):
        return self.stop_event.is_set()

    def process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", str(msg))
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.process_log_queue)

    def input_callback(self, prompt):
        # This runs in the background thread.
        # We need to ask the user on the main thread.
        # Since CTk doesn't have a simple input dialog that blocks a thread easily without freezing main,
        # we will use a simple workaround or standard tkinter dialog if possible.
        
        # For simple y/n or text, we can use CTkInputDialog, but it needs to be invoked on main thread.
        # We'll use a queue/event system.
        
        print(f"DEBUG: Input requested: {prompt}") # Console fallback
        
        # If it's a simple confirmation
        if "(y/n)" in prompt.lower():
            # We can't easily show a popup from a thread. 
            # For now, let's assume 'y' for auto-operations or implement a proper bridge later.
            # But wait, the user wants a GUI.
            
            # Hacky bridge:
            self.input_value = None
            self.input_event.clear()
            
            # Schedule the dialog on main thread
            self.after(0, lambda: self.show_input_dialog(prompt))
            
            # Wait for response
            self.input_event.wait()
            return self.input_value
        
        # Default fallback
        return "y"

    def show_input_dialog(self, prompt):
        # Simple dialog
        dialog = ctk.CTkInputDialog(text=prompt, title="Input Needed")
        value = dialog.get_input()
        self.input_value = value if value else ""
        self.input_event.set()

    def start_process(self):
        if self.is_running:
            return
            
        url = self.url_entry.get().strip()
        if not url:
            return

        self.save_settings()
        self.stop_event.clear()
        self.is_running = True
        self.start_btn.configure(state="disabled", text="Running...")
        self.stop_btn.configure(state="normal")
        self.top250_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        threading.Thread(target=self.run_logic, args=(url,), daemon=True).start()

    def stop_process(self):
        if self.is_running:
            self.stop_event.set()

    def run_logic(self, url):
        try:
            # Check for IMDB Series
            if "imdb.com/title/" in url:
                match = re.search(r'(tt\d+)', url)
                if match:
                    imdb_id = match.group(1)
                    asyncio.run(self.handle_imdb_series(imdb_id, url))
                    return

            # Normal Single Video
            headless = self.headless_chk.get() == 1
            asyncio.run(capture_m3u8.process_video(url, headless=headless, auto_mode=True))
            
        except Exception as e:
            self.log_callback(f"\n❌ Error: {e}\n")
        finally:
            self.is_running = False
            self.stop_event.clear()
            self.after(0, lambda: self.progress_lbl.configure(text="Status: Idle"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))

    async def handle_imdb_series(self, imdb_id, original_url):
        self.log_callback(f"🕵️  Analyzing IMDB Series: {imdb_id}...\n")
        meta = await capture_m3u8.get_imdb_info(imdb_id)
        
        if not meta:
            self.log_callback("❌ Failed to fetch IMDB info.\n")
            return

        if meta['type'] != 'tv':
            # It's a movie, proceed normally
            headless = self.headless_chk.get() == 1
            await capture_m3u8.process_video(original_url, headless=headless, auto_mode=True)
            return

        # It is a TV Series
        self.log_callback(f"\n📺 Series Found: {meta['title']}")
        self.log_callback(f"   Seasons: {meta['seasons']} | Episodes: {meta['total_episodes']}\n")
        
        # Ask user for selection (on main thread)
        self.input_value = None
        self.input_event.clear()
        self.after(0, lambda: self.show_series_dialog(meta))
        self.input_event.wait()
        
        selection = self.input_value # Returns dict {'season': int, 'ep_start': int, 'ep_end': int} or None
        
        if not selection:
            self.log_callback("❌ Selection cancelled.\n")
            return

        # Generate Queue
        queue_list = []
        
        if selection['season'] == 'all':
            self.log_callback(f"   Fetching info for ALL {meta['seasons']} seasons...\n")
            for s in range(1, meta['seasons'] + 1):
                ep_count = await capture_m3u8.get_season_episodes(imdb_id, s)
                self.log_callback(f"   Season {s}: {ep_count} episodes.\n")
                for e in range(1, ep_count + 1):
                    link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                    queue_list.append(link)
        else:
            s = selection['season']
            
            # If user selected a specific season, we need to know how many episodes it has
            # The meta only has total_episodes (global) or we need to fetch season specific
            ep_count = await capture_m3u8.get_season_episodes(imdb_id, s)
            self.log_callback(f"   Season {s} has {ep_count} episodes.\n")
            
            start = selection.get('ep_start', 1)
            end = selection.get('ep_end', ep_count)
            
            # Bounds check
            if end > ep_count: end = ep_count
            
            for e in range(start, end + 1):
                link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                queue_list.append(link)
            
        # Setup Resume Logic
        finder = capture_m3u8.MasterM3U8Finder()
        safe_title = finder.sanitize_filename(meta['title'])
        tv_dir = self.config.get('tv_dir') or "."
        series_dir = os.path.join(tv_dir, safe_title)
        
        if not os.path.exists(series_dir):
            try:
                os.makedirs(series_dir, exist_ok=True)
            except:
                pass
                
        completed_log = os.path.join(series_dir, "completed.log")
        completed_urls = set()
        completed_episodes = set() # Store (season, episode) tuples

        if os.path.exists(completed_log):
            try:
                with open(completed_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        completed_urls.add(line)
                        
                        # Extract season/episode for robust matching
                        s_match = re.search(r'[?&]season=(\d+)', line)
                        e_match = re.search(r'[?&]episode=(\d+)', line)
                        if s_match and e_match:
                            completed_episodes.add((int(s_match.group(1)), int(e_match.group(1))))
            except Exception as e:
                self.log_callback(f"⚠️ Error reading completed.log: {e}\n")

        # Improved resume logging
        skipped_count = 0
        for link in queue_list:
            is_skipped = False
            if link in completed_urls:
                is_skipped = True
            
            if not is_skipped:
                s_match = re.search(r'[?&]season=(\d+)', link)
                e_match = re.search(r'[?&]episode=(\d+)', link)
                if s_match and e_match:
                    s_num, e_num = int(s_match.group(1)), int(e_match.group(1))
                    if (s_num, e_num) in completed_episodes:
                        is_skipped = True
                    else:
                        # File existence check
                        season_dir_check = os.path.join(series_dir, f"Season {s_num:02d}")
                        if os.path.exists(season_dir_check):
                            for f_name in os.listdir(season_dir_check):
                                if f_name.endswith(".mkv") and f"S{s_num:02d}E{e_num:02d}" in f_name:
                                    is_skipped = True
                                    break
            if is_skipped:
                skipped_count += 1

        if completed_urls:
            self.log_callback(f"📂 Found resume data: {len(completed_urls)} episodes previously completed for this series.\n")
            if skipped_count > 0:
                self.log_callback(f"   {skipped_count} of the currently selected episodes will be skipped.\n")
        
        self.log_callback(f"🚀 Queued {len(queue_list)} episodes. Starting batch...\n")
        # Process Queue
        headless = self.headless_chk.get() == 1
        
        for i, link in enumerate(queue_list):
            if self.stop_event.is_set():
                self.log_callback("\n🛑 Batch processing stopped by user.\n")
                break
            
            is_completed = False
            skip_reason = ""

            # 1. Check log file first
            if link in completed_urls:
                is_completed = True
                skip_reason = f"in completed.log"
            else:
                s_match = re.search(r'[?&]season=(\d+)', link)
                e_match = re.search(r'[?&]episode=(\d+)', link)
                if s_match and e_match:
                    s_num, e_num = int(s_match.group(1)), int(e_match.group(1))
                    if (s_num, e_num) in completed_episodes:
                        is_completed = True
                        skip_reason = f"in completed.log (S{s_num:02d}E{e_num:02d})"
                    else:
                        # 2. Check filesystem (self-healing)
                        season_dir = os.path.join(series_dir, f"Season {s_num:02d}")
                        if os.path.exists(season_dir):
                            for f_name in os.listdir(season_dir):
                                if f_name.endswith(".mkv") and f"S{s_num:02d}E{e_num:02d}" in f_name:
                                    is_completed = True
                                    skip_reason = f"file exists ({f_name})"
                                    # Self-heal the log
                                    try:
                                        with open(completed_log, 'a', encoding='utf-8') as f_log:
                                            f_log.write(f"{link}\n")
                                        completed_urls.add(link)
                                    except Exception as log_e:
                                        self.log_callback(f"   ⚠️ Could not self-heal completed.log: {log_e}\n")
                                    break

            if is_completed:
                self.log_callback(f"⏭️  Skipping ({skip_reason}): {link}\n")
                continue

            self.log_callback(f"\n--- Processing {i+1}/{len(queue_list)} ---\n")
            self.after(0, lambda j=i+1, t=len(queue_list): (self.progress_lbl.configure(text=f"Processing file: {j}/{t}"), self.update_idletasks()))
            success = await capture_m3u8.process_video(link, headless=headless, auto_mode=True)
            
            if success is True:
                try:
                    with open(completed_log, 'a', encoding='utf-8') as f:
                        f.write(f"{link}\n")
                    completed_urls.add(link)
                except Exception as e:
                    self.log_callback(f"⚠️ Failed to update completed.log: {e}\n")
            
            if i < len(queue_list) - 1:
                wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                capture_m3u8.report_status(f"Cooling down {wait}s...")
                await asyncio.sleep(wait)

    def show_series_dialog(self, meta):
        # A custom Toplevel window for selection
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Season/Episodes")
        
        w, h = 300, 250
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        
        ctk.CTkLabel(dialog, text=f"Select Season (1-{meta['seasons']} or 'all'):").pack(pady=5)
        season_entry = ctk.CTkEntry(dialog)
        season_entry.pack(pady=5)
        season_entry.insert(0, "1")
        self.add_context_menu(season_entry)
        
        ctk.CTkLabel(dialog, text="Episode Range (Optional):").pack(pady=5)
        range_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        range_frame.pack(pady=5)
        
        ep_start = ctk.CTkEntry(range_frame, width=50, placeholder_text="1")
        ep_start.pack(side="left", padx=5)
        self.add_context_menu(ep_start)
        ctk.CTkLabel(range_frame, text="-").pack(side="left")
        ep_end = ctk.CTkEntry(range_frame, width=50, placeholder_text="All")
        ep_end.pack(side="left", padx=5)
        self.add_context_menu(ep_end)
        
        def on_confirm():
            try:
                val = season_entry.get().strip().lower()
                if val == 'all':
                    self.input_value = {'season': 'all'}
                else:
                    s = int(val)
                    
                    s_val = ep_start.get().strip()
                    start = int(s_val) if s_val.isdigit() else 1
                    
                    e_val = ep_end.get().strip().lower()
                    if not e_val or e_val == 'all':
                        end = 999
                    elif e_val.isdigit():
                        end = int(e_val)
                    else:
                        end = 999
                        
                    self.input_value = {'season': s, 'ep_start': start, 'ep_end': end}
            except:
                self.input_value = None
            
            self.input_event.set()
            dialog.destroy()
            
        ctk.CTkButton(dialog, text="Download", command=on_confirm).pack(pady=20)
        
        # Handle window close
        def on_close():
            self.input_value = None
            self.input_event.set()
            dialog.destroy()
            
        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def open_top250(self):
        if self.is_running: return
        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.top250_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        
        threading.Thread(target=self.run_top250_scrape, daemon=True).start()

    def run_top250_scrape(self):
        try:
            results = asyncio.run(capture_m3u8.scrape_imdb_chart('movie', limit=250))
            self.after(0, lambda: self.show_top250_selection(results))
        except Exception as e:
            self.log_callback(f"❌ Error scraping Top 250: {e}\n")
        finally:
            self.is_running = False
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))

    def show_top250_selection(self, movies):
        if not movies:
            self.log_callback("❌ No movies found.\n")
            return
            
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Movies to Download")
        dialog.geometry("500x600")
        dialog.attributes("-topmost", True)
        
        # Scrollable frame
        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.movie_vars = []
        for m in movies:
            var = ctk.IntVar()
            chk = ctk.CTkCheckBox(scroll, text=f"{m['title']}", variable=var)
            chk.pack(anchor="w", pady=2)
            self.movie_vars.append((var, m))
        
        # Button Frame for Select/Deselect All
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)
        
        def select_all():
            for var, _ in self.movie_vars:
                var.set(1)
                
        def deselect_all():
            for var, _ in self.movie_vars:
                var.set(0)
                
        ctk.CTkButton(btn_frame, text="Select All", command=select_all, width=100).pack(side="left", padx=5, expand=True)
        ctk.CTkButton(btn_frame, text="Deselect All", command=deselect_all, width=100).pack(side="left", padx=5, expand=True)
            
        def save_to_queue():
            selected = [m for var, m in self.movie_vars if var.get() == 1]
            if not selected:
                messagebox.showwarning("No Selection", "Please select at least one movie.")
                return
            
            filename = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
            if filename:
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        for m in selected:
                            f.write(f"{m['url']}\n")
                    messagebox.showinfo("Saved", f"Saved {len(selected)} movies to {os.path.basename(filename)}")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to save file: {e}")

        def start_download():
            selected = [m for var, m in self.movie_vars if var.get() == 1]
            if not selected:
                messagebox.showwarning("No Selection", "Please select at least one movie.")
                return
            
            dialog.destroy()
            
            # Start batch process
            self.is_running = True
            self.start_btn.configure(state="disabled")
            self.top250_btn.configure(state="disabled")
            self.queue_btn.configure(state="disabled")
            self.log_box.configure(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.configure(state="disabled")
            
            threading.Thread(target=self.run_movie_batch, args=(selected,), daemon=True).start()
            
        ctk.CTkButton(dialog, text="Save to Queue", command=save_to_queue, fg_color="orange").pack(pady=5)
        ctk.CTkButton(dialog, text="Download Selected", command=start_download, fg_color="green").pack(pady=5)

    def run_movie_batch(self, movies):
        self.log_callback(f"🚀 Starting batch download for {len(movies)} movies...\n")
        headless = self.headless_chk.get() == 1
        
        try:
            for i, m in enumerate(movies):
                if self.stop_event.is_set():
                    self.log_callback("\n🛑 Batch processing stopped by user.\n")
                    break
                self.log_callback(f"\n--- Processing {i+1}/{len(movies)}: {m['title']} ---\n")
                self.after(0, lambda j=i+1, t=len(movies): (self.progress_lbl.configure(text=f"Processing file: {j}/{t}"), self.update_idletasks()))
                asyncio.run(capture_m3u8.process_video(m['url'], headless=headless, auto_mode=True))
                
                if i < len(movies) - 1:
                    wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                    self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                    capture_m3u8.report_status(f"Cooling down {wait}s...")
                    time.sleep(wait)
                    
        except Exception as e:
            self.log_callback(f"\n❌ Batch Error: {e}\n")
        finally:
            self.after(0, lambda: self.progress_lbl.configure(text="Status: Idle"))
            self.is_running = False
            self.stop_event.clear()
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.start_btn.configure(text="Start / Analyze"))

    def load_queue(self):
        if self.is_running: return
        
        filename = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not filename:
            return
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except Exception as e:
            self.log_callback(f"❌ Error reading queue file: {e}\n")
            return
            
        if not urls:
            self.log_callback("❌ Queue file is empty.\n")
            return
            
        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.top250_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        
        threading.Thread(target=self.run_queue_batch, args=(urls, filename), daemon=True).start()

    def run_queue_batch(self, urls, filename):
        self.log_callback(f"🚀 Starting queue processing from: {os.path.basename(filename)}\n")
        self.log_callback(f"📊 Found {len(urls)} items.\n")
        
        # --- Smart Queue Detection ---
        is_tv_queue = False
        series_imdb_id = None
        series_dir = None
        
        if urls:
            match = re.search(r'imdb=(tt\d+)', urls[0])
            if match:
                potential_imdb_id = match.group(1)
                if all(potential_imdb_id in u for u in urls[1:]):
                    is_tv_queue = True
                    series_imdb_id = potential_imdb_id

        if is_tv_queue:
            self.log_callback(f"ℹ️  Detected TV Series queue for IMDB ID: {series_imdb_id}\n")
            meta = asyncio.run(capture_m3u8.get_imdb_info(series_imdb_id))
            if meta and meta['type'] == 'tv':
                finder = capture_m3u8.MasterM3U8Finder()
                safe_title = finder.sanitize_filename(meta['title'])
                tv_dir = self.config.get('tv_dir') or "."
                series_dir = os.path.join(tv_dir, safe_title)
                base_dir = series_dir 
            else:
                is_tv_queue = False
                self.log_callback(f"⚠️  IMDB ID is a movie, treating as a mixed queue.\n")
                base_dir = os.path.dirname(filename)
        else:
            base_dir = os.path.dirname(filename)

        completed_log = os.path.join(base_dir, "completed.log")
        
        completed_urls = set()
        completed_episodes = set()
        
        if os.path.exists(completed_log):
            try:
                with open(completed_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        completed_urls.add(line)
                        if is_tv_queue:
                            s_match = re.search(r'[?&]season=(\d+)', line)
                            e_match = re.search(r'[?&]episode=(\d+)', line)
                            if s_match and e_match:
                                completed_episodes.add((int(s_match.group(1)), int(e_match.group(1))))
                self.log_callback(f"📂 Found resume log with {len(completed_urls)} entries.\n")
            except Exception as e:
                self.log_callback(f"⚠️ Error reading completed.log: {e}\n")

        headless = self.headless_chk.get() == 1
        
        try:
            for i, url in enumerate(urls):
                if self.stop_event.is_set():
                    self.log_callback("\n🛑 Queue processing stopped by user.\n")
                    break
                
                is_completed = False
                skip_reason = ""

                if url in completed_urls:
                    is_completed = True
                    skip_reason = "in completed.log"
                elif is_tv_queue and series_dir:
                    s_match = re.search(r'[?&]season=(\d+)', url)
                    e_match = re.search(r'[?&]episode=(\d+)', url)
                    if s_match and e_match:
                        s_num, e_num = int(s_match.group(1)), int(e_match.group(1))
                        if (s_num, e_num) in completed_episodes:
                            is_completed = True
                            skip_reason = f"in completed.log (S{s_num:02d}E{e_num:02d})"
                        else:
                            season_dir_check = os.path.join(series_dir, f"Season {s_num:02d}")
                            if os.path.exists(season_dir_check):
                                for f_name in os.listdir(season_dir_check):
                                    if f_name.endswith(".mkv") and f"S{s_num:02d}E{e_num:02d}" in f_name:
                                        is_completed = True
                                        skip_reason = f"file exists ({f_name})"
                                        try:
                                            with open(completed_log, 'a', encoding='utf-8') as f_log:
                                                f_log.write(f"{url}\n")
                                            completed_urls.add(url)
                                        except: pass
                                        break
                
                if is_completed:
                    self.log_callback(f"⏭️  Skipping ({skip_reason}): {url}\n")
                    continue
                self.log_callback(f"\n--- Processing {i+1}/{len(urls)} ---\n")
                self.after(0, lambda j=i+1, t=len(urls): (self.progress_lbl.configure(text=f"Processing file: {j}/{t}"), self.update_idletasks()))
                
                success = asyncio.run(capture_m3u8.process_video(url, headless=headless, auto_mode=True))
                
                if success is True:
                    try:
                        with open(completed_log, 'a', encoding='utf-8') as f:
                            f.write(f"{url}\n")
                        completed_urls.add(url)
                    except Exception as e:
                        self.log_callback(f"⚠️ Failed to update completed.log: {e}\n")
                
                if i < len(urls) - 1:
                    wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                    self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                    capture_m3u8.report_status(f"Cooling down {wait}s...")
                    time.sleep(wait)
                    
        except Exception as e:
            self.log_callback(f"\n❌ Queue Error: {e}\n")
        finally:
            self.after(0, lambda: self.progress_lbl.configure(text="Status: Idle"))
            self.is_running = False
            self.stop_event.clear()
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.start_btn.configure(text="Start / Analyze"))

    def on_closing(self):
        self.save_settings()
        if self.is_running:
            if messagebox.askokcancel("Quit", "A download is in progress. Do you want to stop and quit?"):
                self.stop_process()
                self.destroy()
        else:
            self.destroy()

    def check_availability(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Check", "Please enter an IMDB link.")
            return
            
        match = re.search(r'(tt\d+)', url)
        if not match:
            messagebox.showwarning("Check", "No IMDB ID found in the URL. Example: https://www.imdb.com/title/tt0090540/")
            return
            
        imdb_id = match.group(1)
        self.check_btn.configure(state="disabled", text="Checking...")
        
        def run_check():
            try:
                # 1. Determine if Movie or TV Show
                meta = asyncio.run(capture_m3u8.get_imdb_info(imdb_id))
                
                if meta and meta['type'] == 'tv':
                    # It's a TV Show. Check S01E01 availability
                    embed_url = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season=1&episode=1"
                    type_str = "TV Series (Checking S01E01)"
                else:
                    # It's a Movie
                    embed_url = f"https://vsembed.ru/embed/movie?imdb={imdb_id}"
                    type_str = "Movie"

                # 2. Ping the Embed URL
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(embed_url, headers=headers, timeout=10)
                
                if resp.status_code == 200 and len(resp.text) > 500:
                    result = "Available ✅"
                else:
                    result = "Not Available ❌"
                    
                msg = f"Type: {type_str}\nStatus for {imdb_id}:\n\n{result}"
            except Exception as e:
                msg = f"Error checking: {str(e)}"
                
            self.after(0, lambda: self.check_btn.configure(state="normal", text="Check Availability"))
            self.after(0, lambda: messagebox.showinfo("Availability Result", msg))
            
        threading.Thread(target=run_check, daemon=True).start()

    def search_content(self):
        query = self.url_entry.get().strip()
        if not query:
            messagebox.showwarning("Search", "Please enter a movie or series name in the input box.")
            return
            
        self.start_search(query, 'all')

    def start_search(self, query, filter_type):
        if self.is_running: return
        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.top250_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        
        threading.Thread(target=self.run_search, args=(query, filter_type), daemon=True).start()

    def run_search(self, query, filter_type='all'):
        try:
            results = asyncio.run(capture_m3u8.search_imdb(query, filter_type))

            self.after(0, lambda: self.show_search_results(results))
        except Exception as e:
            self.log_callback(f"❌ Search Error: {e}\n")
        finally:
            self.is_running = False
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))

    def show_search_results(self, results):
        if not results:
            self.log_callback("❌ No results found.\n")
            return
            
        dialog = ctk.CTkToplevel(self)
        dialog.title("Search Results")
        
        w, h = 600, 500
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        
        scroll = ctk.CTkScrollableFrame(dialog)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        def select_item(url):
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
            dialog.destroy()
            
        self.search_images = []

        for item in results:
            frame = ctk.CTkFrame(scroll, fg_color="transparent")
            frame.pack(fill="x", pady=5)
            
            # Construct text with pre-fetched details
            title = item['title']
            meta = item.get('meta', '')
            url = item['url']
            
            btn_text = f"{title}\n{meta}\n{url}"
            
            placeholder_img = ctk.CTkImage(Image.new("RGBA", (67, 100), (0, 0, 0, 0)), size=(67, 100))
            btn = ctk.CTkButton(
                frame, 
                text=btn_text, 
                command=lambda u=item['url']: select_item(u), 
                anchor="w", 
                compound="left",
                image=placeholder_img,
                fg_color="transparent", 
                border_width=1, 
                text_color=("black", "white")
            )
            btn.pack(side="left", fill="both", expand=True)
            
            if item.get('img') and item['img'] != "No Image":
                threading.Thread(target=self.load_and_display_image, args=(item['img'], btn), daemon=True).start()

    def load_and_display_image(self, url, widget):
        try:
            with open("img_trace.log", "a") as f: f.write(f"Loading {url}\n")
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, stream=True, timeout=5)
            with open("img_trace.log", "a") as f: f.write(f"Status {response.status_code}\n")
            if response.status_code == 200:
                img_data = response.content
                pil_image = Image.open(io.BytesIO(img_data))
                ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(67, 100))
                
                def update_ui():
                    with open("img_trace.log", "a") as f: f.write(f"Configuring UI for {url}\n")
                    widget.configure(image=ctk_image)
                    self.search_images.append(ctk_image)
                
                self.after(0, update_ui)
        except Exception as e:
            with open("img_trace.log", "a") as f: f.write(f"Image load error for {url}: {e}\n")

if __name__ == "__main__":
    app = M3U8DownloaderApp()
    app.mainloop()