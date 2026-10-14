# Claude Robot Pet

A small blocky robot ("Clawd"-inspired, drawn from scratch in code — not the
official artwork) that walks back and forth along the bottom of your screen.
Click it to pop up a project picker; pick a project and it opens a terminal
and launches [Claude Code](https://docs.claude.com/en/docs/claude-code) in
that project's folder. Right-click it for an exit menu.

It automatically hides itself while a fullscreen app (e.g. a game) is in the
foreground, and reappears when you switch away, so it doesn't flicker over
or steal clicks from fullscreen games.

> Windows only. It relies on Win32 APIs (`ctypes.windll.user32`) and Tk's
> `-transparentcolor`, which macOS/Linux don't support the same way.

## Files

- `robot_pet.py` — the whole app (sprite generation, movement, click handling,
  project picker).
- `projects.example.json` — sample project list. Copy it to `projects.json`
  and edit (see below). `projects.json` itself is git-ignored because it
  contains your local paths.

## Installation (Windows)

### 1. Prerequisites

| What | Why | How to install |
|---|---|---|
| Python 3.8+ (with Tk, which the python.org installer includes) | runs the pet | `winget install Python.Python.3.12` or [python.org](https://www.python.org/downloads/) — tick **"Add python.exe to PATH"** |
| Pillow | draws the sprite | `pip install pillow` |
| Claude Code CLI (`claude` on PATH) | what the pet launches | see the [Claude Code docs](https://docs.claude.com/en/docs/claude-code) |
| Windows Terminal (optional) | proper Claude Code logo colors; falls back to plain `powershell.exe` | preinstalled on Windows 11, otherwise `winget install Microsoft.WindowsTerminal` |

Check that `claude` works from a fresh PowerShell window before continuing —
the pet just runs `claude` in the chosen folder, so if it isn't on PATH
nothing will happen.

### 2. Get the code

```powershell
git clone https://github.com/VictorYuuuu/claude-robot-pet.git
cd claude-robot-pet
pip install pillow
```

(Or download the ZIP from GitHub and extract it anywhere, e.g.
`C:\Users\<you>\RobotPet`.)

### 3. Configure your projects

```powershell
copy projects.example.json projects.json
notepad projects.json
```

Edit the list to point at your own project folders:

```json
[
    { "name": "My Project", "path": "C:\\Users\\you\\Projects\\my-project" },
    { "name": "Home folder", "path": "C:\\Users\\you" }
]
```

Note the doubled backslashes (`\\`) — that's required in JSON. Save the file
as UTF-8 (Notepad's default) if you use non-ASCII project names.

You can skip this step: if `projects.json` doesn't exist, the picker's
"✏️ 編輯專案清單" (edit project list) row creates an empty one and opens it
in Notepad for you.

### 4. Try it

```powershell
python robot_pet.py
```

The robot should appear above the taskbar and start walking. Click it, pick
a project, and a terminal running Claude Code should open in that folder.

## Start automatically at login

The simplest way is a small `.bat` file in your Startup folder that launches
the pet with `pythonw.exe` (the windowless Python, so no console flashes up).

Run this once in PowerShell **from the folder containing `robot_pet.py`**:

```powershell
$pythonw = (Get-Command pythonw.exe).Source
$script  = (Resolve-Path .\robot_pet.py).Path
$startup = [Environment]::GetFolderPath('Startup')
"@echo off`r`nstart `"`" `"$pythonw`" `"$script`"" |
  Set-Content -Encoding ASCII "$startup\RobotPet.bat"
```

That creates `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RobotPet.bat`
with contents like:

```bat
@echo off
start "" "C:\Users\you\AppData\Local\Programs\Python\Python312\pythonw.exe" "C:\Users\you\RobotPet\robot_pet.py"
```

You can also create it by hand: press `Win + R`, type `shell:startup`, and
save a `.bat` file like the one above in the folder that opens. Use full
paths — the Startup folder doesn't run with your project as the working
directory.

If `Get-Command pythonw.exe` fails, Python isn't on PATH; use the full path
to `pythonw.exe` (it sits next to `python.exe`, which `py -c "import sys; print(sys.executable)"`
will show you).

To test without logging out, double-click `RobotPet.bat`.

### Disabling autostart

Delete `RobotPet.bat` from the Startup folder (`Win + R` → `shell:startup`).
Alternatively, Task Manager → **Startup apps** lets you toggle it off without
deleting it.

## Project picker

Left-clicking the robot opens a dark popup listing the projects in
`projects.json`. The file is re-read every time you click, so no restart is
needed after editing. Rows whose `path` no longer exists are shown grayed out
and can't be clicked. If the file is missing or empty, the popup shows a hint
instead of a list. Click "取消" (cancel) or a project row to close the popup.

The "✏️ 編輯專案清單" row (above 取消) opens `projects.json` directly in
Notepad — creating an empty `[]` file first if it doesn't exist yet.

Picking a project runs `claude` in that folder via a new terminal window,
with `COLORTERM=truecolor` set explicitly — Windows Terminal doesn't set
this itself, and without it Claude Code's logo renders in monochrome
instead of its usual orange.

## Stopping it

Right-click the robot and choose "結束" (Exit). Or, if it's not visible /
stuck: open Task Manager and end the `pythonw.exe` (or `python.exe`) process
running `robot_pet.py`. From PowerShell:

```powershell
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*robot_pet.py*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Nothing appears when launched via `pythonw` | Run `python robot_pet.py` instead to see the error — usually `ModuleNotFoundError: No module named 'PIL'` (run `pip install pillow` for *that* Python). |
| Terminal opens then says `claude` is not recognized | Claude Code isn't on PATH for new shells. Reinstall it or add its folder to PATH, then re-open. |
| Claude Code logo is monochrome | Windows Terminal isn't installed, so it fell back to the classic console. |
| Two robots walking | It was started twice (e.g. Startup + manual). There's no single-instance lock; exit one. |
| Garbled Chinese project names | `projects.json` wasn't saved as UTF-8. |

## Tuning / common tweaks (all in `robot_pet.py`)

| What | Constant |
|---|---|
| Size (width/height per grid cell) | `SCALE_X`, `SCALE_Y` |
| Walking speed | `MOVE_STEP`, `MOVE_INTERVAL_MS` |
| Walk-cycle animation speed | `FRAME_SWITCH_EVERY` |
| Body / eye color | `BODY_COLOR`, `EYE_COLOR` |
| Click-launch cooldown | `CLICK_COOLDOWN_S` |
| Fullscreen-hide check interval | `FULLSCREEN_CHECK_MS` |
| Sprite shape (pixel grid) | `BASE_ROWS`, `EYE_CELLS`, `LEG_COLS_LEFT/RIGHT` |
| Project list file | `PROJECTS_FILE` (defaults to `projects.json` next to the script) |
| Picker colors / size | `PICKER_BG`, `ROW_BG`, `ROW_HOVER_BG`, `ROW_INVALID_BG`, `ROW_TEXT`, `ROW_INVALID_TEXT`, `CANCEL_BG`, `CANCEL_HOVER_BG`, `PICKER_WIDTH`, `ROW_HEIGHT`, `ROW_GAP`, `ROW_RADIUS` |

To change the shape, edit `BASE_ROWS` (a 12-column grid of `0`/`1` strings —
`1` = body). The legs (rows 9–11) are generated separately in `build_frame()`
so the walk cycle can alternate which leg is "lifted".

## Known limitations

- No lock/mutex: launching the script twice spawns a second robot.
- Only walks along the primary monitor's bottom edge (uses
  `SystemParametersInfoW(SPI_GETWORKAREA)`, which excludes the taskbar).
- The window is kept `-topmost` and re-asserts this every 5s
  (`TOPMOST_REASSERT_MS`), which keeps it above wallpaper apps such as
  Wallpaper Engine. If some other always-on-top app covers it, that's the
  setting to look at first.
- Fullscreen detection compares the foreground window's rect against its
  monitor's full bounds (`is_fullscreen_app_active`), so it catches both
  exclusive-fullscreen and borderless-fullscreen games, but not a merely
  maximized window (which respects the taskbar).
- The project picker has no add/remove UI on purpose — `projects.json` is
  meant to be hand-edited. No search/filter box either.

## Disclaimer

Unofficial fan project; not affiliated with or endorsed by Anthropic.
"Claude" and "Claude Code" are Anthropic's names, used here only to describe
what the tool launches.
