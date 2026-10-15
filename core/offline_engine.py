"""
MARK LIV Offline Fallback Engine (Section 11).
Handles fixed local system commands when internet connection is lost.
Does not guess or hallucinate on out-of-scope queries.
Provides offline vocal feedback via Windows native SAPI SpVoice.
"""
from __future__ import annotations

import ctypes
import platform
import re
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "config" / "offline_commands.log"
_OS = platform.system()

# Windows Virtual-Key Codes for Multimedia
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF


def is_online(timeout: float = 2.0) -> bool:
    """Lightweight, fast check to verify internet connectivity to reliable DNS hosts."""
    endpoints = [("8.8.8.8", 53), ("1.1.1.1", 53)]
    for host, port in endpoints:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            continue
    return False




_PHONETIC_MAP = {
    "اسلام عليڪم سائين شان علي! جي سائين، مان حاضر آهيان.": "Assalam-o-alaikum Sain the owner! Jee Sain, I am online and listening.",
    "اسلام عليڪم سائين شان علي! جي سائين، مان حاضر آهيان": "Assalam-o-alaikum Sain the owner! Jee Sain, I am online and listening.",
    "الله واهي سائين شان علي.": "Allah wahi Sain the owner.",
    "الله واهي سائين شان علي": "Allah wahi Sain the owner.",
    "جي سائين شان علي، سسٽم مڪمل طور ٺيڪ آهي.": "Jee Sain the owner, system is operating normally.",
    "سائين جاڳو": "Sain, I am awake.",
    "اسلام عليڪم سائين شان علي": "Assalam-o-alaikum Sain the owner!",
    "اسلام عليڪم": "Assalam-o-alaikum!",
}


def _clean_for_sapi(text: str) -> str:
    """Translate or clean Arabic/Sindhi script so Windows SAPI Desktop voices can speak audibly."""
    if not text:
        return ""
    clean = text.strip()
    if clean in _PHONETIC_MAP:
        return _PHONETIC_MAP[clean]
    
    # Check if text contains bilingual explanation in parentheses (English + Sindhi)
    # SAPI handles English perfectly but chokes on Arabic script
    if "(" in clean and ")" in clean:
        english_part = re.sub(r"\(.*?\)", "", clean).strip()
        if english_part and any(c.isascii() and c.isalpha() for c in english_part):
            return english_part

    # If mostly Arabic/Sindhi script, substitute phonetic greetings
    has_arabic = any("\u0600" <= c <= "\u06ff" for c in clean)
    if has_arabic:
        t = clean
        t = t.replace("اسلام عليڪم", "Assalam-o-alaikum")
        t = t.replace("سائين شان علي", "Sain the owner")
        t = t.replace("سائين", "Sain")
        t = t.replace("جي سائين", "Jee Sain")
        t = t.replace("حاضر آهيان", "I am here")
        t = t.replace("الله واهي", "Allah wahi")
        # Strip any remaining unpronounceable Arabic characters
        t = re.sub(r"[\u0600-\u06ff]", "", t).strip()
        if not t or not any(c.isalnum() for c in t):
            return "Yes Sain the owner, I am listening."
        return t

    return clean


def speak_offline(text: str) -> None:
    """Speak using Windows SAPI SpVoice without requiring any internet connection.
    Automatically phonetically adapts Sindhi/Urdu text so English SAPI voices speak out loud.
    """
    if _OS != "Windows":
        return

    spoken_text = _clean_for_sapi(text)
    if not spoken_text:
        return

    def _worker():
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            voice.Speak(spoken_text)
            pythoncom.CoUninitialize()
        except Exception as e:
            print(f"[OfflineEngine] SAPI speech error: {e}")

    threading.Thread(target=_worker, daemon=True, name="OfflineTTS").start()


def _log_offline_action(command: str, action: str, result: str):
    """Log every offline action executed with an exact timestamp."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat()
        entry = f"[{ts}] CMD: '{command}' | ACTION: {action} | RESULT: {result}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[OfflineEngine] 📝 {entry.strip()}")
    except Exception as e:
        print(f"[OfflineEngine] Logging failed: {e}")


def _press_key(vk_code: int, times: int = 1):
    if _OS == "Windows":
        user32 = ctypes.windll.user32
        for _ in range(times):
            user32.keybd_event(vk_code, 0, 0, 0)
            user32.keybd_event(vk_code, 0, 2, 0)
            time.sleep(0.05)


# Processes that must never be closed by a spoken "close ..." command: closing
# them logs the user out, blanks the desktop, or kills JARVIS itself.
_PROTECTED_PROCESSES = frozenset({
    "explorer", "winlogon", "csrss", "wininit", "services", "lsass", "svchost",
    "system", "smss", "dwm", "taskmgr", "python", "pythonw", "py", "cmd",
    "powershell", "pwsh", "conhost", "windowsterminal", "code",
})


def _close_app(target: str) -> tuple[bool, str]:
    """Close an app by name. Returns (closed, spoken reply).

    The name comes from speech, so it is never put in a shell string: it is
    reduced to one safe executable name and passed to taskkill as an argument.
    The reply reports what taskkill actually did instead of always saying
    "Closed".
    """
    import subprocess

    name = re.sub(r"\s+", "", str(target or "")).strip("-")
    if name.lower().endswith(".exe"):
        name = name[:-4]
    if not name or not re.fullmatch(r"[A-Za-z0-9_]+", name):
        return False, f"I can't tell which app to close from '{target}'."
    if name.lower() in _PROTECTED_PROCESSES:
        return False, f"I won't close {name}: it is a system or JARVIS process."
    try:
        r = subprocess.run(
            ["taskkill", "/f", "/im", f"{name}.exe"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Could not close {name}: {e}"
    if r.returncode == 0:
        return True, f"Closed {name}."
    return False, f"{name} is not running, or I could not close it."


def handle_offline_command(text: str, ui=None) -> tuple[bool, str]:
    """
    Parses and executes a command from the strict closed offline command set.
    Returns (handled: bool, spoken_response: str).
    """
    clean = text.lower().strip()
    if not clean:
        return False, ""

    # Check for speaker restriction
    from core.voice_auth import is_guest_mode
    restricted = is_guest_mode()

    # 1. TIME / DATE INQUIRY
    if any(k in clean for k in (
        "what time is it", "what's the time", "current time", "what time",
        "tell me the time", "وقت", "ڇا وقت", "ٽائيم"
    )):
        now = datetime.now()
        reply = f"The time is {now.strftime('%I:%M %p')}."
        _log_offline_action(text, "TIME_QUERY", reply)
        return True, reply

    if any(k in clean for k in ("what date is it", "today's date", "what is the date", "تاريخ")):
        now = datetime.now()
        reply = f"Today is {now.strftime('%A, %B %d, %Y')}."
        _log_offline_action(text, "DATE_QUERY", reply)
        return True, reply

    # 2. VOLUME CONTROL
    if any(k in clean for k in ("volume up", "increase volume", "louder", "turn up the volume", "آواز وڌايو")):
        _press_key(VK_VOLUME_UP, times=5)
        reply = "Volume increased."
        _log_offline_action(text, "VOLUME_UP", reply)
        return True, reply

    if any(k in clean for k in ("volume down", "decrease volume", "lower volume", "quieter", "turn down the volume", "آواز گھٽايو")):
        _press_key(VK_VOLUME_DOWN, times=5)
        reply = "Volume decreased."
        _log_offline_action(text, "VOLUME_DOWN", reply)
        return True, reply

    if any(k in clean for k in ("mute volume", "mute audio", "unmute", "خاموش")):
        _press_key(VK_VOLUME_MUTE, times=1)
        reply = "Volume muted or unmuted."
        _log_offline_action(text, "VOLUME_MUTE", reply)
        return True, reply

    # 3. SCREEN LOCK
    if any(k in clean for k in ("lock screen", "lock the screen", "lock computer", "اسڪرين لاڪ")):
        if restricted:
            reply = "Action restricted: Locking the computer is reserved for the owner."
            _log_offline_action(text, "LOCK_SCREEN_DENIED", reply)
            return True, reply
        if _OS == "Windows":
            ctypes.windll.user32.LockWorkStation()
            reply = "Locking workstation."
            _log_offline_action(text, "LOCK_SCREEN", reply)
            return True, reply

    # 4. SCREENSHOT
    if any(k in clean for k in ("take a screenshot", "screenshot", "screen capture", "اسڪرين شاٽ")):
        try:
            import pyautogui
            pics_dir = Path.home() / "Pictures" / "Screenshots"
            pics_dir.mkdir(parents=True, exist_ok=True)
            out_file = pics_dir / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            shot = pyautogui.screenshot()
            shot.save(str(out_file))
            reply = "Screenshot captured and saved to Pictures."
            _log_offline_action(text, "SCREENSHOT", f"Saved to {out_file}")
            return True, reply
        except Exception as e:
            reply = f"Failed to capture screenshot: {e}"
            _log_offline_action(text, "SCREENSHOT_ERROR", str(e))
            return True, reply

    # 5. SWITCH TO WINDOW / APP
    match_switch = re.search(r"(?:switch to|go to|show me|bring up|ڏيکاريو)\s+([a-zA-Z0-9_\-\s]+)", clean)
    if match_switch:
        target = match_switch.group(1).strip()
        if restricted:
            reply = "Action restricted: Window switching is reserved for the owner."
            _log_offline_action(text, "SWITCH_WINDOW_DENIED", reply)
            return True, reply

        from actions.window_manager import switch_to_window_internal
        if switch_to_window_internal(target):
            reply = f"Switched to {target}."
            _log_offline_action(text, "SWITCH_WINDOW", reply)
            return True, reply
        else:
            reply = f"Could not find an open window matching {target}."
            _log_offline_action(text, "SWITCH_WINDOW_MISSING", reply)
            return True, reply

    # 6. OPEN APP
    match_open = re.search(r"(?:open|launch|start|کوليو)\s+([a-zA-Z0-9_\-\s]+)", clean)
    if match_open:
        target = match_open.group(1).strip()
        if restricted:
            reply = "Action restricted: Launching applications is reserved for the owner."
            _log_offline_action(text, "OPEN_APP_DENIED", reply)
            return True, reply

        from actions.open_app import open_app
        res = open_app({"app_name": target})
        reply = f"Handled offline: {res}"
        _log_offline_action(text, "OPEN_APP", reply)
        return True, reply

    # 7. CLOSE APP
    match_close = re.search(r"(?:close|terminate|kill|بند ڪريو)\s+([a-zA-Z0-9_\-\s]+)", clean)
    if match_close:
        target = match_close.group(1).strip()
        if restricted:
            reply = "Action restricted: Closing applications is reserved for the owner."
            _log_offline_action(text, "CLOSE_APP_DENIED", reply)
            return True, reply

        try:
            ok, reply = _close_app(target)
            _log_offline_action(text, "CLOSE_APP" if ok else "CLOSE_APP_FAILED", reply)
            return True, reply
        except Exception as e:
            reply = f"Could not close {target}: {e}"
            _log_offline_action(text, "CLOSE_APP_ERROR", str(e))
            return True, reply

    # 8. OUT OF SCOPE — CLEAR REFUSAL WITHOUT GUESSING (as mandated by Section 11)
    reply = (
        "I can't do that offline, I'll handle it once we're back online. "
        "(آءٌ اهو ڪم آف لائين نٿو ڪري سگهان، انٽرنيٽ بحال ٿيڻ تي اهو ڪم ڪندس.)"
    )
    _log_offline_action(text, "OFFLINE_DECLINED", "Out of closed command set")
    return True, reply
