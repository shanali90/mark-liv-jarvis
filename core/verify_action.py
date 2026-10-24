"""core/verify_action.py - verify real results before reporting to user and model.

Standard result format:
  DONE: <what> (checked: <how>)          - verified
  NOT DONE: <what> - <plain reason>      - failed or could not verify
  UNSURE: <what> - I could not confirm it
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional, Set, List


def verify_path_exists(path: Path | str, what: str = "folder") -> tuple[bool, str, Path]:
    """Verify that a created file or folder exists on disk."""
    p = Path(path).resolve()
    if p.exists():
        return True, f"DONE: created {what} '{p}' (checked: path exists)", p
    return False, f"NOT DONE: create {what} - '{p}' does not exist", p


def verify_file_deleted(path: Path | str) -> tuple[bool, str]:
    """Verify that a file has been removed or sent to trash."""
    p = Path(path).resolve()
    if not p.exists():
        return True, f"DONE: deleted '{p.name}' (checked: file removed)",
    return False, f"NOT DONE: delete '{p.name}' - file still exists"


def verify_file_moved(src: Path | str, dst: Path | str) -> tuple[bool, str]:
    """Verify that a file move succeeded."""
    s = Path(src).resolve()
    d = Path(dst).resolve()
    if d.exists() and (not s.exists() or s != d):
        return True, f"DONE: moved '{s.name}' to '{d.parent.name}/' (checked: destination exists)"
    if not d.exists():
        return False, f"NOT DONE: move '{s.name}' - destination '{d}' does not exist"
    return False, f"NOT DONE: move '{s.name}' - source file still exists at original path"


def get_current_window_titles() -> list[str]:
    """Return all non-empty window titles."""
    try:
        import pygetwindow as gw
        return [w.title for w in gw.getAllWindows() if w.title and w.title.strip()]
    except Exception:
        return []


def get_current_process_names() -> set[str]:
    """Return lowercase names of all currently running processes."""
    try:
        import psutil
        names = set()
        for p in psutil.process_iter(['name']):
            try:
                n = p.name()
                if n:
                    names.add(n.lower())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return names
    except Exception:
        return set()


def bring_window_to_front(title_keyword: str) -> bool:
    """Activate and restore a window matching the keyword."""
    try:
        import pygetwindow as gw
        low = title_keyword.lower()
        for w in gw.getAllWindows():
            if w.title and low in w.title.lower():
                try:
                    if w.isMinimized:
                        w.restore()
                    w.activate()
                    return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


def verify_app_opened(
    app_name: str,
    before_processes: Optional[Set[str]] = None,
    before_windows: Optional[List[str]] = None,
    timeout: float = 5.0,
    check_already_open: bool = True,
) -> tuple[bool, str]:
    """Check if app/file was already open (bring to front) or opened within timeout."""
    norm = app_name.strip()
    norm_low = norm.lower()
    # Normalize common extensions
    base_low = norm_low.removesuffix(".exe")

    # 1. Check if already open
    if check_already_open:
        current_titles = get_current_window_titles()
        for t in current_titles:
            if base_low in t.lower():
                if bring_window_to_front(base_low):
                    return True, f"DONE: {norm} was already open, brought to front (checked: window focused)"
                return True, f"DONE: {norm} is already open (checked: window '{t}' active)"

    # 2. Wait up to timeout for window or process to appear
    end = time.monotonic() + timeout
    initial_pids = before_processes or set()
    initial_titles = set(before_windows or [])

    while time.monotonic() < end:
        current_titles = get_current_window_titles()
        for t in current_titles:
            if t not in initial_titles and base_low in t.lower():
                return True, f"DONE: opened {norm} (checked: window '{t}' appeared)"

        current_procs = get_current_process_names()
        new_procs = current_procs - initial_pids
        for p in new_procs:
            if base_low in p:
                return True, f"DONE: opened {norm} (checked: process '{p}' started)"

        time.sleep(0.3)

    return False, f"NOT DONE: open {norm} - no window or process appeared after {int(timeout)} s"


def verify_website_opened(
    url_or_site: str,
    timeout: float = 8.0,
    check_already_open: bool = True,
) -> tuple[bool, str]:
    """Check if site tab was already open or if a matching browser window appears."""
    from core.tab_finder import find_and_focus_existing, service_name

    label = service_name(url_or_site)
    kw = label.lower()

    # 1. Check already-open tab via tab_finder
    if check_already_open:
        try:
            if find_and_focus_existing(url_or_site):
                return True, f"DONE: switched to your open {label} tab (checked: tab focused)"
        except Exception:
            pass

    # 2. Poll for browser window matching site keywords
    end = time.monotonic() + timeout
    net_err_keywords = (
        "can't reach", "can’t reach", "err_", "no internet",
        "server not found", "problem loading page", "dns_probe",
        "internet may be down"
    )

    while time.monotonic() < end:
        current_titles = get_current_window_titles()
        for t in current_titles:
            t_low = t.lower()
            # If a browser window with this site name exists, inspect it for errors
            if kw in t_low or "chrome" in t_low or "edge" in t_low or "browser" in t_low:
                if any(err in t_low for err in net_err_keywords):
                    return False, f"NOT DONE: {label} did not open - your internet may be down"
                if kw in t_low:
                    return True, f"DONE: opened {label} (checked: browser window '{t}' appeared)"
        time.sleep(0.4)

    return False, f"NOT DONE: {label} did not open - browser window did not appear after {int(timeout)} s"


def verify_setting_changed(
    setting_name: str,
    target_val: Optional[int] = None,
    get_func: Optional[Callable[[], Optional[int]]] = None,
    before_val: Optional[int] = None,
) -> tuple[bool, str]:
    """Verify system setting changed by reading back its value."""
    if get_func is None:
        return False, f"UNSURE: {setting_name} changed - I could not confirm it"

    try:
        after_val = get_func()
    except Exception:
        after_val = None

    if after_val is None:
        return False, f"UNSURE: {setting_name} changed - I could not confirm it"

    if target_val is not None:
        if abs(after_val - target_val) <= 2:
            return True, f"DONE: {setting_name} set to {after_val}% (checked: current {setting_name} is {after_val}%)"
        return False, f"NOT DONE: {setting_name} change - current {setting_name} is {after_val}%, expected {target_val}%"

    if before_val is not None:
        if after_val != before_val:
            return True, f"DONE: {setting_name} adjusted to {after_val}% (checked: changed from {before_val}% to {after_val}%)"
        return False, f"NOT DONE: {setting_name} change - {setting_name} remained at {after_val}%"

    return True, f"DONE: {setting_name} is {after_val}% (checked: read back value {after_val}%)"
