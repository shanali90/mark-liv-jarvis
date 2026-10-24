"""Where the user's real Desktop / Downloads / Documents / Videos are.

On Windows the Desktop is very often NOT C:\\Users\\<name>\\Desktop: with OneDrive
backup it lives in C:\\Users\\<name>\\OneDrive\\Desktop (or another language's folder
name). Using Path.home()/"Desktop" then writes into a folder the user never sees,
while JARVIS happily reports "Folder created". Ask Windows where the folder is.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows Known Folder IDs
_FOLDERID = {
    "desktop":   "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "videos":    "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
    "pictures":  "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}
_FALLBACK = {"desktop": "Desktop", "downloads": "Downloads", "documents": "Documents",
             "videos": "Videos", "pictures": "Pictures"}


def _windows_known_folder(name: str) -> Path | None:
    try:
        import ctypes
        from ctypes import wintypes
        import uuid

        guid = uuid.UUID(_FOLDERID[name])

        class _GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD),
                        ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

        g = _GUID(guid.time_low, guid.time_mid, guid.time_hi_version,
                  (ctypes.c_ubyte * 8)(*guid.bytes[8:]))
        out = ctypes.c_wchar_p()
        res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out))
        if res != 0 or not out.value:
            return None
        path = Path(out.value)
        ctypes.windll.ole32.CoTaskMemFree(out)
        return path
    except Exception:
        return None


def user_folder(name: str) -> Path:
    """Real location of a standard user folder; never raises."""
    name = name.lower()
    if sys.platform == "win32":
        found = _windows_known_folder(name)
        if found is not None and found.exists():
            return found
        one = os.environ.get("OneDrive")
        if one and (Path(one) / _FALLBACK[name]).exists():
            return Path(one) / _FALLBACK[name]
    return Path.home() / _FALLBACK[name]


def desktop() -> Path:
    return user_folder("desktop")
