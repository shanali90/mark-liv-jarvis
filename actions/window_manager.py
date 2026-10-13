"""
MARK LIV Window Manager & Application Focus Controller.
Provides dedicated OS-level window enumeration and focus switching.
Reuses existing windows and tabs — never relaunches an application that is already open.
"""
from __future__ import annotations

import ctypes
import platform
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_OS = platform.system()

if _OS == "Windows":
    import win32gui
    import win32con


def _attach_input_desktop():
    """Ensure current thread can inspect windows on the active user desktop."""
    if _OS == "Windows":
        try:
            user32 = ctypes.windll.user32
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass


def list_open_windows() -> list[dict]:
    """Return a list of all visible top-level windows with title and HWND."""
    _attach_input_desktop()
    results = []

    if _OS == "Windows":
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    results.append({"hwnd": hwnd, "title": title})
            return True

        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception as e:
            print(f"[WindowManager] EnumWindows error: {e}")

    return results


def focus_window_by_hwnd(hwnd: int) -> bool:
    """Bring a specific window HWND to the foreground and unminimize if needed."""
    if _OS != "Windows":
        return False
    try:
        user32 = ctypes.windll.user32
        # If minimized, restore it
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        # Force foreground via Alt key trick if Windows blocks SetForegroundWindow
        user32.keybd_event(0x12, 0, 0, 0)  # Alt key down
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 2, 0)  # Alt key up
        return True
    except Exception as e:
        print(f"[WindowManager] Failed to focus HWND {hwnd:#x}: {e}")
        return False


def switch_to_window_internal(target_name: str) -> bool:
    """
    Search running windows for target_name (case-insensitive fuzzy match)
    and bring it to foreground. Returns True if found and focused.
    """
    if not target_name:
        return False

    target_clean = target_name.lower().strip()
    windows = list_open_windows()
    if not windows:
        return False

    # Exact or substring match
    best_hwnd = None
    best_title = None

    # Priority 1: App name in title (e.g. "whatsapp" in "(3) WhatsApp - Google Chrome")
    for w in windows:
        title_lower = w["title"].lower()
        if target_clean in title_lower:
            best_hwnd = w["hwnd"]
            best_title = w["title"]
            break

    # Priority 2: Word-boundary / token match
    if not best_hwnd:
        tokens = [t for t in re.split(r"\W+", target_clean) if len(t) > 2]
        for w in windows:
            title_lower = w["title"].lower()
            if any(t in title_lower for t in tokens):
                best_hwnd = w["hwnd"]
                best_title = w["title"]
                break

    if best_hwnd:
        # Clear any in-flight actions (e.g. WhatsApp draft) before switching
        try:
            from actions.send_message import abort_current_action
            abort_current_action()
        except Exception:
            pass

        ok = focus_window_by_hwnd(best_hwnd)
        if ok:
            print(f"[WindowManager] ✅ Focused existing window: '{best_title}' (HWND: {best_hwnd:#x})")
            return True

    return False


def switch_to_window(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Gemini tool handler for switching to an already-open window."""
    app_or_title = (parameters or {}).get("app_or_title", "").strip()
    if not app_or_title:
        return "No application name or window title provided."

    from core.voice_auth import is_guest_mode
    if is_guest_mode():
        return "Action restricted: Window switching is reserved exclusively for the owner."

    print(f"[WindowManager] Request to switch to: '{app_or_title}'")
    if player:
        player.write_log(f"[switch_to_window] {app_or_title}")

    if switch_to_window_internal(app_or_title):
        return f"Switched focus to {app_or_title}."

    return (
        f"Could not find an open window matching '{app_or_title}'. "
        f"You can ask me to open it if it is not currently running."
    )


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "switch_to_window",
    "description": (
        "Switches focus to an already-open window or application (e.g. 'WhatsApp', 'Chrome', 'Spotify', 'VSCode'). "
        "Use this tool when the user says 'switch to [app]', 'go back to [app]', or 'show me [app]'. "
        "DO NOT use open_app if the app is already open — use switch_to_window instead to avoid launching duplicates."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_or_title": {
                "type": "STRING",
                "description": "Name or title of the open application to focus (e.g. 'WhatsApp', 'Chrome', 'Notepad')"
            }
        },
        "required": [
            "app_or_title"
        ]
    },
    "handler": switch_to_window,
}
