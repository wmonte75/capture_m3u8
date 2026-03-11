import sys
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

# Dependency Check
try:
    import customtkinter as ctk
    from PIL import Image
    import requests
    import io
    import concurrent.futures
except ImportError as e:
    missing_module = str(e).split("'")[1] if "'" in str(e) else str(e)
    # Since this is a GUI script, standard print might not be seen if run without console.
    # However, if they are missing dependencies, they are likely running it via terminal anyway to see why it fails.
    print(f"\n❌ Missing required Python library: {missing_module}")
    print("\nPlease install the missing requirements to run this GUI.")
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        print("\nRun this command in your terminal:")
        print("    python3 -m pip install -r requirements.txt\n")
    else:
        print("\nRun this command in your command prompt/terminal:")
        print("    pip install -r requirements.txt\n")
        
    # Also attempt a basic tkinter message box as a fallback if tkinter is available
    try:
        import tkinter.messagebox as mb
        root = tkinter.Tk()
        root.withdraw()
        mb.showerror("Missing Requirements", 
                     f"Missing Python library: {missing_module}\n\n"
                     "Please run:\npip install -r requirements.txt\nin your terminal.")
    except:
        pass
        
    sys.exit(1)

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

class MediaSaveDialog(ctk.CTkToplevel):
    def __init__(self, parent, meta, img_url, callback):
        super().__init__(parent)
        self.is_tv = (meta.get('type') == 'tv')
        self.title("Media Found" if not self.is_tv else "Save Full Series?")
        self.callback = callback
        self.meta = meta
        self.img_url = img_url
        
        # Geometry
        w, h = 550, 320
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (w // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        
        # Main container
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Left side: Poster
        self.poster_frame = ctk.CTkFrame(self.main_frame, width=134, height=200, fg_color="#1a1a1a")
        self.poster_frame.pack(side="left", padx=(0, 20))
        self.poster_frame.pack_propagate(False)
        self.poster_label = ctk.CTkLabel(self.poster_frame, text="Loading...")
        self.poster_label.pack(expand=True)
        
        # Right side: Info
        self.info_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.info_frame.pack(side="left", fill="both", expand=True)
        
        type_text = "SERIES FOUND" if self.is_tv else "MOVIE FOUND"
        ctk.CTkLabel(self.info_frame, text=type_text, font=("Segoe UI", 10, "bold"), text_color="#3498db").pack(anchor="w")
        ctk.CTkLabel(self.info_frame, text=meta['title'], font=("Segoe UI", 20, "bold"), wraplength=350, justify="left").pack(anchor="w", pady=(0, 10))
        
        if self.is_tv:
            details_str = f"Type: TV Series | Seasons: {meta['seasons']}"
            prompt_str = "\nWould you like to save the entire series\nas a .quu queue file for later?"
        else:
            details_str = f"Type: Movie"
            prompt_str = "\nWould you like to download this movie now\nor add it to your queue file?"
            
        ctk.CTkLabel(self.info_frame, text=details_str, font=("Segoe UI", 12), text_color="gray").pack(anchor="w")
        ctk.CTkLabel(self.info_frame, text=prompt_str, font=("Segoe UI", 14), justify="left").pack(anchor="w", pady=(15, 0))
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        if self.is_tv:
            self.yes_btn = ctk.CTkButton(self.btn_frame, text="Full Series Queue", command=lambda: self.on_click("save_queue"), fg_color="#2ecc71", hover_color="#27ae60", height=40, font=("Segoe UI", 13, "bold"))
            self.yes_btn.pack(side="right", padx=10)
            
            self.no_btn = ctk.CTkButton(self.btn_frame, text="Download Now", command=lambda: self.on_click("just_episode"), fg_color="#3498db", height=40, font=("Segoe UI", 13, "bold"))
            self.no_btn.pack(side="right")
        else:
            self.down_btn = ctk.CTkButton(self.btn_frame, text="Download Now", command=lambda: self.on_click("download_now"), fg_color="#3498db", height=40, font=("Segoe UI", 13, "bold"))
            self.down_btn.pack(side="right", padx=10)
            
            self.queue_btn = ctk.CTkButton(self.btn_frame, text="Add to Queue", command=lambda: self.on_click("add_to_queue"), fg_color="#9b59b6", hover_color="#8e44ad", height=40, font=("Segoe UI", 13, "bold"))
            self.queue_btn.pack(side="right", padx=10)

        # Cancel button for both
        self.cancel_btn = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.destroy, fg_color="transparent", border_width=1, height=40, width=80, font=("Segoe UI", 12))
        self.cancel_btn.pack(side="left")
        
        # Load image in background
        if img_url and img_url != "No Image":
            threading.Thread(target=self.load_poster, args=(img_url,), daemon=True).start()
        else:
            self.show_placeholder()

    def load_poster(self, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, stream=True, timeout=5)
            if response.status_code == 200:
                img_data = response.content
                pil_image = Image.open(io.BytesIO(img_data))
                ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(134, 200))
                self.after(0, lambda: self.poster_label.configure(image=ctk_image, text=""))
            else:
                self.after(0, self.show_placeholder)
        except:
            self.after(0, self.show_placeholder)

    def show_placeholder(self):
        self.poster_label.configure(text="No Image")

    def on_click(self, action):
        self.destroy()
        self.callback(action)

class M3U8DownloaderApp(ctk.CTk):
    def __init__(self):
        # Set AppUserModelID first so the taskbar icon matches the window icon
        try:
            myappid = 'ytlink.m3u8hunter.gui.1.1' # Changed ID slightly to invalidate Windows cache
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
            
        super().__init__()

        self.title("M3U8 Hunter & Downloader - Beta")

        # Set window icon synchronously
        import sys
        import os
        try:
            if getattr(sys, 'frozen', False):
                # Running in a PyInstaller bundle
                application_path = sys._MEIPASS
            else:
                # Running in normal Python environment
                application_path = os.path.dirname(os.path.abspath(__file__))
            
            icon_path = os.path.join(application_path, 'icon2.ico')
            self.iconbitmap(icon_path)
        except Exception as e:
            pass
        
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
        self.bypass_dialog = False
        
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

        # Apply saved theme before widgets are created (avoids flash of wrong theme)
        saved_theme = self.config.get("theme", "dark")
        ctk.set_appearance_mode(saved_theme)

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
        
        self.start_btn = ctk.CTkButton(self.input_frame, text="Start / Analyze", command=self.start_process, fg_color="green", width=220)
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

        self.dark_mode_switch = ctk.CTkSwitch(
            self.opts_frame, text="Dark Mode",
            command=self.toggle_theme
        )
        self.dark_mode_switch.pack(side="right", padx=10)

        # --- Bottom Section: Logs ---
        self.log_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.log_header_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        ctk.CTkLabel(self.log_header_frame, text="Activity Log", font=("", 13, "bold")).pack(side="left")
        self.clear_log_btn = ctk.CTkButton(self.log_header_frame, text="Clear", width=60, height=24, fg_color="transparent", border_width=1, command=self.clear_logs)
        self.clear_log_btn.pack(side="right")

        # Segoe UI handles emojis well on Windows while keeping text/numbers compact
        self.log_box = ctk.CTkTextbox(self, font=("Segoe UI", 11))
        self.log_box.pack(pady=(5, 10), padx=10, fill="both", expand=True)
        self.log_box.configure(state="disabled")
        
        # Configure Tags for Color Coding
        # Success: Green
        self.log_box.tag_config("success", foreground="#2ecc71")
        # Error: Red
        self.log_box.tag_config("error", foreground="#e74c3c")
        # Warning: Orange
        self.log_box.tag_config("warning", foreground="#f39c12")
        # Info/Search: Blue
        self.log_box.tag_config("info", foreground="#3498db")

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

    def toggle_theme(self):
        theme = "dark" if self.dark_mode_switch.get() == 1 else "light"
        ctk.set_appearance_mode(theme)
        self.config["theme"] = theme
        self.save_settings()

    def load_settings(self):
        self.movie_dir_entry.insert(0, self.config.get("movies_dir", ""))
        self.tv_dir_entry.insert(0, self.config.get("tv_dir", ""))
        self.min_cool.insert(0, str(self.config.get("min_cooldown", 10)))
        self.max_cool.insert(0, str(self.config.get("max_cooldown", 25)))

        # Restore dark mode switch state
        if self.config.get("theme", "dark") == "dark":
            self.dark_mode_switch.select()
        else:
            self.dark_mode_switch.deselect()
        
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
        self.config["theme"] = "dark" if self.dark_mode_switch.get() == 1 else "light"
        self.config["window_geometry"] = self.geometry()
        # Update core config
        capture_m3u8.setup_interface(config_data=self.config)
        
        # Save to file
        try:
            script_dir = capture_m3u8.get_base_dir()
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
        # We don't print to console here as the core logic's log() already does it via setup_interface
        self.log_queue.put(message)

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def status_callback(self, message):
        self.after(0, lambda: self.start_btn.configure(text=message))

    def check_stop_callback(self):
        return self.stop_event.is_set()

    def process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            
            # Simple color mapping based on icons
            tag = None
            if any(x in msg for x in ["✅", "💾", "Success"]): tag = "success"
            elif any(x in msg for x in ["❌", "FAILED", "Error"]): tag = "error"
            elif any(x in msg for x in ["⚠️", "Warning"]): tag = "warning"
            elif any(x in msg for x in ["🔍", "🕵️", "⚡", "📝"]): tag = "info"
            
            if tag:
                self.log_box.insert("end", str(msg), tag)
            else:
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
        self.check_btn.configure(state="disabled")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        threading.Thread(target=self.run_logic, args=(url,), daemon=True).start()

    def stop_process(self):
        if self.is_running:
            self.stop_event.set()

    def run_logic(self, url):
        try:
            # Check for IMDB Links (Series or Movie)
            if "imdb.com/title/" in url and not self.bypass_dialog:
                match = re.search(r'(tt\d+)', url)
                if match:
                    # Clear search images since we are technically starting a "search" logic
                    self.search_images = []
                    # Trigger the unified dialog check
                    self.check_for_media_save(url)
                    return
            
            # Reset bypass for the next run
            self.bypass_dialog = False

            # Normal Single Video
            headless = self.headless_chk.get() == 1
            asyncio.run(capture_m3u8.process_video(url, headless=headless, auto_mode=True))
            
        except Exception as e:
            self.log_callback(f"\n❌ Error: {e}\n")
        finally:
            self.is_running = False
            self.stop_event.clear()
            self.after(0, lambda: self.progress_lbl.configure(text="Status: Idle"))
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.check_btn.configure(state="normal"))

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
        tv_dir = self.config.get('tv_dir')
        if not tv_dir or tv_dir == ".":
            tv_dir = os.path.join(capture_m3u8.get_base_dir(), "TV")
            
        series_dir = os.path.join(tv_dir, safe_title)
        
        if not os.path.exists(series_dir):
            try:
                os.makedirs(series_dir, exist_ok=True)
            except:
                pass
                
        # Global completed.log
        script_dir = capture_m3u8.get_base_dir()
        completed_log = os.path.join(script_dir, "completed.log")
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
        
        # --- Offer to save the queue for later resuming ---
        self.input_value = None
        self.input_event.clear()
        self.after(0, lambda: self._ask_save_queue(queue_list, meta['title']))
        self.input_event.wait()  # Result stored in self.input_value but we don't need it here

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

    def _ask_save_queue(self, queue_list, series_title):
        """Prompt user to optionally save the queue as a .quu file."""
        answer = messagebox.askyesno(
            "Save Queue?",
            f"Save {len(queue_list)} episodes as a .quu queue file for later resuming?"
        )
        if answer:
            safe_title = series_title.replace(':', '-').replace('/', '-').replace('\\', '-')
            default_name = f"{safe_title}.quu"
            filename = filedialog.asksaveasfilename(
                defaultextension=".quu",
                initialfile=default_name,
                filetypes=[("Queue Files", "*.quu"), ("All Files", "*.*")]
            )
            if filename:
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(queue_list))
                    self.log_callback(f"💾 Queue saved to: {os.path.basename(filename)}\n")
                except Exception as e:
                    self.log_callback(f"⚠️ Failed to save queue: {e}\n")
        self.input_value = True
        self.input_event.set()

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
            self.stop_btn.configure(state="normal")
            self.top250_btn.configure(state="disabled")
            self.queue_btn.configure(state="disabled")
            self.check_btn.configure(state="disabled")
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
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.check_btn.configure(state="normal"))

    def load_queue(self):
        if self.is_running: return
        
        filename = filedialog.askopenfilename(
            filetypes=[("Queue Files", "*.quu *.txt"), ("Queue Files (.quu)", "*.quu"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
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
        self.stop_btn.configure(state="normal")
        self.top250_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.check_btn.configure(state="disabled")
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
            # Check if all links in the queue belong to the same TV series
            id_matches = [re.search(r'imdb=(tt\d+)', u) for u in urls]
            ids = [m.group(1) for m in id_matches if m]
            
            # It's a TV queue if: All links have the same ID AND all links are TV-specific
            if len(ids) == len(urls) and len(set(ids)) == 1:
                potential_id = ids[0]
                if all(("/tv" in u or ("season=" in u and "episode=" in u)) for u in urls):
                    is_tv_queue = True
                    series_imdb_id = potential_id

        if is_tv_queue:
            self.log_callback(f"ℹ️  Detected TV Series queue for IMDB ID: {series_imdb_id}\n")
            meta = asyncio.run(capture_m3u8.get_imdb_info(series_imdb_id))
            if meta and meta['type'] == 'tv':
                finder = capture_m3u8.MasterM3U8Finder()
                safe_title = finder.sanitize_filename(meta['title'])
                tv_dir = self.config.get('tv_dir')
                if not tv_dir or tv_dir == ".":
                    tv_dir = os.path.join(capture_m3u8.get_base_dir(), "TV")
                    
                series_dir = os.path.join(tv_dir, safe_title)
                base_dir = series_dir 
            else:
                is_tv_queue = False
                self.log_callback(f"⚠️  IMDB ID is a movie, treating as a mixed queue.\n")
                base_dir = os.path.dirname(filename)
        else:
            base_dir = os.path.dirname(filename)

        # Global completed.log
        script_dir = capture_m3u8.get_base_dir()
        completed_log = os.path.join(script_dir, "completed.log")
        
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
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.check_btn.configure(state="normal"))

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
        
        def select_item(url, img_url=None):
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
            dialog.destroy()
            # Background check media type to offer save/queue dialog
            threading.Thread(target=self.check_for_media_save, args=(url, img_url), daemon=True).start()
            
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
                command=lambda u=item['url'], i=item.get('img'): select_item(u, i), 
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

    def check_for_media_save(self, url, img_url=None):
        """Background check if the selected URL is a series or movie and offer save options."""
        if "imdb.com/title/" not in url:
            return
            
        match = re.search(r'(tt\d+)', url)
        if not match:
            return
            
        imdb_id = match.group(1)
        
        try:
            meta = asyncio.run(capture_m3u8.get_imdb_info(imdb_id))
            if not meta:
                return
                
            def on_dialog_close(action):
                if action == "save_queue":
                    threading.Thread(target=self.run_full_series_queue_save, args=(imdb_id, meta), daemon=True).start()
                elif action == "add_to_queue":
                    # For movies, add to a .quu file (append)
                    movie_url = f"https://vsembed.ru/embed/movie?imdb={imdb_id}"
                    threading.Thread(target=self.run_movie_append, args=(movie_url, meta), daemon=True).start()
                elif action == "download_now" or action == "just_episode":
                    # Already in the entry, just click Start with bypass
                    self.bypass_dialog = True
                    self.after(0, self.start_process)
            
            self.after(0, lambda: MediaSaveDialog(self, meta, img_url, on_dialog_close))
            
        except Exception:
            pass

    def run_movie_append(self, movie_url, meta):
        """Append a movie URL to a .quu file."""
        self.after(0, lambda: self.progress_lbl.configure(text="Status: Queueing..."))
        
        def pick_and_append():
            finder = capture_m3u8.MasterM3U8Finder()
            safe_title = finder.sanitize_filename(meta['title'])
            
            filename = filedialog.asksaveasfilename(
                title="Select Queue File to Append To",
                defaultextension=".quu",
                initialfile="Movie_Queue.quu",
                filetypes=[("Queue Files", "*.quu"), ("All Files", "*.*")]
            )
            
            if filename:
                try:
                    # Check if file ends with newline to avoid joining URLs
                    mode = 'a' if os.path.exists(filename) else 'w'
                    with open(filename, mode, encoding='utf-8') as f:
                        if mode == 'a':
                            # Read last byte to see if newline needed
                            with open(filename, 'rb') as fr:
                                fr.seek(0, 2)
                                if fr.tell() > 0:
                                    fr.seek(-1, 2)
                                    if fr.read(1) != b'\n':
                                        f.write('\n')
                        f.write(movie_url + '\n')
                    
                    self.log_callback(f"💾 Added '{meta['title']}' to: {os.path.basename(filename)}\n")
                except Exception as e:
                    self.log_callback(f"⚠️ Failed to append to queue: {e}\n")
            
            self.after(0, lambda: self.progress_lbl.configure(text="Status: Idle"))
            
        self.after(0, pick_and_append)

    def run_full_series_queue_save(self, imdb_id, meta):
        """Fetch all episodes and save to .quu file."""
        try:
            self.log_callback(f"📝 Building full series queue for: {meta['title']}...\n")
            
            async def fetch_all():
                q = []
                for s in range(1, meta['seasons'] + 1):
                    # Update status
                    self.after(0, lambda s_num=s: self.progress_lbl.configure(text=f"Fetching S{s_num:02d}..."))
                    ep_count = await capture_m3u8.get_season_episodes(imdb_id, s)
                    for e in range(1, ep_count + 1):
                        link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                        q.append(link)
                return q
            
            queue_list = asyncio.run(fetch_all())
            
            if not queue_list:
                self.log_callback("❌ Failed to build queue.\n")
                return
                
            def prompt_save():
                self.progress_lbl.configure(text="Status: Idle")
                finder = capture_m3u8.MasterM3U8Finder()
                safe_title = finder.sanitize_filename(meta['title'])
                default_name = f"{safe_title}_Full.quu"
                filename = filedialog.asksaveasfilename(
                    defaultextension=".quu",
                    initialfile=default_name,
                    filetypes=[("Queue Files", "*.quu"), ("All Files", "*.*")]
                )
                if filename:
                    try:
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write('\n'.join(queue_list))
                        self.log_callback(f"💾 Full series queue saved to: {os.path.basename(filename)}\n")
                    except Exception as e:
                        self.log_callback(f"⚠️ Failed to save queue: {e}\n")
                        
            self.after(0, prompt_save)
            
        except Exception as e:
            self.log_callback(f"❌ Error building series queue: {e}\n")

    def load_and_display_image(self, url, widget):
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, stream=True, timeout=5)
            if response.status_code == 200:
                img_data = response.content
                pil_image = Image.open(io.BytesIO(img_data))
                ctk_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(67, 100))
                
                def update_ui():
                    widget.configure(image=ctk_image)
                    self.search_images.append(ctk_image)
                
                self.after(0, update_ui)
        except Exception as e:
            pass

if __name__ == "__main__":
    app = M3U8DownloaderApp()
    app.mainloop()