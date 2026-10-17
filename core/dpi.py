"""Process-wide DPI-awareness setup for Windows desktop coordinate APIs."""
from __future__ import annotations

import platform


_attempted = False


def set_process_dpi_awareness() -> None:
    global _attempted
    if _attempted:
        return
    _attempted = True
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        pass
