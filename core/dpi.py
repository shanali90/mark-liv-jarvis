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

        shcore = ctypes.windll.shcore
        awareness = ctypes.c_int()
        result = shcore.GetProcessDpiAwareness(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(awareness),
        )
        result = int(result) & 0xFFFFFFFF
        if result == 0 and awareness.value == 2:
            return
        if result != 0:
            raise OSError(f"GetProcessDpiAwareness failed with HRESULT {result:#x}")

        result = int(shcore.SetProcessDpiAwareness(2)) & 0xFFFFFFFF
        if result not in (0, 0x80070005):
            raise OSError(f"SetProcessDpiAwareness failed with HRESULT {result:#x}")
    except (AttributeError, OSError) as exc:
        print(f"[DPI] Could not set process DPI awareness: {exc}")
