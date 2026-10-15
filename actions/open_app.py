import json
import os
import re
import time
import webbrowser
import subprocess
import platform
import shutil

try:
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    # Fuzzy match, but only on whole words: a bare substring test made
    # "knowledge" match "edge" and "a" match everything.
    for alias_key, os_map in _APP_ALIASES.items():
        if re.search(rf"\b{re.escape(alias_key)}\b", key) or (
            len(key) >= 3 and re.search(rf"\b{re.escape(key)}\b", alias_key)
        ):
            return os_map.get(_SYSTEM, raw)

    return raw  

# URI schemes the assistant may open by name ("ms-settings:", "spotify:" ...).
# Anything else is refused: schemes such as ms-msdt: or file: can run code.
_SAFE_URI_SCHEMES = {
    "ms-settings", "ms-windows-store", "ms-clock", "ms-calculator", "msteams",
    "microsoft-edge", "spotify", "steam", "discord", "whatsapp", "tg",
    "slack", "zoom", "skype", "mailto",
}
_URI_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):[\w/.\-?=&%#@]*$")


# ── Smart target resolution: installed app first, then the website ───────────
# "Open WhatsApp" can mean the desktop app or web.whatsapp.com. The rule is:
# a URL/domain opens in the browser; a known service opens its installed app if
# the OS lists one, otherwise its website; anything else goes to the normal
# app launcher. Only http(s) is ever opened here.
_WEB_SERVICES: dict[str, str] = {
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "messenger": "https://www.messenger.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "google drive": "https://drive.google.com",
    "google maps": "https://maps.google.com",
    "google calendar": "https://calendar.google.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "tiktok": "https://www.tiktok.com",
    "reddit": "https://www.reddit.com",
    "snapchat": "https://web.snapchat.com",
    "pinterest": "https://www.pinterest.com",
    "telegram": "https://web.telegram.org",
    "discord": "https://discord.com/app",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "outlook": "https://outlook.live.com",
}
_NOT_A_TLD = {"exe", "bat", "cmd", "msc", "lnk", "ps1", "py", "dll", "sys", "msi", "vbs", "js"}
_DOMAIN_RE = re.compile(r"^(?:https?://)?((?:[a-z0-9\-]+\.)+([a-z]{2,24}))(?::\d{1,5})?(?:/[^\s]*)?$", re.I)
_APPID_RE = re.compile(r"^[A-Za-z0-9_.!{}\\\-() ]+$")


def _as_url(name: str) -> str | None:
    """Return an https URL if the spoken/typed name is a web address, else None."""
    t = re.sub(r"\s+dot\s+", ".", name.strip().lower())
    if re.search(r"\s", t):
        return None
    m = _DOMAIN_RE.match(t)
    if not m or m.group(2).lower() in _NOT_A_TLD:
        return None
    return t if t.startswith(("http://", "https://")) else "https://" + t


def _open_url(url: str) -> bool:
    """Open an http(s) URL in Chrome if present, else the default browser."""
    if not url.lower().startswith(("http://", "https://")):
        return False
    chrome = shutil.which("chrome") or shutil.which("google-chrome")
    if not chrome and _SYSTEM == "Windows":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"),
                     os.environ.get("LOCALAPPDATA")):
            cand = os.path.join(base or "", "Google", "Chrome", "Application", "chrome.exe")
            if base and os.path.exists(cand):
                chrome = cand
                break
    if chrome:
        try:
            subprocess.Popen([chrome, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[open_app] Chrome launch failed: {e}")
    try:
        return bool(webbrowser.open(url))
    except Exception as e:
        print(f"[open_app] browser open failed: {e}")
        return False


def _find_start_app(name: str) -> str | None:
    """Windows: AppID of an installed app whose Start-menu name matches, else None."""
    if _SYSTEM != "Windows":
        return None
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        apps = json.loads(r.stdout or "[]")
    except Exception:
        return None
    if isinstance(apps, dict):
        apps = [apps]
    want = name.strip().lower()
    exact = word = None
    for a in apps:
        n, appid = str(a.get("Name", "")).lower(), str(a.get("AppID", ""))
        if not appid or not _APPID_RE.match(appid):
            continue
        if n == want:
            exact = exact or appid
        elif re.search(rf"\b{re.escape(want)}\b", n):
            word = word or appid
    return exact or word


def _launch_start_app(appid: str) -> bool:
    try:
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{appid}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Start app launch failed: {e}")
        return False


def _resolve_and_open(app_name: str) -> str | None:
    """Open a web address or a known web service. None = not handled here."""
    url = _as_url(app_name)
    if url:
        return f"Opened {url} in the browser." if _open_url(url) else f"Could not open {url}."
    key = app_name.strip().lower()
    site = _WEB_SERVICES.get(key)
    if not site:
        return None
    appid = _find_start_app(app_name)
    if appid and _launch_start_app(appid):
        return f"Opened the {app_name} app."
    if _open_url(site):
        return f"{app_name} app is not installed, so I opened {site} in the browser."
    return f"Could not open {app_name}: no app found and the browser would not open."


def _launch_windows(app_name: str) -> bool:
    """Open an app on Windows WITHOUT passing the name through a shell.

    The name comes from the model, so it can carry text from a web page. With
    shell=True a name such as "calc.exe & del x" passed the PATH check (it only
    looked at the part before the first dot) and then ran as two commands.
    """
    exe = shutil.which(app_name)
    if exe:
        try:
            subprocess.Popen(
                [exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    m = _URI_RE.match(app_name)
    if m and m.group(1).lower() in _SAFE_URI_SCHEMES and hasattr(os, "startfile"):
        try:
            os.startfile(app_name)
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"[open_app] could not open {m.group(1)}: {e}")

    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str) -> bool:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    from core.voice_auth import is_guest_mode
    if is_guest_mode():
        return "Action restricted: Opening desktop applications is reserved exclusively for the owner."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)

    # ── Section 10 & 12: Generic app reuse — focus existing window if already open ──
    try:
        from actions.window_manager import switch_to_window_internal
        if switch_to_window_internal(app_name) or switch_to_window_internal(normalized):
            print(f"[open_app] found existing window for '{app_name}', focused")
            if player:
                player.write_log(f"[open_app] focused existing {app_name}")
            return f"Switched to existing open {app_name} window."
    except Exception as e:
        print(f"[open_app] Existing window check error: {e}")

    try:
        smart = _resolve_and_open(app_name)
    except Exception as e:
        print(f"[open_app] resolver error: {e}")
        smart = None
    if smart is not None:
        if player:
            player.write_log(f"[open_app] {smart}")
        return smart

    print(f"[open_app] no existing instance for '{app_name}', opening new ({_SYSTEM})")
    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": "Opens an application OR a website by name. Use it for 'open WhatsApp', 'open Instagram', 'open Facebook', 'open YouTube', 'open github.com', 'open Calculator', 'open Spotify'. For known services it opens the installed app if there is one, otherwise the website in Chrome; a domain such as 'example.com' opens in the browser. For web searches, reading a page, clicking or typing inside a site, use browser_control.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Name of the app or website (e.g. 'WhatsApp', 'Instagram', 'Calculator', 'github.com')"
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": open_app,
}
