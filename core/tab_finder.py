"""Find and focus an already-open Chrome tab without interacting with page content."""
from __future__ import annotations

import platform
import time
from urllib.parse import urlsplit


_SERVICES: dict[str, tuple[str, ...]] = {
    "whatsapp": ("whatsapp",),
    "instagram": ("instagram",),
    "facebook": ("facebook",),
    "youtube": ("youtube",),
    "gmail": ("gmail", "google mail", "mail.google.com"),
}
_SERVICE_LABELS = {
    "whatsapp": "WhatsApp",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "youtube": "YouTube",
    "gmail": "Gmail",
}


def service_name(url_or_service: str) -> str:
    raw = (url_or_service or "").strip()
    key = raw.casefold()
    if key in _SERVICES:
        return _SERVICE_LABELS[key]
    if key in {"chrome", "google chrome"}:
        return "Chrome"
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").removeprefix("www.")
    for name, keywords in _SERVICES.items():
        if any(keyword in host.casefold() for keyword in keywords):
            return _SERVICE_LABELS[name]
    label = host.split(".", 1)[0] if host else raw
    return label.replace("-", " ").title() or "Chrome"


def _match_keywords(url_or_service: str) -> tuple[str, ...]:
    raw = (url_or_service or "").strip()
    key = raw.casefold()
    if key in _SERVICES:
        return _SERVICES[key]
    if key in {"chrome", "google chrome"} or not raw:
        return ("google chrome", "chrome")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (parsed.hostname or "").removeprefix("www.").casefold()
    for keywords in _SERVICES.values():
        if any(keyword in host for keyword in keywords):
            return keywords
    if host:
        return host, host.split(".", 1)[0]
    return (raw.casefold(),)


def _chrome_windows() -> list:
    try:
        import pygetwindow
        import win32gui
    except ImportError as exc:
        print(f"[TabFinder] Chrome tab lookup unavailable: {exc}")
        return []

    windows = []
    for window in pygetwindow.getAllWindows():
        hwnd = getattr(window, "_hWnd", None)
        if hwnd and win32gui.GetClassName(hwnd) == "Chrome_WidgetWin_1":
            windows.append(window)
    return windows


def _window_title(window) -> str:
    import win32gui

    return win32gui.GetWindowText(window._hWnd)


def _focus_window(window) -> bool:
    try:
        if window.isMinimized:
            window.restore()
        window.activate()
        return True
    except Exception as exc:
        print(f"[TabFinder] Could not focus Chrome window: {exc}")
        return False


def _advance_tab() -> None:
    import pyautogui

    pyautogui.hotkey("ctrl", "tab")
    time.sleep(0.15)


def find_and_focus_existing(url_or_service: str) -> bool:
    """Focus an existing matching Chrome tab; never type or click in a page."""
    if platform.system() != "Windows":
        return False

    keywords = _match_keywords(url_or_service)
    for window in _chrome_windows():
        if not _focus_window(window):
            continue
        first_title = _window_title(window)
        title = first_title
        for attempt in range(31):
            lowered = title.casefold()
            if any(keyword in lowered for keyword in keywords):
                return _focus_window(window)
            if attempt == 30 or (attempt > 0 and title == first_title):
                break
            _advance_tab()
            title = _window_title(window)
    return False
