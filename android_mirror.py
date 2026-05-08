#!/usr/bin/env python3
"""
AndroidMirror - Mirror Android display to laptop via USB-C
=========================================================
Requirements:
  - Python 3.8+
  - ADB (Android Debug Bridge) installed and in PATH
  - scrcpy (recommended) OR ffmpeg (fallback)

Android Setup:
  1. Enable Developer Options (tap Build Number 7 times)
  2. Enable USB Debugging in Developer Options
  3. Connect device via USB-C cable
  4. Accept the "Allow USB Debugging" prompt on your Android device
"""

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import os
import json
import shutil
from dataclasses import dataclass, asdict
from typing import Optional, List

# ─────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────

@dataclass
class MirrorSettings:
    resolution:   str  = "1080"      # max height in px
    bitrate:      str  = "8M"        # video bitrate
    fps:          str  = "60"        # max frames per second
    window_title: str  = "Android Mirror"
    stay_on_top:  bool = False
    show_touches: bool = False
    fullscreen:   bool = False
    turn_off_screen: bool = False
    no_audio:     bool = False
    window_x:     str  = "50"
    window_y:     str  = "50"
    window_w:     str  = "400"
    window_h:     str  = "720"

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".android_mirror_settings.json")

def load_settings() -> MirrorSettings:
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        s = MirrorSettings()
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
        return s
    except Exception:
        return MirrorSettings()

def save_settings(s: MirrorSettings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(asdict(s), f, indent=2)
    except Exception:
        pass

# ─────────────────────────────────────────────
# ADB Helpers
# ─────────────────────────────────────────────

def run_adb(*args, timeout=5) -> tuple[bool, str]:
    """Run an adb command, return (success, output)."""
    try:
        result = subprocess.run(
            ["adb", *args],
            capture_output=True, text=True, timeout=timeout
        )
        return True, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return False, "adb not found"
    except subprocess.TimeoutExpired:
        return False, "adb command timed out"
    except Exception as e:
        return False, str(e)

def get_devices() -> List[dict]:
    """Return list of connected ADB devices with metadata."""
    ok, out = run_adb("devices", "-l")
    if not ok:
        return []

    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or "offline" in line or "no permissions" in line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue

        serial = parts[0]
        # Extract friendly name from "model:" token if available
        model = ""
        for p in parts[2:]:
            if p.startswith("model:"):
                model = p[6:].replace("_", " ")
                break

        if not model:
            # Try fetching the prop directly
            _, prop = run_adb("-s", serial, "shell", "getprop", "ro.product.model")
            model = prop.strip() or serial

        devices.append({"serial": serial, "model": model})

    return devices

def adb_is_available() -> bool:
    ok, _ = run_adb("version", timeout=3)
    return ok

def scrcpy_is_available() -> bool:
    return shutil.which("scrcpy") is not None

def ffmpeg_is_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffplay") is not None

# ─────────────────────────────────────────────
# Mirroring Engine
# ─────────────────────────────────────────────

class MirrorSession:
    """Manages a single mirroring session (scrcpy or ffplay fallback)."""

    def __init__(self, serial: str, settings: MirrorSettings, on_stop=None):
        self.serial   = serial
        self.settings = settings
        self.on_stop  = on_stop
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._running:
            return

        if scrcpy_is_available():
            cmd = self._build_scrcpy_cmd()
        elif ffmpeg_is_available():
            cmd = self._build_ffplay_cmd()
        else:
            raise RuntimeError(
                "Neither scrcpy nor ffplay is installed.\n"
                "Install scrcpy:  https://github.com/Genymobile/scrcpy\n"
                "Install ffmpeg:  https://ffmpeg.org/download.html"
            )

        self._running = True
        self._thread = threading.Thread(target=self._run, args=(cmd,), daemon=True)
        self._thread.start()

    def _build_scrcpy_cmd(self) -> list:
        s = self.settings
        cmd = [
            "scrcpy",
            "--serial",         self.serial,
            "--max-size",       s.resolution,
            "--video-bit-rate", s.bitrate,
            "--max-fps",        s.fps,
            "--window-title",   s.window_title,
            "--window-x",       s.window_x,
            "--window-y",       s.window_y,
            "--window-width",   s.window_w,
            "--window-height",  s.window_h,
        ]
        if s.stay_on_top:     cmd.append("--always-on-top")
        if s.show_touches:    cmd.append("--show-touches")
        if s.fullscreen:      cmd.append("--fullscreen")
        if s.turn_off_screen: cmd.append("--turn-screen-off")
        if s.no_audio:        cmd.append("--no-audio")
        return cmd

    def _build_ffplay_cmd(self) -> list:
        """Fallback: stream via ADB exec-out screenrecord → ffplay."""
        s = self.settings
        # Two-step pipeline: adb | ffplay (requires shell=True on some OS)
        # We return a special marker and handle in _run
        return ["__ffplay_pipeline__"]

    def _run(self, cmd: list):
        try:
            if cmd == ["__ffplay_pipeline__"]:
                self._run_ffplay_pipeline()
            else:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self._proc.wait()
        except Exception:
            pass
        finally:
            self._running = False
            if self.on_stop:
                self.on_stop()

    def _run_ffplay_pipeline(self):
        """Stream H.264 from screenrecord into ffplay."""
        s = self.settings
        width  = s.window_w
        height = s.window_h

        adb_cmd = [
            "adb", "-s", self.serial,
            "exec-out", "screenrecord",
            "--output-format=h264",
            "--size", f"{s.resolution}x{s.resolution}",
            "--bit-rate", s.bitrate,
            "-"
        ]
        ffplay_cmd = [
            "ffplay",
            "-i", "pipe:0",
            "-vf", "scale=iw:ih",
            "-window_title", s.window_title,
            "-x", width, "-y", height,
            "-left", s.window_x, "-top", s.window_y,
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-framedrop",
            "-an" if s.no_audio else "",
            "-loglevel", "quiet"
        ]
        ffplay_cmd = [c for c in ffplay_cmd if c]  # remove empty strings

        try:
            adb_proc    = subprocess.Popen(adb_cmd, stdout=subprocess.PIPE)
            ffplay_proc = subprocess.Popen(ffplay_cmd, stdin=adb_proc.stdout)
            self._proc  = ffplay_proc
            adb_proc.stdout.close()
            ffplay_proc.wait()
            adb_proc.terminate()
        except Exception:
            pass

    def stop(self):
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None

    @property
    def is_running(self) -> bool:
        return self._running

# ─────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────

DARK_BG    = "#0f1117"
PANEL_BG   = "#1a1d27"
ACCENT     = "#00e5ff"
ACCENT2    = "#7c4dff"
TEXT_PRI   = "#e8eaf6"
TEXT_SEC   = "#7986cb"
SUCCESS    = "#00e676"
WARNING    = "#ffab40"
DANGER     = "#ff5252"
BORDER     = "#2a2d3e"

class AndroidMirrorApp:
    def __init__(self):
        self.settings = load_settings()
        self.session: Optional[MirrorSession] = None
        self.devices: List[dict] = []
        self._scan_timer = None

        self.root = tk.Tk()
        self.root.title("AndroidMirror")
        self.root.geometry("520x720")
        self.root.minsize(480, 640)
        self.root.configure(bg=DARK_BG)
        self.root.resizable(True, True)

        # Try to set a nice icon (skip if unavailable)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        self._build_ui()
        self._check_environment()
        self._start_device_scan()

    # ── UI Construction ─────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()
        self._build_main()
        self._build_footer()

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=PANEL_BG, pady=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.columnconfigure(0, weight=1)

        # Accent bar
        bar = tk.Frame(hdr, bg=ACCENT, height=3)
        bar.grid(row=0, column=0, sticky="ew")

        inner = tk.Frame(hdr, bg=PANEL_BG, padx=24, pady=16)
        inner.grid(row=1, column=0, sticky="ew")
        inner.columnconfigure(1, weight=1)

        # Icon + title
        icon_lbl = tk.Label(inner, text="⬡", font=("Helvetica", 28, "bold"),
                            fg=ACCENT, bg=PANEL_BG)
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(0,14))

        tk.Label(inner, text="AndroidMirror", font=("Helvetica", 18, "bold"),
                 fg=TEXT_PRI, bg=PANEL_BG).grid(row=0, column=1, sticky="w")
        tk.Label(inner, text="USB-C display mirroring for Android → Laptop",
                 font=("Helvetica", 9), fg=TEXT_SEC, bg=PANEL_BG
                 ).grid(row=1, column=1, sticky="w")

        # Status pill
        self.status_var = tk.StringVar(value="● Idle")
        self.status_lbl = tk.Label(inner, textvariable=self.status_var,
                                   font=("Helvetica", 9, "bold"),
                                   fg=TEXT_SEC, bg=PANEL_BG)
        self.status_lbl.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12,0))

    def _build_main(self):
        canvas = tk.Canvas(self.root, bg=DARK_BG, bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")

        self.main_frame = tk.Frame(canvas, bg=DARK_BG)
        self.main_frame.columnconfigure(0, weight=1)
        canvas_win = canvas.create_window((0,0), window=self.main_frame, anchor="nw")

        def on_resize(e):
            canvas.itemconfig(canvas_win, width=e.width)
        def on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", on_resize)
        self.main_frame.bind("<Configure>", on_frame_configure)

        # Mousewheel
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        pad = {"padx": 20, "pady": 8, "sticky": "ew"}

        self._build_env_section(pad)
        self._build_device_section(pad)
        self._build_settings_section(pad)
        self._build_window_section(pad)

    def _section(self, title: str, subtitle: str = "") -> tk.Frame:
        """Create a labelled card section."""
        card = tk.Frame(self.main_frame, bg=PANEL_BG,
                        highlightbackground=BORDER, highlightthickness=1)
        card.columnconfigure(0, weight=1)
        card.grid(padx=20, pady=8, sticky="ew")

        hdr = tk.Frame(card, bg=PANEL_BG, padx=16, pady=12)
        hdr.grid(sticky="ew")
        hdr.columnconfigure(0, weight=1)

        tk.Label(hdr, text=title, font=("Helvetica", 11, "bold"),
                 fg=ACCENT, bg=PANEL_BG).grid(row=0, column=0, sticky="w")
        if subtitle:
            tk.Label(hdr, text=subtitle, font=("Helvetica", 8),
                     fg=TEXT_SEC, bg=PANEL_BG).grid(row=1, column=0, sticky="w")

        sep = tk.Frame(card, bg=BORDER, height=1)
        sep.grid(sticky="ew", padx=0)

        body = tk.Frame(card, bg=PANEL_BG, padx=16, pady=12)
        body.grid(sticky="ew")
        body.columnconfigure(1, weight=1)

        return body

    def _build_env_section(self, pad):
        body = self._section("System Requirements",
                             "Tools must be installed and in PATH")
        body.columnconfigure(1, weight=1)

        self.env_rows = {}
        tools = [
            ("adb",    "ADB (Android Debug Bridge)", "Required"),
            ("scrcpy", "scrcpy (recommended)",        "Recommended"),
            ("ffmpeg", "ffmpeg + ffplay (fallback)",  "Optional"),
        ]
        for i, (key, label, badge) in enumerate(tools):
            tk.Label(body, text=label, font=("Helvetica", 9),
                     fg=TEXT_PRI, bg=PANEL_BG).grid(row=i, column=0, sticky="w", pady=3)
            status_lbl = tk.Label(body, text="Checking…",
                                  font=("Helvetica", 9, "bold"),
                                  fg=TEXT_SEC, bg=PANEL_BG)
            status_lbl.grid(row=i, column=1, sticky="e")
            self.env_rows[key] = status_lbl

    def _build_device_section(self, pad):
        body = self._section("Connected Devices",
                             "USB-C cable · USB Debugging must be enabled")
        body.columnconfigure(0, weight=1)

        # Device list
        list_frame = tk.Frame(body, bg=DARK_BG,
                              highlightbackground=BORDER, highlightthickness=1)
        list_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,8))
        list_frame.columnconfigure(0, weight=1)

        self.device_listbox = tk.Listbox(
            list_frame,
            font=("Courier", 10),
            bg=DARK_BG, fg=TEXT_PRI,
            selectbackground=ACCENT2,
            selectforeground=TEXT_PRI,
            activestyle="none",
            height=4,
            bd=0, highlightthickness=0,
        )
        self.device_listbox.grid(sticky="ew", padx=8, pady=8)

        btn_frame = tk.Frame(body, bg=PANEL_BG)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)

        self._btn(btn_frame, "⟳  Refresh Devices", self._refresh_devices,
                  col=0, fg=ACCENT).grid(row=0, column=0, sticky="ew", padx=(0,4))

        self.adb_tip = tk.Label(body,
            text="💡 Tip: Run 'adb devices' in terminal if device not showing",
            font=("Helvetica", 8), fg=TEXT_SEC, bg=PANEL_BG, wraplength=420,
            justify="left")
        self.adb_tip.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8,0))

    def _build_settings_section(self, pad):
        body = self._section("Mirror Settings",
                             "Video quality and behaviour options")
        body.columnconfigure(1, weight=1)

        # Resolution
        self._label(body, "Max Resolution (height px):", 0)
        self.res_var = tk.StringVar(value=self.settings.resolution)
        res_cb = ttk.Combobox(body, textvariable=self.res_var,
                              values=["480","720","1080","1440","2160"],
                              state="readonly", width=14)
        res_cb.grid(row=0, column=1, sticky="e", pady=3)

        # Bitrate
        self._label(body, "Video Bitrate:", 1)
        self.bit_var = tk.StringVar(value=self.settings.bitrate)
        bit_cb = ttk.Combobox(body, textvariable=self.bit_var,
                              values=["2M","4M","8M","12M","16M","24M"],
                              state="readonly", width=14)
        bit_cb.grid(row=1, column=1, sticky="e", pady=3)

        # FPS
        self._label(body, "Max FPS:", 2)
        self.fps_var = tk.StringVar(value=self.settings.fps)
        fps_cb = ttk.Combobox(body, textvariable=self.fps_var,
                              values=["24","30","60","120"],
                              state="readonly", width=14)
        fps_cb.grid(row=2, column=1, sticky="e", pady=3)

        # Toggles
        self.stay_top_var    = tk.BooleanVar(value=self.settings.stay_on_top)
        self.show_touch_var  = tk.BooleanVar(value=self.settings.show_touches)
        self.screen_off_var  = tk.BooleanVar(value=self.settings.turn_off_screen)
        self.no_audio_var    = tk.BooleanVar(value=self.settings.no_audio)

        toggles = [
            ("Always on top (window)",            self.stay_top_var,   3),
            ("Show touch indicators on screen",   self.show_touch_var, 4),
            ("Turn off Android screen while mirroring", self.screen_off_var, 5),
            ("No audio (video only)",             self.no_audio_var,   6),
        ]
        for text, var, row in toggles:
            self._toggle(body, text, var, row)

    def _build_window_section(self, pad):
        body = self._section("Mirror Window Position & Size",
                             "Windowed mode — pixel coordinates from top-left of screen")
        body.columnconfigure(1, weight=1)
        body.columnconfigure(3, weight=1)

        coords = [
            ("Window X (px):", "win_x_var", self.settings.window_x, 0, 0),
            ("Window Y (px):", "win_y_var", self.settings.window_y, 1, 0),
            ("Width  (px):",   "win_w_var", self.settings.window_w,  0, 2),
            ("Height (px):",   "win_h_var", self.settings.window_h,  1, 2),
        ]
        for label, attr, val, row, col_offset in coords:
            tk.Label(body, text=label, font=("Helvetica", 9),
                     fg=TEXT_PRI, bg=PANEL_BG
                     ).grid(row=row, column=col_offset, sticky="w", pady=3, padx=(0,8))
            var = tk.StringVar(value=val)
            setattr(self, attr, var)
            tk.Entry(body, textvariable=var, width=7,
                     bg=DARK_BG, fg=TEXT_PRI,
                     insertbackground=ACCENT,
                     relief="flat",
                     font=("Courier", 10),
                     highlightbackground=BORDER,
                     highlightthickness=1
                     ).grid(row=row, column=col_offset+1, sticky="ew", pady=3)

        # Preset positions
        presets_frame = tk.Frame(body, bg=PANEL_BG)
        presets_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(10,0))

        tk.Label(presets_frame, text="Quick Presets:", font=("Helvetica", 9),
                 fg=TEXT_SEC, bg=PANEL_BG).pack(side="left", padx=(0,8))

        presets = [
            ("↖ Top-Left",   "50",  "50",  "400", "720"),
            ("↗ Top-Right", "auto", "50",  "400", "720"),
            ("↙ Centered",  "auto","auto", "400", "720"),
        ]
        for name, x, y, w, h in presets:
            self._small_btn(presets_frame, name,
                            lambda _x=x,_y=y,_w=w,_h=h: self._apply_preset(_x,_y,_w,_h))

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=PANEL_BG, padx=20, pady=14)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(1, weight=1)

        sep = tk.Frame(footer, bg=ACCENT, height=1)
        sep.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,14))

        self.start_btn = self._big_btn(
            footer, "▶  Start Mirroring", self._start_mirror,
            bg=ACCENT, fg=DARK_BG, col=0
        )
        self.stop_btn = self._big_btn(
            footer, "■  Stop", self._stop_mirror,
            bg=DANGER, fg=TEXT_PRI, col=1
        )
        self.stop_btn.configure(state="disabled")

    # ── Widget Helpers ───────────────────────────

    def _label(self, parent, text, row):
        tk.Label(parent, text=text, font=("Helvetica", 9),
                 fg=TEXT_PRI, bg=PANEL_BG).grid(row=row, column=0, sticky="w", pady=3)

    def _toggle(self, parent, text, var, row):
        f = tk.Frame(parent, bg=PANEL_BG)
        f.grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        cb = tk.Checkbutton(f, text=text, variable=var,
                            font=("Helvetica", 9),
                            fg=TEXT_PRI, bg=PANEL_BG,
                            selectcolor=DARK_BG,
                            activebackground=PANEL_BG,
                            activeforeground=ACCENT,
                            cursor="hand2")
        cb.pack(side="left")

    def _btn(self, parent, text, cmd, col=0, row=0, fg=TEXT_PRI, bg=DARK_BG):
        b = tk.Button(parent, text=text, command=cmd,
                      font=("Helvetica", 9, "bold"),
                      fg=fg, bg=bg,
                      relief="flat", bd=0,
                      activebackground=BORDER,
                      activeforeground=ACCENT,
                      cursor="hand2",
                      padx=12, pady=6)
        b.grid(row=row, column=col, sticky="ew")
        return b

    def _big_btn(self, parent, text, cmd, bg=ACCENT, fg=DARK_BG, col=0):
        b = tk.Button(parent, text=text, command=cmd,
                      font=("Helvetica", 11, "bold"),
                      fg=fg, bg=bg,
                      relief="flat", bd=0,
                      activebackground=ACCENT2,
                      activeforeground=TEXT_PRI,
                      cursor="hand2",
                      padx=0, pady=10)
        b.grid(row=1, column=col, sticky="ew", padx=(0,6) if col==0 else (6,0))
        return b

    def _small_btn(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd,
                      font=("Helvetica", 8),
                      fg=TEXT_SEC, bg=DARK_BG,
                      relief="flat", bd=0,
                      activebackground=BORDER,
                      activeforeground=ACCENT,
                      cursor="hand2",
                      padx=8, pady=4)
        b.pack(side="left", padx=2)
        return b

    # ── Logic ────────────────────────────────────

    def _check_environment(self):
        def check():
            adb_ok    = adb_is_available()
            scrcpy_ok = scrcpy_is_available()
            ffmpeg_ok = ffmpeg_is_available()

            self.root.after(0, self._update_env_row, "adb",
                            adb_ok, "✔ Found" if adb_ok else "✘ Not found (install ADB)")
            self.root.after(0, self._update_env_row, "scrcpy",
                            scrcpy_ok, "✔ Found" if scrcpy_ok else "✘ Not found")
            self.root.after(0, self._update_env_row, "ffmpeg",
                            ffmpeg_ok or scrcpy_ok,
                            "✔ Found" if ffmpeg_ok else ("(Using scrcpy)" if scrcpy_ok else "✘ Not found"))
        threading.Thread(target=check, daemon=True).start()

    def _update_env_row(self, key, ok, text):
        lbl = self.env_rows.get(key)
        if lbl:
            lbl.configure(text=text, fg=SUCCESS if ok else WARNING)

    def _start_device_scan(self):
        self._refresh_devices()
        self._scan_timer = self.root.after(5000, self._start_device_scan)

    def _refresh_devices(self):
        def fetch():
            devs = get_devices()
            self.root.after(0, self._populate_devices, devs)
        threading.Thread(target=fetch, daemon=True).start()

    def _populate_devices(self, devices: List[dict]):
        self.devices = devices
        self.device_listbox.delete(0, tk.END)
        if not devices:
            self.device_listbox.insert(tk.END, "  No devices found — check USB & USB Debugging")
            self.device_listbox.itemconfig(0, fg=WARNING)
        else:
            for d in devices:
                self.device_listbox.insert(tk.END, f"  {d['model']}  [{d['serial']}]")
            self.device_listbox.selection_set(0)

    def _get_selected_device(self) -> Optional[dict]:
        sel = self.device_listbox.curselection()
        if not sel or not self.devices:
            return None
        idx = sel[0]
        if idx >= len(self.devices):
            return None
        return self.devices[idx]

    def _apply_preset(self, x, y, w, h):
        if x != "auto": self.win_x_var.set(x)
        if y != "auto": self.win_y_var.set(y)
        self.win_w_var.set(w)
        self.win_h_var.set(h)

    def _collect_settings(self) -> MirrorSettings:
        s = self.settings
        s.resolution      = self.res_var.get()
        s.bitrate         = self.bit_var.get()
        s.fps             = self.fps_var.get()
        s.stay_on_top     = self.stay_top_var.get()
        s.show_touches    = self.show_touch_var.get()
        s.turn_off_screen = self.screen_off_var.get()
        s.no_audio        = self.no_audio_var.get()
        s.window_x        = self.win_x_var.get() or "50"
        s.window_y        = self.win_y_var.get() or "50"
        s.window_w        = self.win_w_var.get() or "400"
        s.window_h        = self.win_h_var.get() or "720"
        return s

    def _start_mirror(self):
        device = self._get_selected_device()
        if not device:
            messagebox.showwarning("No Device",
                "Please connect an Android device via USB-C and enable USB Debugging.")
            return

        if not adb_is_available():
            messagebox.showerror("ADB Missing",
                "ADB is not installed or not in PATH.\n\n"
                "Install Android Platform Tools:\n"
                "https://developer.android.com/tools/releases/platform-tools")
            return

        if not scrcpy_is_available() and not ffmpeg_is_available():
            messagebox.showerror("Missing Tools",
                "Neither scrcpy nor ffplay is installed.\n\n"
                "Install scrcpy (recommended):\n"
                "https://github.com/Genymobile/scrcpy\n\n"
                "Or install ffmpeg:\n"
                "https://ffmpeg.org/download.html")
            return

        settings = self._collect_settings()
        save_settings(settings)

        self.session = MirrorSession(
            serial=device["serial"],
            settings=settings,
            on_stop=self._on_session_stop
        )

        try:
            self.session.start()
        except RuntimeError as e:
            messagebox.showerror("Cannot Start", str(e))
            return

        self._set_mirroring_state(True, device["model"])

    def _stop_mirror(self):
        if self.session:
            self.session.stop()
            self.session = None
        self._set_mirroring_state(False)

    def _on_session_stop(self):
        self.root.after(0, self._set_mirroring_state, False)

    def _set_mirroring_state(self, active: bool, model: str = ""):
        if active:
            self.status_var.set(f"● Mirroring  {model}")
            self.status_lbl.configure(fg=SUCCESS)
            self.start_btn.configure(state="disabled", bg="#555")
            self.stop_btn.configure(state="normal", bg=DANGER)
        else:
            self.status_var.set("● Idle")
            self.status_lbl.configure(fg=TEXT_SEC)
            self.start_btn.configure(state="normal", bg=ACCENT)
            self.stop_btn.configure(state="disabled", bg="#555")

    def _on_close(self):
        if self._scan_timer:
            self.root.after_cancel(self._scan_timer)
        self._stop_mirror()
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        # Apply ttk dark styling
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=DARK_BG, 
                        background=PANEL_BG,
                        foreground=TEXT_PRI, 
                        arrowcolor=ACCENT,
                        selectbackground=ACCENT2, 
                        selectforeground=TEXT_PRI,
                        listbackground="#1a1d27",   # popup list background
                        listforeground="#e8eaf6",   # popup list text color
                        )
        
        # Also map hover state on the dropdown items
        style.map("TCombobox",
            fieldbackground=[("readonly", DARK_BG)],
            foreground=[("readonly", TEXT_PRI)],
            background=[("active", ACCENT2)]   # arrow button hover color
        )

        style.configure("TScrollbar", 
                        background=PANEL_BG,
                        troughcolor=DARK_BG, 
                        arrowcolor=TEXT_SEC)
        self.root.mainloop()


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = AndroidMirrorApp()
    app.run()
