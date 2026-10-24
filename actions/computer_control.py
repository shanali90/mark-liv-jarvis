#computer_control.py
import json
import platform
import string
import subprocess
import sys
import numpy as np
from core.dpi import set_process_dpi_awareness


set_process_dpi_awareness()
if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:

    _WIN_HIDE: dict = {}
import time
import random
from pathlib import Path

pyautogui = None
_PYAUTOGUI = None

pyperclip = None
_PYPERCLIP = None

def _get_pyperclip():
    global pyperclip, _PYPERCLIP
    if _PYPERCLIP is None:
        try:
            import pyperclip as _pc
            pyperclip = _pc
            _PYPERCLIP = True
        except ImportError:
            _PYPERCLIP = False
    return _PYPERCLIP


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "settings.json"
_MEMORY_PATH  = _BASE / "memory" / "long_term.json"
_CLICK_CHANGE_THRESHOLD = 2.0

def _load_config() -> dict:
    try:
        config = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    _remove_secret_fields(config)
    return config


def _remove_secret_fields(config: dict) -> None:
    for key in list(config):
        value = config[key]
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            del config[key]
        elif isinstance(value, dict):
            _remove_secret_fields(value)

def _platform_os() -> str:
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def _get_os() -> str:
    return _load_config().get("os_system", _platform_os()).lower()


def _get_api_key() -> str:
    from core.vault import get_secret

    return get_secret("gemini_api_key")

_SAFE_SCREENSHOT_ROOTS = (
    Path.home(),
)

def _safe_screenshot_path(requested: str | None) -> Path:
    from core.paths import desktop as _real_desktop
    fallback = _real_desktop() / "jarvis_screenshot.png"
    if not requested:
        return fallback
    try:
        # "desktop/x.png" means the user's real Desktop, not a folder called
        # "desktop" inside the project (that is where it used to be saved).
        from core.paths import user_folder as _user_folder
        _parts = Path(str(requested).replace("\\", "/")).parts
        if _parts and _parts[0].lower() in ("desktop", "downloads", "documents", "videos", "pictures"):
            requested = str(_user_folder(_parts[0]).joinpath(*_parts[1:]))
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback

def _require_pyautogui():
    global pyautogui, _PYAUTOGUI
    if _PYAUTOGUI is None:
        try:
            import pyautogui as _pa
            _pa.FAILSAFE = True
            _pa.PAUSE    = 0.05
            pyautogui = _pa
            _PYAUTOGUI = True
        except ImportError:
            _PYAUTOGUI = False
    if not _PYAUTOGUI or pyautogui is None:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)

    if dt == "last_name":
        return random.choice(_LAST_NAMES)

    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"

    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"

    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"

    if dt == "password":
        chars = string.ascii_letters + string.digits + "!@#$%"
        raw   = (
            random.choice(string.ascii_uppercase)
            + random.choice(string.digits)
            + random.choice("!@#$%")
            + "".join(random.choices(chars, k=9))
        )
        return "".join(random.sample(raw, len(raw)))

    if dt == "phone":
        return f"+1{random.randint(200,999)}{random.randint(1_000_000, 9_999_999)}"

    if dt == "birthday":
        y = random.randint(1980, 2000)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"

    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"

    if dt == "zip_code":
        return str(random.randint(10000, 99999))

    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"

def _user_profile() -> dict:
    """Read identity fields from long-term memory."""
    try:
        if _MEMORY_PATH.exists():
            data     = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            return {k: v.get("value", "") for k, v in identity.items()}
    except Exception:
        pass
    return {}

def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)

    if len(text) > 20 and _get_pyperclip():
        pyperclip.copy(text)
        time.sleep(0.1)
        paste_key = "command" if _get_os() == "mac" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
        return f"Smart-typed (clipboard): {text[:60]}{'…' if len(text) > 60 else ''}"

    pyautogui.typewrite(text, interval=0.04)
    return f"Smart-typed: {text[:60]}{'…' if len(text) > 60 else ''}"


def _screen_to_mouse(x: int, y: int, monitor: dict | None = None) -> tuple[int, int]:
    """Convert physical screenshot coordinates into PyAutoGUI screen coordinates."""
    _require_pyautogui()
    if monitor is None:
        import mss

        with mss.mss() as sct:
            monitor = dict(sct.monitors[1])

    screen_width, screen_height = pyautogui.size()
    scale_x = screen_width / monitor["width"]
    scale_y = screen_height / monitor["height"]
    return (
        round((x - monitor["left"]) * scale_x),
        round((y - monitor["top"]) * scale_y),
    )


def _clamp_to_screen(x: int, y: int) -> tuple[int, int]:
    width, height = pyautogui.size()
    return max(1, min(int(x), width - 2)), max(1, min(int(y), height - 2))


def _move_exact(x: int, y: int) -> tuple[int, int] | None:
    """Move smoothly to a target, retry once, and verify the resulting position."""
    x, y = _clamp_to_screen(x, y)
    for _ in range(2):
        pyautogui.moveTo(x, y, duration=0.25)
        actual_x, actual_y = pyautogui.position()
        if abs(actual_x - x) <= 3 and abs(actual_y - y) <= 3:
            return x, y
    return None


def _click(
    x=None,
    y=None,
    button: str = "left",
    clicks: int = 1,
    *,
    current_position: bool = False,
) -> str:
    _require_pyautogui()
    if x is None or y is None:
        if not current_position:
            return "I need a target. Tell me what to click."
        x, y = pyautogui.position()

    x, y = _clamp_to_screen(x, y)
    if _move_exact(x, y) is None:
        actual_x, actual_y = pyautogui.position()
        return (
            f"Could not position the mouse at ({x}, {y}); "
            f"it remained at ({actual_x}, {actual_y}). Nothing was clicked."
        )
    pyautogui.click(x, y, button=button, clicks=clicks)
    return f"Clicked ({x}, {y}) [{button}]"


def _screen_thumbnail() -> "np.ndarray":
    """Capture a compact grayscale image of the primary monitor for verification."""
    import mss
    import PIL.Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
    image = PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return np.asarray(image.convert("L").resize((64, 36)), dtype=np.uint8)


def _screen_changed(before, after) -> bool:
    return float(np.mean(np.abs(before.astype(np.int16) - after.astype(np.int16)))) > _CLICK_CHANGE_THRESHOLD


def _verified_click(
    target: str,
    x=None,
    y=None,
    button: str = "left",
    clicks: int = 1,
    *,
    current_position: bool = False,
) -> str:
    if x is None or y is None:
        if not current_position:
            return "I need a target. Tell me what to click."
        x, y = pyautogui.position()
    x, y = _clamp_to_screen(x, y)

    try:
        before = _screen_thumbnail()
    except Exception as e:
        return f"Could not verify the click on '{target}': screen capture failed: {e}"

    result = _click(x, y, button, clicks)
    if result.startswith("Could not") or result.startswith("I need"):
        return result

    try:
        time.sleep(0.6)
        after = _screen_thumbnail()
        if _screen_changed(before, after):
            return f"Clicked '{target}' at ({x},{y}) - the screen changed, it worked."
        time.sleep(1.0)
        after = _screen_thumbnail()
        if _screen_changed(before, after):
            return f"Clicked '{target}' at ({x},{y}) - the screen changed, it worked."
    except Exception as e:
        return f"Clicked '{target}' at ({x},{y}) but could not verify the screen change: {e}"
    return f"Clicked '{target}' at ({x},{y}) but NOTHING changed on screen - it may not have worked."


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical   = direction in ("up", "down")
    clicks     = amount if direction in ("up", "right") else -amount
    pyautogui.scroll(clicks) if vertical else pyautogui.hscroll(clicks)
    return f"Scrolled {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.25) -> str:
    _require_pyautogui()
    target = _clamp_to_screen(x, y)
    if _move_exact(*target) is None:
        actual_x, actual_y = pyautogui.position()
        return (
            f"Mouse move failed: target ({target[0]}, {target[1]}), "
            f"actual ({actual_x}, {actual_y}) after retry."
        )
    return f"Mouse moved to ({target[0]}, {target[1]})."


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    x1, y1 = _clamp_to_screen(x1, y1)
    x2, y2 = _clamp_to_screen(x2, y2)
    for attempt in range(2):
        if _move_exact(x1, y1) is None:
            return f"Drag failed: could not position at start ({x1}, {y1})."
        pyautogui.dragTo(x2, y2, duration=duration, button="left")
        actual_x, actual_y = pyautogui.position()
        if abs(actual_x - x2) <= 3 and abs(actual_y - y2) <= 3:
            return f"Dragged ({x1},{y1}) → ({x2},{y2})"
        if attempt == 1:
            return (
                f"Drag ended at ({actual_x}, {actual_y}), not "
                f"({x2}, {y2}); the target was not reached."
            )
    return f"Drag failed to reach ({x2}, {y2})."


def _clipboard_get() -> str:
    if _get_pyperclip():
        return pyperclip.paste()
    _hotkey("ctrl", "c")
    time.sleep(0.2)
    return "(copied — pyperclip unavailable for read)"


def _clipboard_paste(text: str) -> str:
    if _get_pyperclip():
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        paste_key = "command" if _get_os() == "mac" else "ctrl"
        pyautogui.hotkey(paste_key, "v")
        return f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip not available"


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img  = pyautogui.screenshot()
    img.save(str(path))
    return f"Screenshot saved: {path}"


def _clear_field() -> str:
    _require_pyautogui()
    select_key = "command" if _get_os() == "mac" else "ctrl"
    pyautogui.hotkey(select_key, "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"

def _focus_window(title: str) -> str:
    os_name = _get_os()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=5, **_WIN_HIDE,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
        script = (
            f'tell application "System Events" to '
            f'set frontmost of (first process whose name contains "{title}") to true'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (macOS) failed: {e}"

    if os_name == "linux":
        try:
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {title}"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", title, "windowactivate"],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except FileNotFoundError:
            return "focus_window (Linux) requires wmctrl or xdotool"
        except Exception as e:
            return f"focus_window (Linux) failed: {e}"

    return f"focus_window: unknown OS '{os_name}'"

def _screen_find(description: str, crop_box: tuple = None) -> tuple[int, int] | None:
    try:
        import mss
        from google.genai import types as gtypes
        import io
        import PIL.Image

        _require_pyautogui()
        with mss.mss() as sct:
            monitor = dict(sct.monitors[1])
            shot = sct.grab(monitor)
            img = PIL.Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            if crop_box:
                crop_left = max(0, crop_box[0] - monitor["left"])
                crop_top = max(0, crop_box[1] - monitor["top"])
                crop_right = min(monitor["width"], crop_box[2] - monitor["left"])
                crop_bottom = min(monitor["height"], crop_box[3] - monitor["top"])
                if crop_right <= crop_left or crop_bottom <= crop_top:
                    return None
                img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                crop_origin = (monitor["left"] + crop_left, monitor["top"] + crop_top)
            else:
                crop_origin = (monitor["left"], monitor["top"])

        from core import gemini
        import re

        def locate(image, origin):
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            prompt = (
                f"This is a screenshot of my screen. Find the UI element described as: "
                f"'{description}'. Reply ONLY with its tight bounding box in this exact "
                f"format: [ymin, xmin, ymax, xmax], normalized from 0 to 1000. "
                f"If it is not visible, reply ONLY with: NOT_FOUND"
            )
            response = gemini.call(
                [gtypes.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"), prompt],
                tier=gemini.FAST, timeout_ms=20_000,
            )
            if response is None:
                return "error", None
            text = (response.text or "").strip()
            if "NOT_FOUND" in text.upper():
                return "not_found", None
            match = re.search(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", text)
            if not match:
                return "error", None
            ymin, xmin, ymax, xmax = map(int, match.groups())
            physical_x = origin[0] + int(((xmin + xmax) / 2) * image.width / 1000.0)
            physical_y = origin[1] + int(((ymin + ymax) / 2) * image.height / 1000.0)
            return "found", _screen_to_mouse(physical_x, physical_y, monitor)

        status, coords = locate(img, crop_origin)
        if status == "found":
            return coords
        if status != "not_found":
            return None

        # Retry once on a smaller center crop; coordinates remain relative to
        # the primary monitor so multi-monitor offsets are preserved.
        crop_left, crop_top = img.width // 4, img.height // 4
        crop_right, crop_bottom = crop_left + img.width // 2, crop_top + img.height // 2
        retry_img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
        retry_origin = (crop_origin[0] + crop_left, crop_origin[1] + crop_top)
        status, coords = locate(retry_img, retry_origin)
        return coords if status == "found" else None

    except Exception as e:
        print(f"[ComputerControl] ERROR screen_find failed: {e}")

    return None

def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for all computer control actions.

    parameters keys (all optional unless noted):
      action        : (required) one of the actions listed below
      text          : text to type or paste
      x, y          : screen coordinates
      button        : 'left' | 'right' (default: left)
      keys          : hotkey string, e.g. 'ctrl+c'
      key           : single key name, e.g. 'enter'
      direction     : 'up' | 'down' | 'left' | 'right'
      amount        : scroll amount (default: 3)
      seconds       : wait duration
      title         : window title fragment for focus_window
      description   : natural-language element description for screen_find/click
      type          : data type for random_data
      field         : memory field name for user_data
      clear_first   : bool, clear field before typing (default: true)
      path          : save path for screenshot (must be inside home dir)

    Actions:
      type          — type text at cursor
      smart_type    — clear field + type (clipboard-backed)
      click         — left click
      double_click  — double left click
      right_click   — right click
      move          — move mouse
      drag          — click-drag between two points
      hotkey        — key combination
      press         — single key
      scroll        — scroll the wheel
      copy          — read clipboard
      paste         — write + paste clipboard
      screenshot    — capture screen (safe path only)
      wait          — sleep N seconds
      clear_field   — select-all + delete
      focus_window  — bring window to foreground
      screen_find   — AI element finder (returns x,y)
      screen_click  — AI element finder + click
      random_data   — generate fake form data
      user_data     — pull real data from memory
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {params}")

    try:

        if action == "type":
            return _type(params.get("text", ""))

        if action == "smart_type":
            return _smart_type(
                params.get("text", ""),
                clear_first=params.get("clear_first", True),
            )

        if action in ("click", "left_click"):
            return _verified_click(
                "current position" if params.get("current_position") else "screen coordinates",
                params.get("x"), params.get("y"), "left", 1,
                current_position=params.get("current_position", False),
            )

        if action == "double_click":
            return _verified_click(
                "screen coordinates", params.get("x"), params.get("y"), "left", 2,
            )

        if action == "right_click":
            return _verified_click(
                "screen coordinates", params.get("x"), params.get("y"), "right", 1,
            )

        if action == "move":
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        if action == "drag":
            return _drag(
                int(params.get("x1", 0)), int(params.get("y1", 0)),
                int(params.get("x2", 0)), int(params.get("y2", 0)),
            )

        if action == "hotkey":
            raw  = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            return _hotkey(*keys)

        if action == "press":
            return _press(params.get("key", "enter"))

        if action == "scroll":
            return _scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
            )

        if action == "copy":
            return _clipboard_get()

        if action == "paste":
            return _clipboard_paste(params.get("text", ""))

        if action == "screenshot":
            return _screenshot(params.get("path"))

        if action == "camera_snapshot":
            from actions.screen_processor import _capture_camera
            import io, PIL.Image
            path = _safe_screenshot_path(params.get("path"))
            # _capture_camera returns (bytes, mime_type)
            img_bytes, _ = _capture_camera()
            img = PIL.Image.open(io.BytesIO(img_bytes))
            img.save(str(path))
            return f"Camera photo saved: {path}"

        if action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        if action == "screen_click":
            desc = params.get("description", "")
            coords = _screen_find(desc)
            if not coords:
                return f"I could not find '{desc}' on screen."
            return _verified_click(desc, x=coords[0], y=coords[1])

        if action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = min(secs, 30.0)
            time.sleep(secs)
            return f"Waited {secs}s"

        if action == "clear_field":
            return _clear_field()

        if action == "focus_window":
            return _focus_window(params.get("title", ""))

        if action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 random {dt} → {result}")
            return result

        if action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ERROR No '{field}' in memory, using random: {value}")
            return value

        return f"Unknown action: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' failed: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "computer_control",
    "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen. Report the tool result to the user honestly. Never claim success when the result says nothing changed or not found.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | camera_snapshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"
            },
            "text": {
                "type": "STRING",
                "description": "Text to type or paste"
            },
            "x": {
                "type": "INTEGER",
                "description": "X coordinate"
            },
            "y": {
                "type": "INTEGER",
                "description": "Y coordinate"
            },
            "current_position": {
                "type": "BOOLEAN",
                "description": "Explicitly click the current pointer location when no x/y target is given"
            },
            "keys": {
                "type": "STRING",
                "description": "Key combination e.g. 'ctrl+c'"
            },
            "key": {
                "type": "STRING",
                "description": "Single key e.g. 'enter'"
            },
            "direction": {
                "type": "STRING",
                "description": "up | down | left | right"
            },
            "amount": {
                "type": "INTEGER",
                "description": "Scroll amount (default: 3)"
            },
            "seconds": {
                "type": "NUMBER",
                "description": "Seconds to wait"
            },
            "title": {
                "type": "STRING",
                "description": "Window title for focus_window"
            },
            "description": {
                "type": "STRING",
                "description": "Element description for screen_find/screen_click"
            },
            "type": {
                "type": "STRING",
                "description": "Data type for random_data"
            },
            "field": {
                "type": "STRING",
                "description": "Field for user_data: name|email|city"
            },
            "clear_first": {
                "type": "BOOLEAN",
                "description": "Clear field before typing (default: true)"
            },
            "path": {
                "type": "STRING",
                "description": "Save path for screenshot"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": computer_control,
}
