"""Small desktop pet: a blocky robot that walks along the bottom of the
screen. Click it to open PowerShell and launch Claude Code.
"""

import ctypes
import json
import os
import shutil
import subprocess
import time
import tkinter as tk

from PIL import Image, ImageColor, ImageTk

TRANSPARENT_KEY = "#FF00FE"  # unlikely to appear in the sprite, used as click-through color
BODY_COLOR = "#CC785C"
EYE_COLOR = "#000000"
TRANSPARENT_KEY_RGB = ImageColor.getrgb(TRANSPARENT_KEY)
BODY_COLOR_RGB = ImageColor.getrgb(BODY_COLOR)
EYE_COLOR_RGB = ImageColor.getrgb(EYE_COLOR)
SCALE_X = 6  # pixels per grid cell, horizontal
SCALE_Y = 4  # pixels per grid cell, vertical (smaller = flatter)
MOVE_STEP = 3
MOVE_INTERVAL_MS = 40
FRAME_SWITCH_EVERY = 4  # move-steps per walk-frame swap
TOPMOST_REASSERT_MS = 5000
CLICK_COOLDOWN_S = 2.0
FULLSCREEN_CHECK_MS = 2000
FULLSCREEN_IGNORE_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Button", ""}

PROJECTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.json")
PICKER_BG = "#1E1E1E"
ROW_BG = "#2A2A2A"
ROW_HOVER_BG = "#3A3A3A"
ROW_INVALID_BG = "#242424"
ROW_TEXT = "#EAEAEA"
ROW_INVALID_TEXT = "#6E6E6E"
CANCEL_BG = "#3A2A2A"
CANCEL_HOVER_BG = "#4A3232"
TITLE_TEXT = "#B0B0B0"
PICKER_WIDTH = 320
ROW_HEIGHT = 44
ROW_GAP = 8
ROW_RADIUS = 10
PICKER_PADDING = 16

# 12x12 grid: head/torso with side nubs and eyes; rows 9-11 are the legs
# and are rebuilt per walk-frame in build_frame().
BASE_ROWS = [
    "000111111000",
    "000111111000",
    "000111111000",
    "110111111011",
    "110111111011",
    "000111111000",
    "000111111000",
    "000111111000",
    "000111111000",
]
EYE_CELLS = [(3, 5), (4, 5), (7, 5), (8, 5), (3, 6), (4, 6), (7, 6), (8, 6)]
LEG_COLS_LEFT = (3, 4)
LEG_COLS_RIGHT = (7, 8)
GRID_W = 12


def build_frame(lifted_leg: str) -> Image.Image:
    rows = list(BASE_ROWS)
    for row_i in (9, 10, 11):
        cells = ["0"] * GRID_W
        for c in LEG_COLS_LEFT:
            cells[c] = "1"
        for c in LEG_COLS_RIGHT:
            cells[c] = "1"
        if lifted_leg == "left" and row_i == 9:
            for c in LEG_COLS_LEFT:
                cells[c] = "0"
        if lifted_leg == "right" and row_i == 9:
            for c in LEG_COLS_RIGHT:
                cells[c] = "0"
        rows.append("".join(cells))

    h = len(rows)
    img = Image.new("RGB", (GRID_W, h), TRANSPARENT_KEY_RGB)
    px = img.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "1":
                px[x, y] = BODY_COLOR_RGB
    for x, y in EYE_CELLS:
        px[x, y] = EYE_COLOR_RGB

    img = img.resize((GRID_W * SCALE_X, h * SCALE_Y), Image.NEAREST)
    return img


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def get_work_area():
    SPI_GETWORKAREA = 0x0030
    rect = RECT()
    ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right, rect.bottom


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def is_fullscreen_app_active(own_hwnd) -> bool:
    """True if the foreground window covers an entire monitor (exclusive or
    borderless-fullscreen games/apps), as opposed to a merely maximized
    window (which still respects the taskbar's work area)."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd or hwnd == own_hwnd:
        return False

    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    if buf.value in FULLSCREEN_IGNORE_CLASSES:
        return False

    win_rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
        return False

    MONITOR_DEFAULTTONEAREST = 2
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return False
    mon = info.rcMonitor

    return (
        win_rect.left <= mon.left
        and win_rect.top <= mon.top
        and win_rect.right >= mon.right
        and win_rect.bottom >= mon.bottom
    )


def round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def load_projects():
    if not os.path.isfile(PROJECTS_FILE):
        return []
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [
        {"name": str(entry["name"]), "path": str(entry["path"])}
        for entry in data
        if isinstance(entry, dict) and "name" in entry and "path" in entry
    ]


class ProjectPicker:
    """Dark rounded-row popup listing projects.json; picks a folder to
    launch Claude Code in, or cancels."""

    def __init__(self, parent, on_select, on_edit_projects):
        self.on_select = on_select
        self.on_edit_projects = on_edit_projects
        self.projects = load_projects()

        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=PICKER_BG)

        tk.Label(
            self.win, text="選擇專案", bg=PICKER_BG, fg=TITLE_TEXT,
            font=("Segoe UI", 11, "bold"), pady=10,
        ).pack(fill="x")

        row_count = max(len(self.projects), 1) + 2  # +1 edit row, +1 cancel row
        canvas_h = row_count * ROW_HEIGHT + (row_count - 1) * ROW_GAP + PICKER_PADDING * 2
        self.canvas = tk.Canvas(
            self.win, width=PICKER_WIDTH, height=canvas_h, bg=PICKER_BG, highlightthickness=0,
        )
        self.canvas.pack()

        y = PICKER_PADDING
        if self.projects:
            for proj in self.projects:
                valid = os.path.isdir(proj["path"])
                suffix = "" if valid else "(找不到資料夾)"
                self._add_row(y, proj["name"], valid, proj["path"] if valid else None, suffix)
                y += ROW_HEIGHT + ROW_GAP
        else:
            self.canvas.create_text(
                PICKER_WIDTH / 2, y + ROW_HEIGHT / 2,
                text=f"尚未設定專案,請編輯\n{PROJECTS_FILE}",
                fill=ROW_INVALID_TEXT, font=("Segoe UI", 9), justify="center",
            )
            y += ROW_HEIGHT + ROW_GAP

        self._add_row(y, "✏️ 編輯專案清單", True, None, on_click_override=self.on_edit_projects)
        y += ROW_HEIGHT + ROW_GAP
        self._add_row(y, "取消", True, None, is_cancel=True)

        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _add_row(self, y, text, enabled, path, suffix="", is_cancel=False, on_click_override=None):
        x1, x2 = PICKER_PADDING, PICKER_WIDTH - PICKER_PADDING
        y2 = y + ROW_HEIGHT
        bg = CANCEL_BG if is_cancel else (ROW_BG if enabled else ROW_INVALID_BG)
        hover_bg = CANCEL_HOVER_BG if is_cancel else ROW_HOVER_BG
        fg = ROW_TEXT if enabled else ROW_INVALID_TEXT

        rect = round_rect(self.canvas, x1, y, x2, y2, ROW_RADIUS, fill=bg, outline="")
        label = text if not suffix else f"{text} {suffix}"
        txt = self.canvas.create_text(
            (x1 + x2) / 2, (y + y2) / 2, text=label, fill=fg, font=("Segoe UI", 10),
        )
        if not enabled:
            return

        def on_enter(_e):
            self.canvas.itemconfig(rect, fill=hover_bg)
            self.canvas.config(cursor="hand2")

        def on_leave(_e):
            self.canvas.itemconfig(rect, fill=bg)
            self.canvas.config(cursor="")

        def on_click(_e):
            self.close()
            if on_click_override is not None:
                on_click_override()
            else:
                self.on_select(None if is_cancel else path)

        for item in (rect, txt):
            self.canvas.tag_bind(item, "<Enter>", on_enter)
            self.canvas.tag_bind(item, "<Leave>", on_leave)
            self.canvas.tag_bind(item, "<Button-1>", on_click)

    def close(self):
        self.win.destroy()


class RobotPet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.configure(bg=TRANSPARENT_KEY)

        self.frames = {
            "left": {
                "A": ImageTk.PhotoImage(build_frame("left")),
                "B": ImageTk.PhotoImage(build_frame("right")),
            },
        }
        base_a = build_frame("left").transpose(Image.FLIP_LEFT_RIGHT)
        base_b = build_frame("right").transpose(Image.FLIP_LEFT_RIGHT)
        self.frames["right"] = {
            "A": ImageTk.PhotoImage(base_a),
            "B": ImageTk.PhotoImage(base_b),
        }

        sample = build_frame("left")
        self.img_w, self.img_h = sample.size

        wa_left, wa_top, wa_right, wa_bottom = get_work_area()
        self.min_x = wa_left
        self.max_x = wa_right - self.img_w
        self.y = wa_bottom - self.img_h
        self.x = (self.min_x + self.max_x) // 2

        self.direction = "left"
        self.walk_frame = "A"
        self.step_count = 0
        self.last_launch = 0.0
        self.hidden = False
        self.picker = None

        self.label = tk.Label(
            self.root, bd=0, highlightthickness=0, bg=TRANSPARENT_KEY,
            image=self.frames[self.direction][self.walk_frame], cursor="hand2",
        )
        self.label.pack()
        self.label.bind("<Button-1>", self.on_click)
        self.label.bind("<Button-3>", self.on_right_click)

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="結束", command=self.root.destroy)

        self.root.geometry(f"{self.img_w}x{self.img_h}+{self.x}+{self.y}")
        self.root.after(MOVE_INTERVAL_MS, self.tick)
        self.root.after(TOPMOST_REASSERT_MS, self.reassert_topmost)
        self.root.after(FULLSCREEN_CHECK_MS, self.check_fullscreen)

    def reassert_topmost(self):
        if not self.hidden:
            self.root.attributes("-topmost", True)
        self.root.after(TOPMOST_REASSERT_MS, self.reassert_topmost)

    def check_fullscreen(self):
        own_hwnd = self.root.winfo_id()
        fullscreen = is_fullscreen_app_active(own_hwnd)
        if fullscreen and not self.hidden:
            self.hidden = True
            self.root.withdraw()
        elif not fullscreen and self.hidden:
            self.hidden = False
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        self.root.after(FULLSCREEN_CHECK_MS, self.check_fullscreen)

    def tick(self):
        dx = -MOVE_STEP if self.direction == "left" else MOVE_STEP
        self.x += dx
        if self.x <= self.min_x:
            self.x = self.min_x
            self.direction = "right"
        elif self.x >= self.max_x:
            self.x = self.max_x
            self.direction = "left"

        self.step_count += 1
        if self.step_count % FRAME_SWITCH_EVERY == 0:
            self.walk_frame = "B" if self.walk_frame == "A" else "A"

        self.label.configure(image=self.frames[self.direction][self.walk_frame])
        self.root.geometry(f"+{self.x}+{self.y}")
        self.root.after(MOVE_INTERVAL_MS, self.tick)

    def on_click(self, _event):
        if self.picker is not None:
            return
        now = time.time()
        if now - self.last_launch < CLICK_COOLDOWN_S:
            return
        self.last_launch = now
        self.picker = ProjectPicker(self.root, self.on_project_selected, self.on_edit_projects)

    def on_project_selected(self, path):
        self.picker = None
        if path:
            self.launch_project(path)

    def on_edit_projects(self):
        self.picker = None
        if not os.path.isfile(PROJECTS_FILE):
            try:
                with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
                    f.write("[]\n")
            except OSError:
                pass
        subprocess.Popen(["notepad.exe", PROJECTS_FILE])

    def launch_project(self, path):
        # Windows Terminal doesn't set COLORTERM itself, so CLI tools that
        # check it for truecolor support (e.g. claude's logo) render
        # monochrome unless we set it explicitly for the child process.
        env = dict(os.environ, COLORTERM="truecolor")
        wt_path = shutil.which("wt.exe") or shutil.which("wt")
        if wt_path:
            # -d sets the starting directory so we don't need to smuggle a
            # `cd` through wt's own ';'-delimited argument syntax.
            subprocess.Popen(
                [wt_path, "-w", "-1", "-d", path, "powershell.exe", "-NoExit", "-Command", "claude"],
                env=env,
            )
        else:
            subprocess.Popen(
                ["powershell.exe", "-NoExit", "-Command", f"cd '{path}'; claude"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                env=env,
            )

    def on_right_click(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    RobotPet().run()
