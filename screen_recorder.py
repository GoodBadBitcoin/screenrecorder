#!/usr/bin/env python3
"""
ScreenRecorder - Custom Region Screen Recording Tool for Windows
Records screen with pixel-exact area selection, drag overlay, audio capture, and GUI.
Requires: ffmpeg installed and in PATH
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mss
import numpy as np
from PIL import Image, ImageEnhance, ImageTk
import sounddevice as sd
import soundfile as sf
import subprocess
import threading
import time
import os
import tempfile
from datetime import datetime
from pathlib import Path
import ctypes
import json

# ── Translations ──
TRANSLATIONS = {
    "de": {
        "window_title": "Screen Recorder",
        "app_title": "⏺  Screen Recorder",
        "region_frame": "  Aufnahmebereich",
        "x_label": "X:",
        "y_label": "Y:",
        "width_label": "Breite:",
        "height_label": "Höhe:",
        "select_region": "🖱  Bereich auswählen",
        "show_region": "👁  Bereich anzeigen",
        "hide_region": "👁  Bereich ausblenden",
        "presets_label": "Presets:",
        "audio_frame": "  Audio",
        "mic_checkbox": "Mikrofon aufnehmen",
        "device_label": "Gerät:",
        "output_frame": "  Ausgabe",
        "fps_label": "FPS:",
        "format_label": "Format:",
        "folder_label": "Ordner:",
        "start_recording": "⏺  Aufnahme starten",
        "stop_recording": "⏹  Aufnahme stoppen",
        "status_ready": "Bereit",
        "status_overlay_active": "Overlay aktiv — verschieben / resizen per Drag",
        "status_recording": "⏺  Aufnahme läuft …",
        "status_processing": "⏳  Verarbeite …",
        "status_saved": "✅  Gespeichert: {name}  ({time})",
        "status_region": "Bereich: {w}×{h} bei ({x}, {y})",
        "overlay_instructions": "Bereich aufziehen  ·  ESC = Abbrechen",
        "error_ffmpeg_title": "ffmpeg nicht gefunden",
        "error_ffmpeg_msg": "Bitte installiere ffmpeg und stelle sicher, dass es im PATH liegt.\nDownload: https://ffmpeg.org/download.html",
        "error_size_title": "Ungültige Größe",
        "error_size_msg": "Breite und Höhe müssen >= 16 px sein.",
        "lang_label": "Sprache:",
    },
    "en": {
        "window_title": "Screen Recorder",
        "app_title": "⏺  Screen Recorder",
        "region_frame": "  Recording Area",
        "x_label": "X:",
        "y_label": "Y:",
        "width_label": "Width:",
        "height_label": "Height:",
        "select_region": "🖱  Select Region",
        "show_region": "👁  Show Region",
        "hide_region": "👁  Hide Region",
        "presets_label": "Presets:",
        "audio_frame": "  Audio",
        "mic_checkbox": "Record Microphone",
        "device_label": "Device:",
        "output_frame": "  Output",
        "fps_label": "FPS:",
        "format_label": "Format:",
        "folder_label": "Folder:",
        "start_recording": "⏺  Start Recording",
        "stop_recording": "⏹  Stop Recording",
        "status_ready": "Ready",
        "status_overlay_active": "Overlay active — drag to move / resize",
        "status_recording": "⏺  Recording …",
        "status_processing": "⏳  Processing …",
        "status_saved": "✅  Saved: {name}  ({time})",
        "status_region": "Region: {w}×{h} at ({x}, {y})",
        "overlay_instructions": "Draw area  ·  ESC = Cancel",
        "error_ffmpeg_title": "ffmpeg not found",
        "error_ffmpeg_msg": "Please install ffmpeg and make sure it is in your PATH.\nDownload: https://ffmpeg.org/download.html",
        "error_size_title": "Invalid Size",
        "error_size_msg": "Width and height must be >= 16 px.",
        "lang_label": "Language:",
    },
}

LANG_CONFIG_PATH = Path.home() / ".screenrecorder_lang.json"


def load_language():
    try:
        return json.loads(LANG_CONFIG_PATH.read_text())["lang"]
    except Exception:
        return "de"


def save_language(lang):
    LANG_CONFIG_PATH.write_text(json.dumps({"lang": lang}))

# ── Windows DPI awareness for accurate coordinates ──
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ─────────────────────────────────────────────
#  Utility Functions
# ─────────────────────────────────────────────

def check_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def get_audio_devices():
    devices = sd.query_devices()
    result = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            name = d["name"]
            ch = d["max_input_channels"]
            result.append((i, f"{name} ({ch}ch)", min(ch, 2)))
    return result


def make_even(n):
    return n if n % 2 == 0 else n - 1


def mux_audio_video(video_path, audio_path, output_path):
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Region Overlay (Live Preview Frame)
# ─────────────────────────────────────────────

class RegionOverlay(tk.Toplevel):
    """
    Transparent window showing the recording area as a colored border.
    Draggable to reposition, with resize grips at corners and edges.
    Reports position/size changes back to the main app.
    """

    BORDER = 3
    GRIP_SIZE = 14
    COLOR_BORDER = "#00ff88"
    COLOR_GRIP = "#00cc66"
    COLOR_INFO_BG = "#1e1e2e"
    COLOR_INFO_FG = "#00ff88"
    TRANSPARENT_COLOR = "#010101"

    def __init__(self, parent, x, y, w, h, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self._region_x = x
        self._region_y = y
        self._region_w = w
        self._region_h = h

        self._drag_mode = None
        self._drag_start_mx = 0
        self._drag_start_my = 0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_start_w = 0
        self._drag_start_h = 0

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-transparentcolor", self.TRANSPARENT_COLOR)
        self.configure(bg=self.TRANSPARENT_COLOR)

        self.canvas = tk.Canvas(
            self, highlightthickness=0,
            bg=self.TRANSPARENT_COLOR, cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        self._apply_geometry()
        self._draw()

    def _apply_geometry(self):
        pad = self.BORDER + self.GRIP_SIZE
        info_bar = 28
        win_x = self._region_x - pad
        win_y = self._region_y - pad - info_bar
        win_w = self._region_w + pad * 2
        win_h = self._region_h + pad * 2 + info_bar * 2
        self.geometry(f"{win_w}x{win_h}+{win_x}+{win_y}")

    def _draw(self):
        c = self.canvas
        c.delete("all")
        pad = self.BORDER + self.GRIP_SIZE
        info_bar = 28
        x0, y0 = pad, pad + info_bar
        x1 = x0 + self._region_w
        y1 = y0 + self._region_h
        b = self.BORDER

        # Outer border
        c.create_rectangle(
            x0 - b, y0 - b, x1 + b, y1 + b,
            outline=self.COLOR_BORDER, width=b,
        )

        # Corner grips
        g = self.GRIP_SIZE
        corners = [
            (x0 - b - g, y0 - b - g, x0 - b, y0 - b),
            (x1 + b, y0 - b - g, x1 + b + g, y0 - b),
            (x0 - b - g, y1 + b, x0 - b, y1 + b + g),
            (x1 + b, y1 + b, x1 + b + g, y1 + b + g),
        ]
        for cx0, cy0, cx1, cy1 in corners:
            c.create_rectangle(cx0, cy0, cx1, cy1,
                               fill=self.COLOR_GRIP, outline="")

        # Edge grips (midpoints)
        mid_w = 30
        mid_h = 8
        edges = [
            ((x0 + x1) // 2 - mid_w // 2, y0 - b - mid_h,
             (x0 + x1) // 2 + mid_w // 2, y0 - b),
            ((x0 + x1) // 2 - mid_w // 2, y1 + b,
             (x0 + x1) // 2 + mid_w // 2, y1 + b + mid_h),
            (x0 - b - mid_h, (y0 + y1) // 2 - mid_w // 2,
             x0 - b, (y0 + y1) // 2 + mid_w // 2),
            (x1 + b, (y0 + y1) // 2 - mid_w // 2,
             x1 + b + mid_h, (y0 + y1) // 2 + mid_w // 2),
        ]
        for ex0, ey0, ex1, ey1 in edges:
            c.create_rectangle(ex0, ey0, ex1, ey1,
                               fill=self.COLOR_GRIP, outline="")

        # Size label (top-center)
        label_x = (x0 + x1) // 2
        label_y = y0 - b - g - 14
        label = f"{self._region_w} × {self._region_h}"
        c.create_rectangle(
            label_x - 74, label_y - 12,
            label_x + 74, label_y + 12,
            fill=self.COLOR_INFO_BG, outline=self.COLOR_BORDER, width=1,
        )
        c.create_text(label_x, label_y, text=label,
                       fill=self.COLOR_INFO_FG, font=("Consolas", 11, "bold"))

        # Position label (bottom-center)
        pos_y = y1 + b + g + 14
        pos_label = f"X:{self._region_x}  Y:{self._region_y}"
        c.create_rectangle(
            label_x - 74, pos_y - 12,
            label_x + 74, pos_y + 12,
            fill=self.COLOR_INFO_BG, outline=self.COLOR_BORDER, width=1,
        )
        c.create_text(label_x, pos_y, text=pos_label,
                       fill=self.COLOR_INFO_FG, font=("Consolas", 10))

    def update_region(self, x, y, w, h):
        self._region_x = x
        self._region_y = y
        self._region_w = make_even(max(w, 32))
        self._region_h = make_even(max(h, 32))
        self._apply_geometry()
        self._draw()

    def _fire_change(self):
        if self.on_change:
            self.on_change(
                self._region_x, self._region_y,
                self._region_w, self._region_h,
            )

    def _hit_test(self, mx, my):
        pad = self.BORDER + self.GRIP_SIZE
        info_bar = 28
        x0, y0 = pad, pad + info_bar
        x1 = x0 + self._region_w
        y1 = y0 + self._region_h

        if mx < x0 and my < y0:
            return "resize_tl"
        if mx > x1 and my < y0:
            return "resize_tr"
        if mx < x0 and my > y1:
            return "resize_bl"
        if mx > x1 and my > y1:
            return "resize_br"
        if mx < x0:
            return "resize_l"
        if mx > x1:
            return "resize_r"
        if my < y0:
            return "resize_t"
        if my > y1:
            return "resize_b"
        return "move"

    def _on_hover(self, event):
        zone = self._hit_test(event.x, event.y)
        cursors = {
            "move": "fleur",
            "resize_tl": "top_left_corner",
            "resize_tr": "top_right_corner",
            "resize_bl": "bottom_left_corner",
            "resize_br": "bottom_right_corner",
            "resize_l": "sb_h_double_arrow",
            "resize_r": "sb_h_double_arrow",
            "resize_t": "sb_v_double_arrow",
            "resize_b": "sb_v_double_arrow",
        }
        self.canvas.configure(cursor=cursors.get(zone, "fleur"))

    def _on_press(self, event):
        self._drag_mode = self._hit_test(event.x, event.y)
        self._drag_start_mx = event.x_root
        self._drag_start_my = event.y_root
        self._drag_start_x = self._region_x
        self._drag_start_y = self._region_y
        self._drag_start_w = self._region_w
        self._drag_start_h = self._region_h

    def _on_motion(self, event):
        dx = event.x_root - self._drag_start_mx
        dy = event.y_root - self._drag_start_my
        mode = self._drag_mode

        if mode == "move":
            self._region_x = self._drag_start_x + dx
            self._region_y = self._drag_start_y + dy

        elif mode == "resize_br":
            self._region_w = make_even(max(32, self._drag_start_w + dx))
            self._region_h = make_even(max(32, self._drag_start_h + dy))

        elif mode == "resize_bl":
            new_w = make_even(max(32, self._drag_start_w - dx))
            self._region_x = self._drag_start_x + (self._drag_start_w - new_w)
            self._region_w = new_w
            self._region_h = make_even(max(32, self._drag_start_h + dy))

        elif mode == "resize_tr":
            self._region_w = make_even(max(32, self._drag_start_w + dx))
            new_h = make_even(max(32, self._drag_start_h - dy))
            self._region_y = self._drag_start_y + (self._drag_start_h - new_h)
            self._region_h = new_h

        elif mode == "resize_tl":
            new_w = make_even(max(32, self._drag_start_w - dx))
            new_h = make_even(max(32, self._drag_start_h - dy))
            self._region_x = self._drag_start_x + (self._drag_start_w - new_w)
            self._region_y = self._drag_start_y + (self._drag_start_h - new_h)
            self._region_w = new_w
            self._region_h = new_h

        elif mode == "resize_r":
            self._region_w = make_even(max(32, self._drag_start_w + dx))
        elif mode == "resize_l":
            new_w = make_even(max(32, self._drag_start_w - dx))
            self._region_x = self._drag_start_x + (self._drag_start_w - new_w)
            self._region_w = new_w
        elif mode == "resize_b":
            self._region_h = make_even(max(32, self._drag_start_h + dy))
        elif mode == "resize_t":
            new_h = make_even(max(32, self._drag_start_h - dy))
            self._region_y = self._drag_start_y + (self._drag_start_h - new_h)
            self._region_h = new_h

        self._apply_geometry()
        self._draw()
        self._fire_change()

    def _on_release(self, event):
        self._drag_mode = None


# ─────────────────────────────────────────────
#  Region Selector (Drag on Darkened Screenshot)
# ─────────────────────────────────────────────

class RegionSelector(tk.Toplevel):
    def __init__(self, parent, callback, overlay_text="Bereich aufziehen  ·  ESC = Abbrechen"):
        super().__init__(parent)
        self.callback = callback
        self._overlay_text = overlay_text
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.text_id = None

        with mss.mss() as sct:
            mon = sct.monitors[0]
            raw = sct.grab(mon)
            screenshot = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        self.offset_x = mon["left"]
        self.offset_y = mon["top"]

        darkened = ImageEnhance.Brightness(screenshot).enhance(0.35)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(
            f"{screenshot.width}x{screenshot.height}"
            f"+{mon['left']}+{mon['top']}"
        )

        self.canvas = tk.Canvas(
            self, cursor="crosshair", highlightthickness=0,
            width=screenshot.width, height=screenshot.height,
        )
        self.canvas.pack(fill="both", expand=True)

        self.bg_photo = ImageTk.PhotoImage(darkened)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        self.canvas.create_text(
            screenshot.width // 2, 36,
            text=self._overlay_text,
            fill="white", font=("Segoe UI", 14, "bold"),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda e: self.destroy())
        self.focus_force()

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.text_id:
            self.canvas.delete(self.text_id)

        x0, y0 = self.start_x, self.start_y
        x1, y1 = event.x, event.y

        self.rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#00ff88", width=2, dash=(6, 3),
        )

        w, h = abs(x1 - x0), abs(y1 - y0)
        label_y = min(y0, y1) - 18
        if label_y < 10:
            label_y = max(y0, y1) + 18

        self.text_id = self.canvas.create_text(
            (x0 + x1) // 2, label_y,
            text=f"{w} × {h} px",
            fill="#00ff88", font=("Consolas", 13, "bold"),
        )

    def _on_release(self, event):
        x0 = min(self.start_x, event.x)
        y0 = min(self.start_y, event.y)
        x1 = max(self.start_x, event.x)
        y1 = max(self.start_y, event.y)
        w = x1 - x0
        h = y1 - y0

        if w > 10 and h > 10:
            abs_x = x0 + self.offset_x
            abs_y = y0 + self.offset_y
            self.callback(abs_x, abs_y, make_even(w), make_even(h))

        self.destroy()


# ─────────────────────────────────────────────
#  Audio Recorder
# ─────────────────────────────────────────────

class AudioRecorder:
    def __init__(self, output_path, device_index, samplerate=44100, channels=2):
        self.output_path = output_path
        self.device_index = device_index
        self.samplerate = samplerate
        self.channels = channels
        self.recording = False
        self._frames = []
        self._thread = None

    def start(self):
        self.recording = True
        self._frames = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        def _cb(indata, frames, time_info, status):
            if self.recording:
                self._frames.append(indata.copy())
        try:
            with sd.InputStream(
                device=self.device_index, samplerate=self.samplerate,
                channels=self.channels, callback=_cb, blocksize=1024,
            ):
                while self.recording:
                    time.sleep(0.05)
        except Exception as e:
            print(f"[AudioRecorder] Error: {e}")

    def stop(self):
        self.recording = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._frames:
            data = np.concatenate(self._frames, axis=0)
            sf.write(self.output_path, data, self.samplerate)
            return True
        return False


# ─────────────────────────────────────────────
#  Video Recorder (mss → ffmpeg pipe)
# ─────────────────────────────────────────────

class VideoRecorder:
    def __init__(self, output_path, x, y, width, height, fps=30):
        self.output_path = output_path
        self.region = {"left": x, "top": y, "width": width, "height": height}
        self.fps = fps
        self.recording = False
        self.frame_count = 0
        self.start_time = 0
        self._thread = None
        self._proc = None

    def start(self):
        self.recording = True
        self.frame_count = 0
        self.start_time = time.time()

        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgra",
            "-s", f"{self.region['width']}x{self.region['height']}",
            "-r", str(self.fps),
            "-i", "pipe:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            self.output_path,
        ]

        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        interval = 1.0 / self.fps
        next_frame = time.perf_counter()

        with mss.mss() as sct:
            while self.recording:
                next_frame += interval
                try:
                    img = sct.grab(self.region)
                    self._proc.stdin.write(bytes(img.raw))
                    self.frame_count += 1
                except Exception:
                    break
                sleep = next_frame - time.perf_counter()
                if sleep > 0:
                    time.sleep(sleep)
                else:
                    next_frame = time.perf_counter()

    def stop(self):
        self.recording = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._proc and self._proc.stdin:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=15)
            except Exception:
                self._proc.kill()
        return time.time() - self.start_time

    @property
    def elapsed(self):
        return time.time() - self.start_time if self.start_time else 0.0


# ─────────────────────────────────────────────
#  Main Application GUI
# ─────────────────────────────────────────────

class RecorderApp(tk.Tk):

    BG = "#1e1e2e"
    FG = "#cdd6f4"
    ACCENT = "#00ff88"
    CARD = "#2a2a3d"
    ENTRY_BG = "#363650"
    BTN_REC = "#e03e3e"
    BTN_STOP = "#f5a623"

    def __init__(self):
        super().__init__()
        self._lang = load_language()
        self.t = TRANSLATIONS[self._lang]

        self.title(self.t["window_title"])
        self.configure(bg=self.BG)
        self.geometry("440x720")
        self.resizable(False, False)

        self.recording = False
        self.video_rec = None
        self.audio_rec = None
        self._timer_id = None
        self._tmp_dir = tempfile.mkdtemp(prefix="screenrec_")
        self._overlay = None
        self._suppress_field_update = False

        self.var_x = tk.IntVar(value=0)
        self.var_y = tk.IntVar(value=0)
        self.var_w = tk.IntVar(value=1920)
        self.var_h = tk.IntVar(value=1080)
        self.var_fps = tk.IntVar(value=30)
        self.var_mic = tk.BooleanVar(value=False)
        self.var_mic_device = tk.StringVar()
        self.var_outdir = tk.StringVar(value=str(Path.home() / "Videos"))
        self.var_format = tk.StringVar(value="mp4")
        self.var_status = tk.StringVar(value=self.t["status_ready"])
        self.var_lang = tk.StringVar(value=self._lang)

        for var in (self.var_x, self.var_y, self.var_w, self.var_h):
            var.trace_add("write", self._on_field_changed)

        self._audio_devices = get_audio_devices()
        self._device_names = [d[1] for d in self._audio_devices]

        self._build_ui()

        if not check_ffmpeg():
            messagebox.showerror(
                self.t["error_ffmpeg_title"],
                self.t["error_ffmpeg_msg"],
            )

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Card.TLabelframe", background=self.CARD, foreground=self.FG)
        style.configure("Card.TLabelframe.Label", background=self.CARD,
                        foreground=self.ACCENT, font=("Segoe UI", 10, "bold"))

        pad = {"padx": 12, "pady": (8, 4)}

        # ── Language Selector ──
        lang_frame = tk.Frame(self, bg=self.BG)
        lang_frame.pack(fill="x", padx=12, pady=(8, 0))

        tk.Label(lang_frame, text=self.t["lang_label"], bg=self.BG, fg="#888",
                 font=("Segoe UI", 8)).pack(side="left")
        lang_combo = ttk.Combobox(
            lang_frame, textvariable=self.var_lang,
            values=["de", "en"], state="readonly", width=4,
        )
        lang_combo.pack(side="left", padx=(4, 0))
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        # ── Title ──
        tk.Label(
            self, text=self.t["app_title"], font=("Segoe UI", 16, "bold"),
            bg=self.BG, fg=self.ACCENT,
        ).pack(pady=(6, 6))

        # ── Region Frame ──
        region_frame = ttk.LabelFrame(self, text=self.t["region_frame"],
                                       style="Card.TLabelframe")
        region_frame.pack(fill="x", **pad)

        inner_r = tk.Frame(region_frame, bg=self.CARD)
        inner_r.pack(fill="x", padx=8, pady=8)

        fields = [
            (self.t["x_label"], self.var_x), (self.t["y_label"], self.var_y),
            (self.t["width_label"], self.var_w), (self.t["height_label"], self.var_h),
        ]
        for i, (label, var) in enumerate(fields):
            row, col = divmod(i, 2)
            tk.Label(inner_r, text=label, bg=self.CARD, fg=self.FG,
                     font=("Segoe UI", 9)).grid(
                row=row, column=col * 2, sticky="e", padx=(4, 2))
            tk.Entry(inner_r, textvariable=var, width=8, bg=self.ENTRY_BG,
                     fg=self.FG, insertbackground=self.FG, font=("Consolas", 10),
                     relief="flat", bd=4).grid(
                row=row, column=col * 2 + 1, sticky="w", padx=(0, 10), pady=2)

        # Buttons row
        btn_row = tk.Frame(inner_r, bg=self.CARD)
        btn_row.grid(row=2, column=0, columnspan=4, pady=(8, 4))

        tk.Button(
            btn_row, text=self.t["select_region"], command=self._select_region,
            bg=self.ACCENT, fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", padx=10, pady=4,
        ).pack(side="left", padx=(0, 8))

        self.btn_overlay = tk.Button(
            btn_row, text=self.t["show_region"], command=self._toggle_overlay,
            bg="#5865f2", fg="white", font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2", padx=10, pady=4,
        )
        self.btn_overlay.pack(side="left")

        # Presets row
        preset_row = tk.Frame(inner_r, bg=self.CARD)
        preset_row.grid(row=3, column=0, columnspan=4, pady=(4, 2))

        tk.Label(preset_row, text=self.t["presets_label"], bg=self.CARD, fg="#888",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 6))

        for name, pw, ph in [("1920×1080", 1920, 1080), ("1280×720", 1280, 720),
                              ("854×480", 854, 480), ("1080×1920", 1080, 1920)]:
            tk.Button(
                preset_row, text=name,
                command=lambda w=pw, h=ph: self._apply_preset(w, h),
                bg=self.ENTRY_BG, fg=self.FG, font=("Segoe UI", 8),
                relief="flat", cursor="hand2", padx=6, pady=1,
            ).pack(side="left", padx=2)

        # ── Audio Frame ──
        audio_frame = ttk.LabelFrame(self, text=self.t["audio_frame"], style="Card.TLabelframe")
        audio_frame.pack(fill="x", **pad)

        inner_a = tk.Frame(audio_frame, bg=self.CARD)
        inner_a.pack(fill="x", padx=8, pady=8)

        tk.Checkbutton(
            inner_a, text=self.t["mic_checkbox"], variable=self.var_mic,
            bg=self.CARD, fg=self.FG, selectcolor=self.ENTRY_BG,
            activebackground=self.CARD, activeforeground=self.FG,
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, sticky="w")

        tk.Label(inner_a, text=self.t["device_label"], bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.cmb_device = ttk.Combobox(
            inner_a, textvariable=self.var_mic_device,
            values=self._device_names, state="readonly", width=40,
        )
        self.cmb_device.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        if self._device_names:
            self.cmb_device.current(0)

        # ── Output Frame ──
        out_frame = ttk.LabelFrame(self, text=self.t["output_frame"], style="Card.TLabelframe")
        out_frame.pack(fill="x", **pad)

        inner_o = tk.Frame(out_frame, bg=self.CARD)
        inner_o.pack(fill="x", padx=8, pady=8)

        tk.Label(inner_o, text=self.t["fps_label"], bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="e", padx=(0, 4))
        ttk.Combobox(inner_o, textvariable=self.var_fps,
                     values=[15, 24, 30, 60], state="readonly", width=5
                     ).grid(row=0, column=1, sticky="w")

        tk.Label(inner_o, text=self.t["format_label"], bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 9)).grid(row=0, column=2, sticky="e", padx=(16, 4))
        ttk.Combobox(inner_o, textvariable=self.var_format,
                     values=["mp4", "mkv", "avi"], state="readonly", width=5
                     ).grid(row=0, column=3, sticky="w")

        tk.Label(inner_o, text=self.t["folder_label"], bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="e",
                                             padx=(0, 4), pady=(6, 0))
        tk.Entry(inner_o, textvariable=self.var_outdir, width=30,
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 font=("Segoe UI", 9), relief="flat", bd=4
                 ).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        tk.Button(inner_o, text="...", command=self._browse_dir,
                  bg=self.ENTRY_BG, fg=self.FG, relief="flat", width=3
                  ).grid(row=1, column=3, sticky="w", pady=(6, 0), padx=(4, 0))

        # ── Controls ──
        ctrl_frame = tk.Frame(self, bg=self.BG)
        ctrl_frame.pack(fill="x", padx=12, pady=(16, 4))

        self.btn_start = tk.Button(
            ctrl_frame, text=self.t["start_recording"], command=self._start_recording,
            bg=self.BTN_REC, fg="white", font=("Segoe UI", 12, "bold"),
            relief="flat", cursor="hand2", padx=20, pady=8,
        )
        self.btn_start.pack(fill="x")

        self.btn_stop = tk.Button(
            ctrl_frame, text=self.t["stop_recording"], command=self._stop_recording,
            bg=self.BTN_STOP, fg="#1e1e2e", font=("Segoe UI", 12, "bold"),
            relief="flat", cursor="hand2", padx=20, pady=8,
        )

        # ── Status ──
        tk.Label(
            self, textvariable=self.var_status, bg=self.BG, fg=self.FG,
            font=("Consolas", 10), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 10), side="bottom")

    # ── Language switch ──

    def _on_language_changed(self, event=None):
        lang = self.var_lang.get()
        if lang == self._lang:
            return
        self._lang = lang
        self.t = TRANSLATIONS[lang]
        save_language(lang)
        # Rebuild UI
        self._hide_overlay()
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
        self.var_status.set(self.t["status_ready"])

    # ── Overlay management ──

    def _toggle_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            self._hide_overlay()
        else:
            self._show_overlay()

    def _show_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()
        try:
            x, y = self.var_x.get(), self.var_y.get()
            w = max(32, self.var_w.get())
            h = max(32, self.var_h.get())
        except (tk.TclError, ValueError):
            return

        self._overlay = RegionOverlay(self, x, y, w, h,
                                       on_change=self._on_overlay_moved)
        self.btn_overlay.configure(text=self.t["hide_region"], bg="#e03e3e")
        self.var_status.set(self.t["status_overlay_active"])

    def _hide_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            self._overlay.destroy()
        self._overlay = None
        self.btn_overlay.configure(text=self.t["show_region"], bg="#5865f2")
        self.var_status.set(self.t["status_ready"])

    def _on_overlay_moved(self, x, y, w, h):
        self._suppress_field_update = True
        self.var_x.set(x)
        self.var_y.set(y)
        self.var_w.set(w)
        self.var_h.set(h)
        self._suppress_field_update = False

    def _on_field_changed(self, *args):
        if self._suppress_field_update:
            return
        if not self._overlay or not self._overlay.winfo_exists():
            return
        try:
            self._overlay.update_region(
                self.var_x.get(), self.var_y.get(),
                self.var_w.get(), self.var_h.get(),
            )
        except (tk.TclError, ValueError):
            pass

    def _apply_preset(self, w, h):
        self.var_w.set(w)
        self.var_h.set(h)

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_outdir.get())
        if d:
            self.var_outdir.set(d)

    def _select_region(self):
        self._hide_overlay()
        self.withdraw()
        self.after(200, lambda: RegionSelector(
            self, self._on_region_selected, self.t["overlay_instructions"]))

    def _on_region_selected(self, x, y, w, h):
        self.var_x.set(x)
        self.var_y.set(y)
        self.var_w.set(w)
        self.var_h.set(h)
        self.deiconify()
        self.var_status.set(self.t["status_region"].format(w=w, h=h, x=x, y=y))
        self.after(300, self._show_overlay)

    def _generate_filename(self):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"recording_{ts}.{self.var_format.get()}"

    def _start_recording(self):
        w = make_even(self.var_w.get())
        h = make_even(self.var_h.get())
        if w < 16 or h < 16:
            messagebox.showwarning(self.t["error_size_title"],
                                   self.t["error_size_msg"])
            return

        self._hide_overlay()

        Path(self.var_outdir.get()).mkdir(parents=True, exist_ok=True)

        self.recording = True
        self.btn_start.pack_forget()
        self.btn_stop.pack(fill="x")

        video_tmp = os.path.join(self._tmp_dir, "video_tmp.mp4")
        self.video_rec = VideoRecorder(
            video_tmp, self.var_x.get(), self.var_y.get(), w, h,
            fps=self.var_fps.get(),
        )
        self.video_rec.start()

        self.audio_rec = None
        if self.var_mic.get() and self._audio_devices:
            idx = self.cmb_device.current()
            if idx >= 0:
                dev_index = self._audio_devices[idx][0]
                channels = self._audio_devices[idx][2]
                audio_tmp = os.path.join(self._tmp_dir, "audio_tmp.wav")
                self.audio_rec = AudioRecorder(audio_tmp, dev_index, channels=channels)
                self.audio_rec.start()

        self.var_status.set(self.t["status_recording"])
        self._update_timer()

    def _update_timer(self):
        if not self.recording:
            return
        elapsed = self.video_rec.elapsed if self.video_rec else 0
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)
        frames = self.video_rec.frame_count if self.video_rec else 0
        self.var_status.set(f"⏺  {hrs:02d}:{mins:02d}:{secs:02d}  ·  {frames} Frames")
        self._timer_id = self.after(500, self._update_timer)

    def _stop_recording(self):
        self.recording = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
        self.var_status.set(self.t["status_processing"])
        self.update_idletasks()
        self.btn_stop.pack_forget()
        self.btn_start.pack(fill="x")
        threading.Thread(target=self._finalize, daemon=True).start()

    def _finalize(self):
        video_tmp = os.path.join(self._tmp_dir, "video_tmp.mp4")
        audio_tmp = os.path.join(self._tmp_dir, "audio_tmp.wav")

        duration = self.video_rec.stop() if self.video_rec else 0
        has_audio = self.audio_rec.stop() if self.audio_rec else False

        final_path = str(Path(self.var_outdir.get()) / self._generate_filename())

        if has_audio and os.path.exists(audio_tmp):
            if not mux_audio_video(video_tmp, audio_tmp, final_path):
                os.replace(video_tmp, final_path)
        elif os.path.exists(video_tmp):
            os.replace(video_tmp, final_path)

        for f in [video_tmp, audio_tmp]:
            try:
                os.remove(f)
            except OSError:
                pass

        mins, secs = divmod(int(duration), 60)
        self.after(0, self.var_status.set,
                   self.t["status_saved"].format(
                       name=Path(final_path).name,
                       time=f"{mins}:{secs:02d}"))

    def destroy(self):
        self.recording = False
        self._hide_overlay()
        if self.video_rec:
            self.video_rec.stop()
        if self.audio_rec:
            self.audio_rec.stop()
        try:
            os.rmdir(self._tmp_dir)
        except OSError:
            pass
        super().destroy()


if __name__ == "__main__":
    app = RecorderApp()
    app.mainloop()
