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
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        awareness = ctypes.c_int()
        get_process_awareness = shcore.GetProcessDpiAwareness
        get_process_awareness.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int),
        ]
        get_process_awareness.restype = ctypes.c_long
        result = get_process_awareness(
            get_current_process(), ctypes.byref(awareness)
        )
        result = int(result) & 0xFFFFFFFF
        if result == 0 and awareness.value == 2:
            return
        if result != 0:
            raise OSError(f"GetProcessDpiAwareness failed with HRESULT {result:#x}")

        set_process_awareness = shcore.SetProcessDpiAwareness
        set_process_awareness.argtypes = [ctypes.c_int]
        set_process_awareness.restype = ctypes.c_long
        result = int(set_process_awareness(2)) & 0xFFFFFFFF
        if result not in (0, 0x80070005):
            raise OSError(f"SetProcessDpiAwareness failed with HRESULT {result:#x}")
    except (AttributeError, OSError) as exc:
        print(f"[DPI] Could not set process DPI awareness: {exc}")
