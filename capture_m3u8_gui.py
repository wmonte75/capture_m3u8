import sys
import threading
import queue
import asyncio
import json
import os
import shutil
import time
import random
import re
import ctypes
from datetime import datetime, timedelta # Added for bug fix
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
        tw.attributes("-topmost", True)
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
    def __init__(self, parent, meta, img_url, availability_msg, is_available, callback):
        super().__init__(parent)
        self.is_tv = (meta.get('type') == 'tv')
        self.title("Media Found" if not self.is_tv else "Save Full Series?")
        self.callback = callback
        self.meta = meta
        self.img_url = img_url
        self.availability_msg = availability_msg
        self.is_available = is_available
        
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
            total_eps = meta.get('total_episodes', 0)
            seasons_count = meta.get('seasons', 0)
            eps_str = f" | Episodes: {total_eps}" if total_eps > 0 else ""
            details_str = f"Type: TV Series | Seasons: {seasons_count}{eps_str}"
            prompt_str = "\nWould you like to save the entire series\nas a .quu queue file for later?"
        else:
            details_str = f"Type: Movie"
            prompt_str = "\nWould you like to download this movie now\nor add it to your queue file?"
            
        ctk.CTkLabel(self.info_frame, text=details_str, font=("Segoe UI", 12), text_color="gray").pack(anchor="w")
        
        # Availability Status
        status_color = "#2ecc71" if self.is_available else "#e74c3c"
        ctk.CTkLabel(self.info_frame, text=self.availability_msg, font=("Segoe UI", 12, "bold"), text_color=status_color).pack(anchor="w", pady=(5, 0))

        if not self.is_available:
            prompt_str = "\nThis title was not found on the embed servers.\nAction buttons have been disabled."
            
        ctk.CTkLabel(self.info_frame, text=prompt_str, font=("Segoe UI", 14), justify="left").pack(anchor="w", pady=(10, 0))
        
        # Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        if self.is_tv:
            self.yes_btn = ctk.CTkButton(self.btn_frame, text="Full Series Queue", command=lambda: self.on_click("save_queue"), fg_color="#2ecc71", hover_color="#27ae60", height=40, font=("Segoe UI", 13, "bold"))
            self.yes_btn.pack(side="right", padx=10)
            
            self.no_btn = ctk.CTkButton(self.btn_frame, text="Download Now", command=lambda: self.on_click("just_episode"), fg_color="#3498db", height=40, font=("Segoe UI", 13, "bold"))
            self.no_btn.pack(side="right")
            
            if not self.is_available:
                self.yes_btn.configure(state="disabled", fg_color="gray")
                self.no_btn.configure(state="disabled", fg_color="gray")
        else:
            self.down_btn = ctk.CTkButton(self.btn_frame, text="Download Now", command=lambda: self.on_click("download_now"), fg_color="#3498db", height=40, font=("Segoe UI", 13, "bold"))
            self.down_btn.pack(side="right", padx=10)
            
            self.queue_btn = ctk.CTkButton(self.btn_frame, text="Add to Queue", command=lambda: self.on_click("add_to_queue"), fg_color="#9b59b6", hover_color="#8e44ad", height=40, font=("Segoe UI", 13, "bold"))
            self.queue_btn.pack(side="right", padx=10)

            if not self.is_available:
                self.down_btn.configure(state="disabled", fg_color="gray")
                self.queue_btn.configure(state="disabled", fg_color="gray")

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

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, open_tab=None):
        super().__init__(parent)
        self.parent = parent
        self.title("Application Settings")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        parent.update_idletasks()
        w, h = 640, 720
        # Parse parent geometry directly for reliable centering
        geo_match = re.match(r'(\d+)x(\d+)\+(\d+)\+(\d+)', parent.geometry())
        if geo_match:
            pw, ph, px, py = map(int, geo_match.groups())
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
        else:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (w // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.tabs = ctk.CTkTabview(self, width=600, height=620)
        self.tabs.pack(padx=15, pady=(15, 5), fill="both", expand=True)

        self.tabs.add("General")
        self.tabs.add("Download")
        self.tabs.add("Providers")
        self.tabs.add("Tools")

        self._build_general_tab()
        self._build_download_tab()
        self._build_providers_tab()
        self._build_tools_tab()

        ctk.CTkButton(self, text="Save & Close", command=self.save_and_close, fg_color="#27ae60", hover_color="#2ecc71").pack(pady=(5, 15))

        if open_tab and open_tab in ["General", "Download", "Providers", "Tools"]:
            self.tabs.set(open_tab)

    def _browse_folder(self, entry_widget):
        folder = filedialog.askdirectory()
        if folder:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, folder)

    def _browse_file(self, entry_widget, title="Select executable"):
        if sys.platform == 'win32':
            filetypes = [("Executables", "*.exe"), ("All Files", "*.*")]
        else:
            filetypes = [("All Files", "*.*")]
        f = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if f:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, f)

    def _build_general_tab(self):
        tab = self.tabs.tab("General")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="📁 Directories", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, padx=15, pady=(15, 10), sticky="w")

        ctk.CTkLabel(tab, text="Movies Folder:").grid(row=1, column=0, padx=15, pady=6, sticky="e")
        self.movie_dir_entry = ctk.CTkEntry(tab)
        self.movie_dir_entry.grid(row=1, column=1, padx=5, pady=6, sticky="ew")
        self.movie_dir_entry.insert(0, self.parent.config.get("movies_dir", ""))
        ctk.CTkButton(tab, text="Browse", width=60, command=lambda: self._browse_folder(self.movie_dir_entry)).grid(row=1, column=2, padx=15, pady=6)

        ctk.CTkLabel(tab, text="TV Shows Folder:").grid(row=2, column=0, padx=15, pady=6, sticky="e")
        self.tv_dir_entry = ctk.CTkEntry(tab)
        self.tv_dir_entry.grid(row=2, column=1, padx=5, pady=6, sticky="ew")
        self.tv_dir_entry.insert(0, self.parent.config.get("tv_dir", ""))
        ctk.CTkButton(tab, text="Browse", width=60, command=lambda: self._browse_folder(self.tv_dir_entry)).grid(row=2, column=2, padx=15, pady=6)

        ctk.CTkLabel(tab, text="🎨 Interface", font=("Segoe UI", 13, "bold")).grid(row=3, column=0, columnspan=3, padx=15, pady=(25, 10), sticky="w")

        row4 = ctk.CTkFrame(tab, fg_color="transparent")
        row4.grid(row=4, column=0, columnspan=3, padx=15, pady=5, sticky="w")
        self.headless_chk = ctk.CTkCheckBox(row4, text="Headless Mode")
        self.headless_chk.pack(side="left", padx=(0, 20))
        if self.parent.config.get("headless", True): self.headless_chk.select()
        else: self.headless_chk.deselect()

        self.dark_mode_switch = ctk.CTkSwitch(row4, text="Dark Mode", command=self._toggle_theme)
        self.dark_mode_switch.pack(side="left", padx=(0, 20))
        if self.parent.config.get("theme", "dark") == "dark": self.dark_mode_switch.select()
        else: self.dark_mode_switch.deselect()

        self.lang_opt = ctk.CTkOptionMenu(row4, values=["en", "es", "fr", "de", "it", "ja", "ko", "pt", "ru", "zh"], width=70)
        self.lang_opt.set(self.parent.config.get("language", "en"))
        self.lang_opt.pack(side="left")

        # --- SCP / Remote Transfer Section ---
        ctk.CTkLabel(tab, text="📡 Remote Transfer (SFTP)", font=("Segoe UI", 13, "bold")).grid(row=5, column=0, columnspan=3, padx=15, pady=(25, 10), sticky="w")

        self.scp_enabled_chk = ctk.CTkCheckBox(tab, text="Enable Remote Transfer", command=self._toggle_scp)
        self.scp_enabled_chk.grid(row=6, column=0, columnspan=3, padx=15, pady=(0, 5), sticky="w")
        if self.parent.config.get("scp_enabled", False):
            self.scp_enabled_chk.select()

        self.scp_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.scp_frame.grid(row=7, column=0, columnspan=3, padx=15, pady=5, sticky="ew")
        self.scp_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.scp_frame, text="Server Host:").grid(row=0, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_host_entry = ctk.CTkEntry(self.scp_frame, placeholder_text="e.g. 192.168.1.100 or nas.local")
        self.scp_host_entry.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        self.scp_host_entry.insert(0, self.parent.config.get("scp_host", ""))

        ctk.CTkLabel(self.scp_frame, text="Username:").grid(row=1, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_user_entry = ctk.CTkEntry(self.scp_frame)
        self.scp_user_entry.grid(row=1, column=1, padx=5, pady=4, sticky="ew")
        self.scp_user_entry.insert(0, self.parent.config.get("scp_username", ""))

        ctk.CTkLabel(self.scp_frame, text="Auth Type:").grid(row=2, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_auth_type = ctk.CTkOptionMenu(self.scp_frame, values=["SSH Key", "Password"], command=self._toggle_scp_auth)
        self.scp_auth_type.grid(row=2, column=1, padx=5, pady=4, sticky="w")
        self.scp_auth_type.set(self.parent.config.get("scp_auth_type", "SSH Key"))

        self.scp_key_frame = ctk.CTkFrame(self.scp_frame, fg_color="transparent")
        self.scp_key_frame.grid(row=3, column=0, columnspan=2, padx=0, pady=2, sticky="ew")
        self.scp_key_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.scp_key_frame, text="Key File:").grid(row=0, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_key_entry = ctk.CTkEntry(self.scp_key_frame, placeholder_text="path to .pem or private key")
        self.scp_key_entry.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        self.scp_key_entry.insert(0, self.parent.config.get("scp_key_path", ""))
        ctk.CTkButton(self.scp_key_frame, text="Browse", width=60, command=lambda: self._browse_file(self.scp_key_entry, "Select SSH Key", [("All Files", "*.*")])).grid(row=0, column=2, padx=5, pady=4)

        self.scp_pw_frame = ctk.CTkFrame(self.scp_frame, fg_color="transparent")
        self.scp_pw_frame.grid(row=4, column=0, columnspan=2, padx=0, pady=2, sticky="ew")
        self.scp_pw_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.scp_pw_frame, text="Password:").grid(row=0, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_pw_entry = ctk.CTkEntry(self.scp_pw_frame, show="*")
        self.scp_pw_entry.grid(row=0, column=1, padx=5, pady=4, sticky="ew")
        self.scp_pw_entry.insert(0, self.parent.config.get("scp_password", ""))
        ctk.CTkLabel(self.scp_pw_frame, text="⚠️ Stored in config.json", text_color="orange", font=("Segoe UI", 9)).grid(row=0, column=2, padx=5, pady=4)

        ctk.CTkLabel(self.scp_frame, text="Remote Movies Path:").grid(row=5, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_remote_movie_entry = ctk.CTkEntry(self.scp_frame, placeholder_text="/mnt/media/movies")
        self.scp_remote_movie_entry.grid(row=5, column=1, padx=5, pady=4, sticky="ew")
        self.scp_remote_movie_entry.insert(0, self.parent.config.get("scp_remote_movies_dir", ""))

        ctk.CTkLabel(self.scp_frame, text="Remote TV Path:").grid(row=6, column=0, padx=(0, 5), pady=4, sticky="e")
        self.scp_remote_tv_entry = ctk.CTkEntry(self.scp_frame, placeholder_text="/mnt/media/tv")
        self.scp_remote_tv_entry.grid(row=6, column=1, padx=5, pady=4, sticky="ew")
        self.scp_remote_tv_entry.insert(0, self.parent.config.get("scp_remote_tv_dir", ""))

        self.scp_delete_local_chk = ctk.CTkCheckBox(self.scp_frame, text="Delete local file after successful transfer")
        self.scp_delete_local_chk.grid(row=7, column=0, columnspan=2, padx=0, pady=(8, 4), sticky="w")
        if self.parent.config.get("scp_delete_local", False):
            self.scp_delete_local_chk.select()

        self._toggle_scp()
        self._toggle_scp_auth()

    def _toggle_scp(self):
        if self.scp_enabled_chk.get() == 1:
            self.scp_frame.grid()
        else:
            self.scp_frame.grid_remove()

    def _toggle_scp_auth(self, choice=None):
        auth = choice or self.scp_auth_type.get()
        if auth == "SSH Key":
            self.scp_key_frame.grid()
            self.scp_pw_frame.grid_remove()
        else:
            self.scp_key_frame.grid_remove()
            self.scp_pw_frame.grid()

    def _build_download_tab(self):
        tab = self.tabs.tab("Download")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="⏱️ Timing", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=3, padx=15, pady=(15, 8), sticky="w")

        timing = ctk.CTkFrame(tab, fg_color="transparent")
        timing.grid(row=1, column=0, columnspan=3, padx=15, pady=2, sticky="w")
        ctk.CTkLabel(timing, text="Cooldown:").pack(side="left")
        self.min_cool = ctk.CTkEntry(timing, width=50)
        self.min_cool.pack(side="left", padx=4)
        self.min_cool.insert(0, str(self.parent.config.get("min_cooldown", 10)))
        ctk.CTkLabel(timing, text="to").pack(side="left", padx=2)
        self.max_cool = ctk.CTkEntry(timing, width=50)
        self.max_cool.pack(side="left", padx=4)
        self.max_cool.insert(0, str(self.parent.config.get("max_cooldown", 25)))
        ctk.CTkLabel(timing, text="seconds").pack(side="left", padx=2)

        ctk.CTkLabel(tab, text="Fallback Speed (Manual):").grid(row=2, column=0, padx=15, pady=(15, 5), sticky="e")
        self.speed_opt = ctk.CTkOptionMenu(
            tab,
            values=["Unlimited", "25M", "10M", "6.5M", "6M", "5.5M", "5M", "4.5M", "4M", "3.5M", "3M", "2.5M", "2M", "1.5M", "1M"]
        )
        self.speed_opt.set(self.parent.config.get("download_speed", "6M"))
        self.speed_opt.grid(row=2, column=1, padx=5, pady=(15, 5), sticky="w")

        ctk.CTkLabel(tab, text="Preferred Resolution:").grid(row=3, column=0, padx=15, pady=(10, 5), sticky="e")
        self.pref_res = ctk.CTkOptionMenu(
            tab,
            values=["Auto", "1080p", "720p", "480p", "360p"]
        )
        self.pref_res.set(self.parent.config.get("preferred_resolution", "Auto"))
        self.pref_res.grid(row=3, column=1, padx=5, pady=(10, 5), sticky="w")

        sep = ctk.CTkFrame(tab, height=2, fg_color="#333333")
        sep.grid(row=4, column=0, columnspan=3, padx=15, pady=(20, 10), sticky="ew")

        ctk.CTkLabel(tab, text="🎛️ PRO: Adaptive Speed Control", font=("Segoe UI", 13, "bold"), text_color="#f1c40f").grid(
            row=5, column=0, columnspan=3, padx=15, pady=(0, 8), sticky="w")

        toggle_row = ctk.CTkFrame(tab, fg_color="transparent")
        toggle_row.grid(row=6, column=0, columnspan=3, padx=15, pady=(0, 8), sticky="w")
        self.pro_switch = ctk.CTkSwitch(toggle_row, text="Auto-Limit Speed by Resolution", command=self._toggle_pro, font=("Segoe UI", 12, "bold"))
        self.pro_switch.pack(side="left")
        self.pro_hint = ctk.CTkLabel(toggle_row, text="  (Disabled)", text_color="gray", font=("Segoe UI", 10))
        self.pro_hint.pack(side="left", padx=5)
        if self.parent.config.get("auto_speed_by_resolution", False):
            self.pro_switch.select()

        self.pro_card = ctk.CTkFrame(tab, fg_color="#151515", corner_radius=8)
        self.pro_card.grid(row=7, column=0, columnspan=3, padx=15, pady=5, sticky="ew")

        tiers = [
            ("1080p and above", "speed_cap_1080", "2.5M"),
            ("720p", "speed_cap_720", "2M"),
            ("480p", "speed_cap_480", "1.5M"),
            ("360p and below", "speed_cap_360", "1M"),
        ]
        self.tier_widgets = {}
        for label, key, default in tiers:
            r = ctk.CTkFrame(self.pro_card, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(r, text=f"{label}:", width=130, anchor="e", font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
            dd = ctk.CTkOptionMenu(r, values=["Unlimited", "10M", "5M", "4M", "3.5M", "3M", "2.5M", "2M", "1.5M", "1M", "750K", "500K"], width=110)
            dd.set(self.parent.config.get(key, default))
            dd.configure(state="disabled")
            dd.pack(side="left")
            self.tier_widgets[key] = dd

        self._toggle_pro()

    def _build_providers_tab(self):
        tab = self.tabs.tab("Providers")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="🔗 Provider Templates", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 10), sticky="w")

        ctk.CTkLabel(tab, text="Movie:").grid(row=1, column=0, padx=15, pady=6, sticky="e")
        self.movie_tpl_entry = ctk.CTkEntry(tab, placeholder_text="...{imdb}")
        self.movie_tpl_entry.grid(row=1, column=1, padx=(5, 15), pady=6, sticky="ew")
        self.movie_tpl_entry.insert(0, self.parent.config.get("movie_template", "https://vsembed.ru/embed/movie?imdb={imdb}"))
        ToolTip(self.movie_tpl_entry, "Use {imdb} placeholder for the Movie ID.")

        ctk.CTkLabel(tab, text="TV Series:").grid(row=2, column=0, padx=15, pady=6, sticky="e")
        self.tv_tpl_entry = ctk.CTkEntry(tab, placeholder_text="...{imdb}&season={s}&episode={e}")
        self.tv_tpl_entry.grid(row=2, column=1, padx=(5, 15), pady=6, sticky="ew")
        self.tv_tpl_entry.insert(0, self.parent.config.get("tv_template", "https://vidsrcme.ru/embed/tv?imdb={imdb}&season={s}&episode={e}"))
        ToolTip(self.tv_tpl_entry, "Use {imdb}, {s} (season), and {e} (episode) placeholders.")

    def _build_tools_tab(self):
        tab = self.tabs.tab("Tools")
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="🔧 Binary Paths (Auto-detected if blank)", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=15, pady=(15, 8))

        # Platform-appropriate binary names (no .exe on Linux/Mac)
        _bin_ext = ".exe" if sys.platform == 'win32' else ""
        binaries = [
            ("FFmpeg:", "ffmpeg_path", f"ffmpeg{_bin_ext}"),
            ("FFprobe:", "ffprobe_path", f"ffprobe{_bin_ext}"),
            ("N_m3u8DL-RE:", "nm3u8dl_re_path", f"N_m3u8DL-RE{_bin_ext}"),
            ("MKVPropEdit:", "mkvpropedit_path", f"mkvpropedit{_bin_ext}"),
            ("MKVMerge:", "mkvmerge_path", f"mkvmerge{_bin_ext}"),
        ]
        self.tool_entries = {}
        for label, key, example in binaries:
            row = ctk.CTkFrame(tab, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=3)
            ctk.CTkLabel(row, text=label, width=110, anchor="e", font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
            ent = ctk.CTkEntry(row, placeholder_text=f"Auto ({example})")
            ent.insert(0, self.parent.config.get(key, ""))
            ent.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkButton(row, text="Browse", width=55, command=lambda e=ent, t=label: self._browse_file(e, f"Select {t.replace(':', '')}")).pack(side="left")
            self.tool_entries[key] = ent

        sep = ctk.CTkFrame(tab, height=2, fg_color="#333333")
        sep.pack(fill="x", padx=15, pady=(18, 10))

        ctk.CTkLabel(tab, text="🛠️ Maintenance", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=15, pady=(5, 8))

        btn_box = ctk.CTkFrame(tab, fg_color="transparent")
        btn_box.pack(anchor="w", padx=15, pady=2)
        self.reload_btn = ctk.CTkButton(btn_box, text="Reload Plugins", fg_color="transparent", border_width=1, width=130, command=self.parent.reload_plugins)
        self.reload_btn.pack(side="left", padx=4)
        self.update_btn = ctk.CTkButton(btn_box, text="Check & Update Tools", fg_color="#34495e", hover_color="#2c3e50", width=150, command=self._run_tools_update)
        self.update_btn.pack(side="left", padx=4)

        ctk.CTkLabel(tab, text="🗑️ Session", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=15, pady=(20, 8))
        ctk.CTkButton(tab, text="Clear Browser Session", fg_color="#e74c3c", hover_color="#c0392b", width=150, command=lambda: capture_m3u8.clear_session(reason="user request")).pack(anchor="w", padx=20, pady=2)

        # Auto-fill discovered paths after the tab is built
        self._refresh_tool_paths()

    def _refresh_tool_paths(self):
        """Auto-discover binary locations and populate the Tools tab entries."""
        for dep in capture_m3u8.REQUIRED_BINARIES:
            key = dep["config_key"]
            if key not in self.tool_entries:
                continue
            path = capture_m3u8.find_binary(dep["binary"], key)
            if path and os.path.exists(path):
                ent = self.tool_entries[key]
                ent.delete(0, "end")
                ent.insert(0, path)
                self.parent.config[key] = path

    def _toggle_theme(self):
        theme = "dark" if self.dark_mode_switch.get() == 1 else "light"
        ctk.set_appearance_mode(theme)
        self.parent.config["theme"] = theme

    def _toggle_pro(self):
        on = self.pro_switch.get() == 1
        for dd in self.tier_widgets.values():
            dd.configure(state="normal" if on else "disabled")
        if on:
            self.pro_hint.configure(text="  (Enabled — reads master.m3u8)", text_color="#2ecc71")
            self.speed_opt.configure(state="disabled")
            self.pro_card.configure(fg_color="#1a2e1a")
        else:
            self.pro_hint.configure(text="  (Disabled)", text_color="gray")
            self.speed_opt.configure(state="normal")
            self.pro_card.configure(fg_color="#151515")

    def _run_tools_update(self):
        self.update_btn.configure(state="disabled", text="Updating...")
        def update_task():
            try:
                self.parent.log_callback("🔄 Starting OS-aware binary update check...\n")
                asyncio.run(capture_m3u8.update_nm3u8dl_re())
                asyncio.run(capture_m3u8.update_mkvtoolnix())
                asyncio.run(capture_m3u8.update_ffmpeg())
                self.parent.log_callback("✅ All tools checked and updated.\n")
            except Exception as e:
                self.parent.log_callback(f"❌ Update task failed: {e}\n")
            finally:
                self.after(0, lambda: self.update_btn.configure(state="normal", text="Check & Update Tools"))
                self.after(0, self._refresh_tool_paths)
        threading.Thread(target=update_task, daemon=True).start()

    def save_and_close(self):
        self.parent.config["movies_dir"] = self.movie_dir_entry.get()
        self.parent.config["tv_dir"] = self.tv_dir_entry.get()
        try:
            self.parent.config["min_cooldown"] = int(self.min_cool.get())
            self.parent.config["max_cooldown"] = int(self.max_cool.get())
        except: pass
        self.parent.config["download_speed"] = self.speed_opt.get()
        self.parent.config["theme"] = "dark" if self.dark_mode_switch.get() == 1 else "light"
        self.parent.config["headless"] = (self.headless_chk.get() == 1)
        self.parent.config["movie_template"] = self.movie_tpl_entry.get().strip()
        self.parent.config["tv_template"] = self.tv_tpl_entry.get().strip()
        self.parent.config["auto_speed_by_resolution"] = (self.pro_switch.get() == 1)
        self.parent.config["preferred_resolution"] = self.pref_res.get()
        self.parent.config["language"] = self.lang_opt.get()
        for key, dd in self.tier_widgets.items():
            self.parent.config[key] = dd.get()
        for key, ent in self.tool_entries.items():
            self.parent.config[key] = ent.get().strip()

        self.parent.config["scp_enabled"] = (self.scp_enabled_chk.get() == 1)
        self.parent.config["scp_host"] = self.scp_host_entry.get().strip()
        self.parent.config["scp_username"] = self.scp_user_entry.get().strip()
        self.parent.config["scp_auth_type"] = self.scp_auth_type.get()
        self.parent.config["scp_key_path"] = self.scp_key_entry.get().strip()
        self.parent.config["scp_password"] = self.scp_pw_entry.get()
        self.parent.config["scp_remote_movies_dir"] = self.scp_remote_movie_entry.get().strip()
        self.parent.config["scp_remote_tv_dir"] = self.scp_remote_tv_entry.get().strip()
        self.parent.config["scp_delete_local"] = (self.scp_delete_local_chk.get() == 1)

        self.parent.save_settings()
        self.destroy()


class DependencyInstallerDialog(ctk.CTkToplevel):
    """Startup dialog that detects missing binaries and offers auto-install or manual commands."""
    def __init__(self, parent, deps):
        super().__init__(parent)
        self.parent = parent
        self.deps = deps
        self.title("Missing Dependencies")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        parent.update_idletasks()
        w, h = 520, 420
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (w // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        ctk.CTkLabel(self, text="Missing Dependencies Detected", font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="The following tools are required but were not found.", text_color="gray").pack()

        scroll = ctk.CTkScrollableFrame(self, width=480, height=210)
        scroll.pack(padx=20, pady=15, fill="both", expand=True)

        self.dep_widgets = {}
        for dep in deps:
            self._add_dep_row(scroll, dep)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(5, 20))

        has_auto = any(d.get("auto") for d in deps)
        if has_auto:
            ctk.CTkButton(btn_frame, text="Install All Possible", fg_color="#27ae60", hover_color="#2ecc71", command=self._install_all).pack(side="left", padx=5)
        if sys.platform == 'win32':
            ctk.CTkButton(btn_frame, text="Try Fallback Bundle", fg_color="#e67e22", hover_color="#d35400", command=self._try_fallback).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Open Tools Tab", fg_color="#34495e", hover_color="#2c3e50", command=self._open_tools).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Skip", fg_color="transparent", border_width=1, command=self.destroy).pack(side="left", padx=5)

    def _add_dep_row(self, parent_frame, dep):
        row = ctk.CTkFrame(parent_frame, fg_color="#1a1a1a", corner_radius=6)
        row.pack(fill="x", pady=5, padx=5)

        name = dep["name"]
        auto = dep.get("auto", False)
        command = dep.get("command", "")

        ctk.CTkLabel(row, text=name, font=("Segoe UI", 12, "bold"), width=130, anchor="w").pack(side="left", padx=10, pady=10)

        status_lbl = ctk.CTkLabel(row, text="Not installed", text_color="#e74c3c", font=("Segoe UI", 10), width=180, anchor="w")
        status_lbl.pack(side="left", padx=5, pady=10, fill="x", expand=True)

        self.dep_widgets[name] = {"label": status_lbl}

        if auto:
            btn = ctk.CTkButton(row, text="Install", width=80, height=28, command=lambda d=dep: self._install_one(d))
            btn.pack(side="right", padx=10, pady=10)
            self.dep_widgets[name]["btn"] = btn
        else:
            cmd_lbl = ctk.CTkLabel(row, text=command, font=("Segoe UI", 10), wraplength=180, anchor="e")
            cmd_lbl.pack(side="right", padx=10, pady=10)
            self.dep_widgets[name]["cmd"] = cmd_lbl

    def _install_one(self, dep, rescan_all=False):
        name = dep["name"]
        widgets = self.dep_widgets.get(name, {})
        btn = widgets.get("btn")
        lbl = widgets.get("label")

        if btn:
            btn.configure(state="disabled", text="...")
        if lbl:
            lbl.configure(text="Installing...", text_color="#3498db")

        def task():
            try:
                updater = dep.get("updater")
                if updater == "nm3u8dl":
                    asyncio.run(capture_m3u8.update_nm3u8dl_re())
                elif updater == "ffmpeg":
                    asyncio.run(capture_m3u8.update_ffmpeg())
                elif updater == "mkvtoolnix":
                    asyncio.run(capture_m3u8.update_mkvtoolnix())
                else:
                    raise RuntimeError("No updater available")

                if rescan_all:
                    # Re-scan every dep in the dialog — one updater may install multiple binaries
                    still_missing = capture_m3u8.get_missing_binaries()
                    still_names = {d["name"] for d in still_missing}
                    for d in self.deps:
                        n = d["name"]
                        if n not in still_names:
                            self.after(0, lambda name=n: self._mark_done(name))
                        else:
                            self.after(0, lambda name=n: self._mark_failed(name, "Not found after install"))
                else:
                    # Verify only this dep
                    path = capture_m3u8.find_binary(dep["binary"], dep.get("config_key"))
                    if path and os.path.exists(path):
                        self.after(0, lambda n=name: self._mark_done(n))
                    else:
                        self.after(0, lambda n=name: self._mark_failed(n, "Not found after install"))
            except Exception as e:
                self.after(0, lambda n=name, err=str(e): self._mark_failed(n, err))

        threading.Thread(target=task, daemon=True).start()

    def _try_fallback(self):
        """Download the consolidated fallback bundle and refresh statuses."""
        def task():
            try:
                asyncio.run(capture_m3u8.download_fallback_binaries())
                # Re-check which are still missing
                still_missing = capture_m3u8.get_missing_binaries()
                still_names = {d["name"] for d in still_missing}
                for dep in self.deps:
                    n = dep["name"]
                    if n not in still_names:
                        self.after(0, lambda name=n: self._mark_done(name))
                    else:
                        self.after(0, lambda name=n: self._mark_failed(name, "Still missing after fallback"))
            except Exception as e:
                for dep in self.deps:
                    n = dep["name"]
                    self.after(0, lambda name=n, err=str(e): self._mark_failed(name, err))

        threading.Thread(target=task, daemon=True).start()

    def _install_all(self):
        """Install missing tools, deduplicating shared updaters to avoid races."""
        seen_updaters = set()
        for dep in self.deps:
            if dep.get("auto") and dep.get("updater") not in seen_updaters:
                seen_updaters.add(dep.get("updater"))
                self._install_one(dep, rescan_all=True)

    def _mark_done(self, name):
        widgets = self.dep_widgets.get(name, {})
        btn = widgets.get("btn")
        lbl = widgets.get("label")
        if lbl:
            lbl.configure(text="Installed ✅", text_color="#2ecc71")
        if btn:
            btn.configure(state="disabled", text="Done")
        # Update parent config with the actual discovered path so settings show it
        for dep in self.deps:
            if dep["name"] == name:
                path = capture_m3u8.find_binary(dep["binary"], dep.get("config_key"))
                if path and os.path.exists(path):
                    self.parent.config[dep["config_key"]] = path
                break
        self._check_all_done()

    def _mark_failed(self, name, error):
        widgets = self.dep_widgets.get(name, {})
        btn = widgets.get("btn")
        lbl = widgets.get("label")
        short_err = error[:40] + "..." if len(error) > 40 else error
        if lbl:
            lbl.configure(text=f"Failed: {short_err}", text_color="#e74c3c")
        if btn:
            btn.configure(state="normal", text="Retry")
        self._check_all_done()

    def _check_all_done(self):
        """Auto-close the dialog once every tracked binary is present locally."""
        try:
            if not capture_m3u8.get_missing_binaries():
                self.after(600, self.destroy)
        except Exception:
            pass

    def _open_tools(self):
        self.destroy()
        self.parent.open_settings(open_tab="Tools")


class M3U8DownloaderApp(ctk.CTk):
    def __init__(self):
        # Set AppUserModelID first so the taskbar icon matches the window icon
        try:
            myappid = 'ytlink.m3u8hunter.gui.1.1' # Changed ID slightly to invalidate Windows cache
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
            
        # --- BUG FIX: Clean up stale browser session on GUI startup ---
        capture_m3u8.cleanup_stale_browser_session()
            
        super().__init__()

        self.title("M3U8 Hunter & Downloader - Beta")

        # Set window icon synchronously
        try:
            icon_path = capture_m3u8.get_resource_path('binaries/icon2.ico')
            if sys.platform.startswith('linux'):
                # Linux doesn't support .ico for window icons well, use PIL to set it
                from PIL import Image, ImageTk
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, photo)
                # Keep a reference to prevent garbage collection
                self._icon_photo = photo
            else:
                # Windows handles .ico natively for window and taskbar
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
        self.last_ended_with_cr = False
        self.settings_window = None
        
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
        # load_settings() is no longer needed to populate widgets since they are in the Settings window
        
        # Start Log Monitor
        self.after(100, self.process_log_queue)

        # Startup check: if critical binaries are missing, nudge user to Tools tab
        self.after(600, self.check_missing_binaries)

    def check_missing_binaries(self):
        """Detect missing binaries and show the DependencyInstallerDialog."""
        deps = capture_m3u8.get_missing_binaries()
        if deps:
            DependencyInstallerDialog(self, deps)

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

        self.stop_btn = ctk.CTkButton(self.input_frame, text="Stop", command=self.stop_process, fg_color="red", width=60, state="disabled")
        self.stop_btn.pack(side="right", padx=5)

        self.top250_btn = ctk.CTkButton(self.input_frame, text="Top 250 Movies", command=self.open_top250, fg_color="blue", width=120)
        self.top250_btn.pack(side="right", padx=5)

        self.queue_btn = ctk.CTkButton(self.input_frame, text="Load Queue", command=self.load_queue, fg_color="purple", width=100)
        self.queue_btn.pack(side="right", padx=5)

        self.check_btn = ctk.CTkButton(self.input_frame, text="Check Availability", command=self.check_availability, fg_color="orange", width=120)
        self.check_btn.pack(side="right", padx=5)

        self.open_settings_btn = ctk.CTkButton(self.input_frame, text="⚙️", command=self.open_settings, width=40, fg_color="gray")
        self.open_settings_btn.pack(side="right", padx=5)

        # Bind Enter key to search
        self.url_entry.bind("<Return>", lambda e: self.search_content())

        # ── Professional Status Bar ──
        self.status_bar = ctk.CTkFrame(self, height=42, fg_color="#1a1a1a", corner_radius=6)
        self.status_bar.pack(fill="x", padx=10, pady=(0, 5))
        self.status_bar.grid_propagate(False)
        for c, w in [(0, 0), (1, 0), (2, 1), (3, 0)]:
            self.status_bar.grid_columnconfigure(c, weight=w)

        self.status_icon = ctk.CTkLabel(self.status_bar, text="🔵", font=("Segoe UI", 14), width=28)
        self.status_icon.grid(row=0, column=0, padx=(10, 2), pady=5)
        self.status_text = ctk.CTkLabel(self.status_bar, text="Idle", font=("Segoe UI", 12, "bold"), text_color="#3498db")
        self.status_text.grid(row=0, column=1, padx=(0, 10), pady=5, sticky="w")
        self.progress_bar = ctk.CTkProgressBar(self.status_bar, height=16, corner_radius=8)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=2, padx=10, pady=5, sticky="ew")
        self.counter_lbl = ctk.CTkLabel(self.status_bar, text="—", font=("Segoe UI", 11, "bold"), width=70)
        self.counter_lbl.grid(row=0, column=3, padx=(5, 15), pady=5, sticky="e")

        # --- Current Title Display (full width, between status bar and logs) ---
        self.current_title_frame = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self.current_title_frame.pack(fill="x", padx=10, pady=(5, 0))
        self.current_title_frame.pack_propagate(False)
        self.current_title_lbl = ctk.CTkLabel(self.current_title_frame, text="", font=("Segoe UI", 11, "bold"), text_color="#dddddd", anchor="w")
        self.current_title_lbl.pack(side="left", padx=10, fill="x", expand=True)

        # --- Bottom Section: Logs ---
        self.log_header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.log_header_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        ctk.CTkLabel(self.log_header_frame, text="Activity Log", font=("", 13, "bold")).pack(side="left")

        self.clear_log_btn = ctk.CTkButton(self.log_header_frame, text="Clear", width=60, height=24, fg_color="transparent", border_width=1, command=self.clear_logs)
        self.clear_log_btn.pack(side="right")

        self.log_box = ctk.CTkTextbox(self, font=("Segoe UI", 11))
        self.log_box.pack(pady=(5, 10), padx=10, fill="both", expand=True)
        self.log_box.configure(state="disabled")
        
        # Configure Tags for Color Coding
        self.log_box.tag_config("success", foreground="#2ecc71")
        self.log_box.tag_config("error", foreground="#e74c3c")
        self.log_box.tag_config("warning", foreground="#f39c12")
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

    def open_settings(self, open_tab=None):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = SettingsWindow(self, open_tab=open_tab)
        else:
            self.settings_window.focus()
            if open_tab:
                self.settings_window.tabs.set(open_tab)

    def save_settings(self):
        """Save current configuration to disk."""
        # Update geometry in config
        self.config["window_geometry"] = self.geometry()
        
        # Update core config
        capture_m3u8.setup_interface(config_data=self.config)
        
        # Save to file safely (prevents overwriting manual edits like API keys)
        try:
            capture_m3u8.save_config(self.config)
        except Exception as e:
            self.log_callback(f"Failed to save config: {e}")

    def log_callback(self, message):
        # We don't print to console here as the core logic's log() already does it via setup_interface
        self.log_queue.put(message)

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def reload_plugins(self):
        pm = capture_m3u8.PluginManager()
        names = pm.get_plugin_names()
        self.log_callback(f"🔌 Plugins reloaded. Found {len(names)} active plugin(s) in /plugins folder.\n")
        for i, name in enumerate(names, 1):
            self.log_callback(f"   {i}. {name}\n")

    STATUS_MAP = {
        "Idle":        ("#3498db", "🔵", "Idle"),
        "Hunting":     ("#e67e22", "🟠", "Hunting..."),
        "Downloading": ("#2ecc71", "🟢", "Downloading"),
        "Cooling":     ("#9b59b6", "⏳", "Cooling down"),
        "Error":       ("#e74c3c", "❌", "Error"),
        "Success":     ("#2ecc71", "✅", "Success"),
    }

    def update_status_bar(self, state=None, message=None, progress=None, counter=None, title=None):
        """Unified status bar updater. Call from any thread via self.after()."""
        def _apply():
            if state and state in self.STATUS_MAP:
                color, icon, default_text = self.STATUS_MAP[state]
                self.status_text.configure(text=message or default_text, text_color=color)
                self.status_icon.configure(text=icon)
            elif message:
                self.status_text.configure(text=message)
            if progress is not None:
                self.progress_bar.set(float(progress))
            if counter is not None:
                self.counter_lbl.configure(text=counter)
            if title is not None:
                self.current_title_lbl.configure(text=title if title else "")
        self.after(0, _apply)

    def status_callback(self, message):
        # Route CLI status messages to the status bar without hijacking the Start button
        msg_lower = message.lower()
        if "hunting" in msg_lower:
            self.update_status_bar("Hunting")
        elif "download" in msg_lower or "dl:" in msg_lower:
            self.update_status_bar("Downloading")
        elif "cool" in msg_lower:
            self.update_status_bar("Cooling")
        elif "error" in msg_lower:
            self.update_status_bar("Error")
        elif "success" in msg_lower:
            self.update_status_bar("Success")
        else:
            self.update_status_bar(message=message)

    def check_stop_callback(self):
        return self.stop_event.is_set()

    def process_log_queue(self):
        while not self.log_queue.empty():
            msg = str(self.log_queue.get())

            # Sync status bar title with "🎬 Title: ..." log lines
            if '🎬 Title:' in msg:
                try:
                    title = msg.split('🎬 Title:')[1].strip()
                    if title:
                        self.update_status_bar(title=title)
                except Exception:
                    pass

            self.log_box.configure(state="normal")
            
            # Simple color mapping based on icons
            tag = None
            if any(x in msg for x in ["✅", "💾", "Success"]): tag = "success"
            elif any(x in msg for x in ["❌", "FAILED", "Error"]): tag = "error"
            elif any(x in msg for x in ["⚠️", "Warning"]): tag = "warning"
            elif any(x in msg for x in ["🔍", "🕵️", "⚡", "📝"]): tag = "info"
            
            # Robust overwrite for FFmpeg signatures as per user request
            if ("frame=" in msg.lower() or "size=" in msg.lower()) and not msg.startswith('\033'):
                if not msg.startswith('\r') and not self.last_ended_with_cr:
                    msg = '\r' + msg

            # Handle Carriage Returns for overwriting lines (FFmpeg progress)
            if '\r' in msg:
                parts = msg.split('\r')
                for i, part in enumerate(parts):
                    if i == 0:
                        # First part: if last msg ended with \r and we have new content, overwrite
                        if self.last_ended_with_cr and part:
                             self.log_box.delete("end-1c linestart", "end-1c")
                        if part:
                             self.log_box.insert("end", part, tag)
                    else:
                        # Subsequent parts (\r encountered within this msg)
                        # Only delete if there is a 'part' to replace it with
                        if part:
                            self.log_box.delete("end-1c linestart", "end-1c")
                            self.log_box.insert("end", part, tag)
                
                self.last_ended_with_cr = msg.endswith('\r')
            else:
                # Normal message without \r
                if self.last_ended_with_cr:
                    # If last one was an incomplete overwrite, just proceed
                    self.last_ended_with_cr = False
                self.log_box.insert("end", msg, tag)

            # Keep scroll at bottom
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self.process_log_queue)

    def input_callback(self, prompt):
        # This runs in the background thread.
        # We need to ask the user on the main thread.
        print(f"DEBUG: Input requested: {prompt}") # Console fallback
        
        # Schedule the dialog on main thread and wait for response
        self.input_value = None
        self.input_event.clear()
        self.after(0, lambda: self.show_input_dialog(prompt))
        self.input_event.wait()
        
        return self.input_value if self.input_value is not None else "s"

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

    def _on_finish(self):
        """Reset GUI state after processing is complete."""
        self.is_running = False
        self.stop_event.clear()
        self.update_status_bar("Idle")
        self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))
        self.after(0, lambda: self.stop_btn.configure(state="disabled"))
        self.after(0, lambda: self.top250_btn.configure(state="normal"))
        self.after(0, lambda: self.queue_btn.configure(state="normal"))
        self.after(0, lambda: self.check_btn.configure(state="normal"))

    def run_logic(self, url):
        # Flush IMDB cache before starting a new logic run/download
        capture_m3u8.flush_imdb_cache()
        is_imdb = "imdb.com/title/" in url
        was_bypass = self.bypass_dialog
        
        try:
            # Check for IMDB Links (Series or Movie)
            if is_imdb and not was_bypass:
                match = re.search(r'(tt\d+)', url)
                if match:
                    imdb_id = match.group(1)
                    # Clear search images since we are technically starting a "search" logic
                    self.search_images = []
                    def on_meta(meta):
                        try:
                            if meta and meta.get('type') == 'tv':
                                threading.Thread(target=lambda: asyncio.run(self.handle_imdb_series(imdb_id, url)), daemon=True).start()
                            else:
                                self.check_for_media_save(url)
                                # For non-series/movies, if we just showed a dialog, we might be finished with the "Hunting" phase of the button
                                # but wait, check_for_media_save usually leads to another start_process.
                        except Exception as e:
                            self.log_callback(f"\n❌ Error in metadata handling: {e}\n")
                        finally:
                            if not meta or meta.get('type') != 'tv':
                                self._on_finish()
                            
                    threading.Thread(target=lambda: on_meta(asyncio.run(capture_m3u8.get_imdb_info(imdb_id))), daemon=True).start()
                    return # The thread will handle the rest, but we need to ensure it calls _on_finish
            
            # Reset bypass for the next run
            self.bypass_dialog = False

            # Normal Single Video
            headless = self.config.get("headless", True)
            self.update_status_bar("Hunting", message="Processing movie...")
            success = asyncio.run(capture_m3u8.process_video(url, headless=headless, auto_mode=True))
            
            # Log successful single downloads to completed.log
            completed_log = os.path.join(capture_m3u8.get_log_dir(), "completed.log")
            if isinstance(success, str) and success != "404":
                if os.path.exists(success) and os.path.getsize(success) > 5 * 1024 * 1024:
                    try:
                        with open(completed_log, 'a', encoding='utf-8') as f:
                            f.write(f"{url}\n")
                        self.log_callback("✅ Marked as complete.\n")
                    except Exception as e:
                        self.log_callback(f"⚠️ Failed to update completed.log: {e}\n")
            
        except Exception as e:
            self.log_callback(f"\n❌ Error: {e}\n")
        finally:
            # Only reset here if we didn't return early to a background thread
            if not is_imdb or was_bypass:
                self._on_finish()

    async def handle_imdb_series(self, imdb_id, original_url):
        try:
            self.log_callback(f"🕵️  Analyzing IMDB Series: {imdb_id}...\n")
            
            # Optimization: Use a shared browser context for all IMDB scans in this session
            from playwright.async_api import async_playwright
            capture_m3u8.ensure_playwright_browsers()
            
            async with async_playwright() as p:
                if sys.platform.startswith('linux'):
                    exec_path = capture_m3u8.get_browser_executable("firefox")
                    if not exec_path: return
                    browser = await p.firefox.launch(headless=True, executable_path=exec_path)
                else:
                    exec_path = capture_m3u8.get_browser_executable("chromium")
                    if not exec_path: return
                    browser = await p.chromium.launch(headless=True, executable_path=exec_path)
                
                shared_page = await browser.new_page(user_agent=capture_m3u8.USER_AGENT)
                
                meta = await capture_m3u8.get_imdb_info(imdb_id, page=shared_page)
                
                if not meta:
                    self.log_callback("❌ Failed to fetch IMDB info.\n")
                    await browser.close()
                    self._on_finish()
                    return
    
                if meta['type'] != 'tv':
                    # It's a movie, proceed normally
                    headless = self.config.get("headless", True)
                    await capture_m3u8.process_video(original_url, headless=headless, auto_mode=True)
                    await browser.close()
                    self._on_finish()
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
                    await browser.close()
                    self._on_finish()
                    return
    
                # Generate Queue
                queue_list = []
                
                if selection['season'] == 'all':
                    self.log_callback(f"   Fetching info for ALL {meta['seasons']} seasons...\n")
                    for s in range(1, meta['seasons'] + 1):
                        ep_count = await capture_m3u8.get_season_episodes(imdb_id, s, page=shared_page)
                        self.log_callback(f"   Season {s}: {ep_count} episodes.\n")
                        for e in range(1, ep_count + 1):
                            link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                            queue_list.append(link)
                else:
                    s = selection['season']
                    ep_count = await capture_m3u8.get_season_episodes(imdb_id, s, page=shared_page)
                    self.log_callback(f"   Season {s} has {ep_count} episodes.\n")
                    
                    start = selection.get('ep_start', 1)
                    end = selection.get('ep_end', ep_count)
                    
                    # Bounds check
                    if end > ep_count: end = ep_count
                    
                    for e in range(start, end + 1):
                        link = f"https://vidsrcme.ru/embed/tv?imdb={imdb_id}&season={s}&episode={e}"
                        queue_list.append(link)
                
                await browser.close()
                
            # Setup Resume Logic
            finder = capture_m3u8.MasterM3U8Finder()
            safe_title = finder.sanitize_filename(meta['title'])
            tv_dir = self.config.get('tv_dir')
            if not tv_dir or tv_dir == ".":
                tv_dir = os.path.join(capture_m3u8.get_base_dir(), "TV")
                
            series_dir = os.path.join(tv_dir, safe_title)
            
            # Global completed.log
            completed_log = os.path.join(capture_m3u8.get_log_dir(), "completed.log")
            completed_urls = set()
            completed_episodes = set() # Store (imdb_id, season, episode) tuples

            if os.path.exists(completed_log):
                try:
                    with open(completed_log, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line: continue
                            completed_urls.add(line)
                            
                            # Extract IMDB ID and season/episode for robust matching
                            imdb_m = re.search(r'imdb=(tt\d+)', line)
                            s_match = re.search(r'[?&]season=(\d+)', line)
                            e_match = re.search(r'[?&]episode=(\d+)', line)
                            if imdb_m and s_match and e_match:
                                completed_episodes.add((imdb_m.group(1), int(s_match.group(1)), int(e_match.group(1))))
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
                        if (imdb_id, s_num, e_num) in completed_episodes:
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

            this_series_count = sum(1 for cid, s, e in completed_episodes if cid == imdb_id)
            if this_series_count > 0:
                self.log_callback(f"📂 Found resume data: {this_series_count} episodes previously completed for this series.\n")
            if skipped_count > 0:
                self.log_callback(f"   {skipped_count} of the currently selected episodes will be skipped.\n")
            
            # --- Silently auto-save the queue to temp folder ---
            temp_dir = os.path.join(capture_m3u8.get_base_dir(), "temp_downloads")
            os.makedirs(temp_dir, exist_ok=True)
            quu_path = os.path.join(temp_dir, f"{safe_title}.quu")
            try:
                with open(quu_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(queue_list))
                self.log_callback(f"💾 Queue auto-saved to: {os.path.basename(quu_path)}\n")
            except Exception as e:
                self.log_callback(f"⚠️ Failed to auto-save .quu file: {e}\n")

            self.log_callback(f"🚀 Queued {len(queue_list)} episodes. Starting batch...\n")
            # Ensure UI state is correct before batch processing
            self.is_running = True
            self.after(0, lambda: self.start_btn.configure(state="disabled", text="Running..."))
            self.after(0, lambda: self.stop_btn.configure(state="normal"))
            self.after(0, lambda: self.top250_btn.configure(state="disabled"))
            self.after(0, lambda: self.queue_btn.configure(state="disabled"))
            self.after(0, lambda: self.check_btn.configure(state="disabled"))
            # Process Queue
            headless = self.config.get("headless", True)
            
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
                        if (imdb_id, s_num, e_num) in completed_episodes:
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
                self.update_status_bar("Downloading", counter=f"{i+1} / {len(queue_list)}", progress=(i+1)/len(queue_list))
                success = await capture_m3u8.process_video(link, headless=headless, auto_mode=True)
                
                if isinstance(success, str) and success != "404":
                    if os.path.exists(success) and os.path.getsize(success) > 5 * 1024 * 1024:
                        try:
                            with open(completed_log, 'a', encoding='utf-8') as f:
                                f.write(f"{link}\n")
                            completed_urls.add(link)
                        except Exception as e:
                            self.log_callback(f"⚠️ Failed to update completed.log: {e}\n")
                    else:
                        self.log_callback(f"⚠️ File missing or too small after processing. Not marking complete.\n")
                elif success == "404":
                    self.log_callback(f"⏭️ Skipping 404 item...\n")
                
                if i < len(queue_list) - 1:
                    wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                    self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                    capture_m3u8.report_status(f"Cooling down {wait}s...")
                    await asyncio.sleep(wait)
        except Exception as e:
            self.log_callback(f"\n❌ Error in series handler: {e}\n")
        finally:
            self._on_finish()

    def _silent_save_queue(self, queue_list, series_title, series_dir):
        """Silently save the queue as a .quu file to the series directory."""
        # Clean title and try to extract year: "Title (1990)" -> "Title (1990)"
        match = re.search(r'^(.*?)\s*\((\d{4})\)$', series_title)
        if match:
            clean_name = f"{match.group(1).strip()} ({match.group(2)})"
        else:
            clean_name = series_title.replace(':', ' -').replace('/', '-').replace('\\', '-')
        
        safe_title = capture_m3u8.MasterM3U8Finder().sanitize_filename(clean_name)
        temp_dir = os.path.join(capture_m3u8.get_base_dir(), "temp_downloads")
        os.makedirs(temp_dir, exist_ok=True)
        quu_path = os.path.join(temp_dir, f"{safe_title}.quu")
        try:
            with open(quu_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(queue_list))
            self.log_callback(f"💾 Queue auto-saved to series directory (.quu)\n")
        except Exception as e:
            self.log_callback(f"⚠️ Failed to auto-save .quu file: {e}\n")
        self.input_event.set()

    def show_series_dialog(self, meta):
        # A custom Toplevel window for selection
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Season/Episodes")
        
        w, h = 320, 300
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.attributes("-topmost", True)
        
        # Header with counts
        total_eps = meta.get('total_episodes', 0)
        eps_str = f" | Total Episodes: {total_eps}" if total_eps > 0 else ""
        header_text = f"Seasons: {meta['seasons']}{eps_str}"
        ctk.CTkLabel(dialog, text=header_text, font=("Segoe UI", 12, "bold"), text_color="#3498db").pack(pady=(10, 5))
        
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
            
        def on_cancel():
            self.input_value = None
            self.input_event.set()
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        ctk.CTkButton(btn_frame, text="Download", command=on_confirm, width=100).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", command=on_cancel, fg_color="#e74c3c", hover_color="#c0392b", width=100).pack(side="left", padx=10)
        
        # Handle window close
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

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
        
        w, h = 500, 600
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
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
        headless = self.config.get("headless", True)
        
        try:
            for i, m in enumerate(movies):
                if self.stop_event.is_set():
                    self.log_callback("\n🛑 Batch processing stopped by user.\n")
                    break
                self.log_callback(f"\n--- Processing {i+1}/{len(movies)}: {m['title']} ---\n")
                self.update_status_bar("Downloading", counter=f"{i+1} / {len(movies)}", progress=(i+1)/len(movies))
                success = asyncio.run(capture_m3u8.process_video(m['url'], headless=headless, auto_mode=True))
                
                # Log successful downloads to completed.log
                if isinstance(success, str) and success != "404":
                    if os.path.exists(success) and os.path.getsize(success) > 5 * 1024 * 1024:
                        try:
                            with open(completed_log, 'a', encoding='utf-8') as f:
                                f.write(f"{m['url']}\n")
                            self.log_callback("   ✅ Marked as complete.\n")
                        except Exception as e:
                            self.log_callback(f"   ⚠️ Failed to update completed.log: {e}\n")
                
                if i < len(movies) - 1:
                    wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                    self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                    capture_m3u8.report_status(f"Cooling down {wait}s...")
                    time.sleep(wait)
                    
        except Exception as e:
            self.log_callback(f"\n❌ Batch Error: {e}\n")
        finally:
            self.update_status_bar("Idle")
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
        
        # Clear the internal log queue to prevent "ghost" messages from previous runs
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        
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
        completed_log = os.path.join(capture_m3u8.get_log_dir(), "completed.log")
        
        completed_urls = set()
        completed_episodes = set()
        completed_movies = set()
        
        if os.path.exists(completed_log):
            try:
                with open(completed_log, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        completed_urls.add(line)
                        
                        imdb_m = re.search(r'(tt\d{7,})', line)
                        s_match = re.search(r'[?&]season=(\d+)', line)
                        e_match = re.search(r'[?&]episode=(\d+)', line)
                        
                        if imdb_m:
                            imdb_id = imdb_m.group(1)
                            if s_match and e_match:
                                # TV Episode
                                completed_episodes.add((imdb_id, int(s_match.group(1)), int(e_match.group(1))))
                            else:
                                # Movie
                                completed_movies.add(imdb_id)
                self.log_callback(f"📂 Found resume log with {len(completed_urls)} entries.\n")
            except Exception as e:
                self.log_callback(f"⚠️ Error reading completed.log: {e}\n")

        headless = self.config.get("headless", True)
        
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
                else:
                    # Robust check using IMDB ID
                    curr_imdb_m = re.search(r'(tt\d{7,})', url)
                    curr_s_match = re.search(r'[?&]season=(\d+)', url)
                    curr_e_match = re.search(r'[?&]episode=(\d+)', url)
                    
                    if curr_imdb_m:
                        imdb_id = curr_imdb_m.group(1)
                        if curr_s_match and curr_e_match:
                            s_num, e_num = int(curr_s_match.group(1)), int(curr_e_match.group(1))
                            if (imdb_id, s_num, e_num) in completed_episodes:
                                is_completed = True
                                skip_reason = f"in completed.log (Identified S{s_num:02d}E{e_num:02d})"
                        elif imdb_id in completed_movies:
                            is_completed = True
                            skip_reason = f"in completed.log (Movie IMDB: {imdb_id})"

                if not is_completed and is_tv_queue and series_dir:
                    s_match = re.search(r'[?&]season=(\d+)', url)
                    e_match = re.search(r'[?&]episode=(\d+)', url)
                    if s_match and e_match:
                        s_num, e_num = int(s_match.group(1)), int(e_match.group(1))
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
                self.update_status_bar("Downloading", counter=f"{i+1} / {len(urls)}", progress=(i+1)/len(urls))
                
                success = asyncio.run(capture_m3u8.process_video(url, headless=headless, auto_mode=True))
                
                if isinstance(success, str) and success != "404":
                    if os.path.exists(success) and os.path.getsize(success) > 5 * 1024 * 1024:
                        try:
                            with open(completed_log, 'a', encoding='utf-8') as f:
                                f.write(f"{url}\n")
                            completed_urls.add(url)
                        except Exception as e:
                            self.log_callback(f"⚠️ Failed to update completed.log: {e}\n")
                    else:
                        self.log_callback(f"⚠️ File missing or too small after processing. Not marking complete.\n")
                elif success == "404":
                    self.log_callback(f"⏭️ Skipping 404 item...\n")
                
                if i < len(urls) - 1:
                    wait = random.randint(self.config['min_cooldown'], self.config['max_cooldown'])
                    self.log_callback(f"⏳ Cooling down for {wait} seconds...\n")
                    capture_m3u8.report_status(f"Cooling down {wait}s...")
                    # Interruptible sleep
                    self.stop_event.wait(wait)
                    
        except Exception as e:
            self.log_callback(f"\n❌ Queue Error: {e}\n")
        finally:
            self.update_status_bar("Idle")
            self.is_running = False
            self.stop_event.clear()
            self.after(0, lambda: self.start_btn.configure(state="normal", text="Start / Analyze"))
            self.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.after(0, lambda: self.top250_btn.configure(state="normal"))
            self.after(0, lambda: self.queue_btn.configure(state="normal"))
            self.after(0, lambda: self.check_btn.configure(state="normal"))

    def _confirm_quit(self):
        """Custom Yes/Cancel quit confirmation dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Quit")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        x = self.winfo_x() + (self.winfo_width() // 2) - 150
        y = self.winfo_y() + (self.winfo_height() // 2) - 80
        dialog.geometry(f"300x130+{x}+{y}")

        ctk.CTkLabel(dialog, text="A download is in progress.\nDo you want to stop and quit?",
                     font=("Segoe UI", 12)).pack(pady=(15, 10))

        result = False
        def on_yes():
            nonlocal result
            result = True
            dialog.destroy()
        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="Yes", command=on_yes, width=80,
                      fg_color="#e74c3c", hover_color="#c0392b").pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", command=on_cancel, width=80).pack(side="left", padx=10)

        self.wait_window(dialog)
        return result

    def on_closing(self):
        # Only persist window geometry on close to avoid clobbering manual edits
        try:
            latest_config, _ = capture_m3u8.load_config()
        except Exception:
            latest_config = {}
        latest_config["window_geometry"] = self.geometry()
        try:
            capture_m3u8.save_config(latest_config)
        except Exception as e:
            self.log_callback(f"Failed to save config: {e}")

        if self.is_running:
            if self._confirm_quit():
                self.stop_process()
                capture_m3u8.terminate_all_downloads()
                self.destroy()
        else:
            capture_m3u8.terminate_all_downloads()
            capture_m3u8.clear_session(reason="GUI shutdown")
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
                # Fetch metadata to see if it's a series or movie
                meta = asyncio.run(capture_m3u8.get_imdb_info(imdb_id))
                is_tv = (meta and meta.get('type') == 'tv')
                
                # Perform content-based verification
                available, status_msg = asyncio.run(capture_m3u8.check_embed_availability(imdb_id, is_tv))
                
                result_icon = "✅" if available else "❌"
                msg = f"Type: {'TV Series' if is_tv else 'Movie'}\nAvailability: {status_msg} {result_icon}"
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
        
        # Standardize window appearance for PyInstaller/Cross-platform
        dialog.update()
        dialog.focus_force()
        
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
            # 1. Start with Cache (fastest)
            meta = capture_m3u8.IMDB_CACHE.get(imdb_id)
            # If cached entry is from search (missing full details like seasons), force re-fetch for TV
            if meta and meta.get('type') == 'tv' and 'seasons' not in meta:
                meta = None
                
            if not meta:
                # Fallback to fetching basic metadata if not in cache
                try:
                    meta = asyncio.run(asyncio.wait_for(capture_m3u8.get_imdb_info(imdb_id), timeout=20))
                except Exception as e:
                    self.log_callback(f"⚠️ Metadata fetch timed out: {e}\n")
                    # If we can't even get basic info, we still need a fallback
                    if not meta: return 

            if not meta:
                return
            
            is_tv = (meta.get('type') == 'tv')
            # 2. Content verification check (with timeout)
            available = False
            status_msg = "Checking status..."
            try:
                available, status_msg = asyncio.run(asyncio.wait_for(capture_m3u8.check_embed_availability(imdb_id, is_tv), timeout=10))
            except Exception as e:
                status_msg = f"Availability Timeout ({e})"
                available = False
                
            def on_dialog_close(action):
                if action == "save_queue":
                    threading.Thread(target=self.run_full_series_queue_save, args=(imdb_id, meta), daemon=True).start()
                elif action == "add_to_queue":
                    movie_url = f"https://vsembed.ru/embed/movie?imdb={imdb_id}"
                    threading.Thread(target=self.run_movie_append, args=(movie_url, meta), daemon=True).start()
                elif action == "download_now" or action == "just_episode":
                    if is_tv:
                        threading.Thread(target=lambda: asyncio.run(self.handle_imdb_series(imdb_id, url)), daemon=True).start()
                    else:
                        self.bypass_dialog = True
                        self.after(0, self.start_process)
            
            # 3. Always show dialog if we have basic metadata
            self.after(0, lambda: MediaSaveDialog(self, meta, img_url, status_msg, available, on_dialog_close))
            
        except Exception as e:
            self.log_callback(f"❌ Dialog Error: {e}")
            import traceback
            traceback.print_exc()

    def run_movie_append(self, movie_url, meta):
        """Append a movie URL to a .quu file."""
        self.update_status_bar(message="Queueing...")
        
        def pick_and_append():
            finder = capture_m3u8.MasterM3U8Finder()
            safe_title = finder.sanitize_filename(meta['title'])
            
            filename = filedialog.asksaveasfilename(
                title="Select Queue File to Append To",
                defaultextension=".quu",
                initialfile="Movie_Queue.quu",
                filetypes=[("Queue Files", "*.quu"), ("All Files", "*.*")],
                confirmoverwrite=False
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
            
            self._on_finish()
            
        self.after(0, pick_and_append)

    def run_full_series_queue_save(self, imdb_id, meta):
        """Fetch all episodes and save to .quu file."""
        try:
            self.log_callback(f"📝 Building full series queue for: {meta['title']}...\n")
            
            async def fetch_all():
                q = []
                num_seasons = meta.get('seasons', 1)
                for s in range(1, num_seasons + 1):
                    # Update status
                    self.update_status_bar(message=f"Fetching S{s:02d}...")
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
                finder = capture_m3u8.MasterM3U8Finder()
                title_str = meta['title']
                match = re.search(r'^(.*?)\s*\((\d{4})\)$', title_str)
                if match:
                    clean_name = f"{match.group(1).strip()}.{match.group(2)}"
                else:
                    # Fallback if no year in title, check if we have series start year in meta
                    clean_name = title_str
                    if meta.get('year'): # or similar
                        pass 
                
                safe_title = finder.sanitize_filename(clean_name)
                default_name = f"{safe_title}.quu"
                filename = filedialog.asksaveasfilename(
                    title="Select Queue File",
                    defaultextension=".quu",
                    initialfile=default_name,
                    filetypes=[("Queue Files", "*.quu"), ("All Files", "*.*")],
                    confirmoverwrite=False
                )
                if filename:
                    try:
                        # Use append mode and ensure data starts on a new line if file exists
                        mode = 'a' if os.path.exists(filename) else 'w'
                        with open(filename, mode, encoding='utf-8') as f:
                            if mode == 'a':
                                with open(filename, 'rb') as fr:
                                    fr.seek(0, 2)
                                    if fr.tell() > 0:
                                        fr.seek(-1, 2)
                                        if fr.read(1) != b'\n':
                                            f.write('\n')
                            f.write('\n'.join(queue_list) + '\n')
                        self.log_callback(f"💾 Full series queue appended to: {os.path.basename(filename)}\n")
                    except Exception as e:
                        self.log_callback(f"⚠️ Failed to save queue: {e}\n")
                
                self._on_finish()
                        
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