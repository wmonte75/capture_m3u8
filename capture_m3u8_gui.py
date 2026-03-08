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

# Import the core logic
import capture_m3u8

# Configuration
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

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
        self.geometry("900x700")
        
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

        # Setup Interface
        self.create_widgets()
        self.load_settings()
        
        # Start Log Monitor
        self.after(100, self.process_log_queue)

    def create_widgets(self):
        # --- Top Section: Input ---
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=10, fill="x")
        
        self.url_label = ctk.CTkLabel(self.input_frame, text="Video URL or IMDB Link:")
        self.url_label.pack(side="left", padx=10)
        
        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="https://...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=10)
        self.add_context_menu(self.url_entry)
        
        self.start_btn = ctk.CTkButton(self.input_frame, text="Start / Analyze", command=self.start_process, fg_color="green")
        self.start_btn.pack(side="right", padx=10)

        self.stop_btn = ctk.CTkButton(self.input_frame, text="Stop", command=self.stop_process, fg_color="red", width=60)
        self.stop_btn.pack(side="right", padx=5)

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

    def on_closing(self):
        self.save_settings()
        if self.is_running:
            if messagebox.askokcancel("Quit", "A download is in progress. Do you want to stop and quit?"):
                self.stop_process()
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":
    app = M3U8DownloaderApp()
    app.mainloop()