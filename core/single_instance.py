"""Windows named-mutex guard for the scheduled JARVIS launcher."""
from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

ERROR_ALREADY_EXISTS = 183


def run_with_named_mutex(
    name: str,
    run: Callable[[], int],
    *,
    api=None,
) -> int:
    """Run once while holding a Windows mutex; Windows releases it on a crash."""
    if api is None:
        if sys.platform != "win32" or not hasattr(ctypes, "WinDLL"):
            # Non-Windows fallback (e.g. tests or other platforms)
            try:
                import fcntl  # type: ignore
                lock_file = f"/tmp/{name.replace('\\', '_')}.lock"
                fp = open(lock_file, "w")
                try:
                    fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError):
                    return 0
                try:
                    res = run()
                    return 0 if res is None else int(res)
                finally:
                    try:
                        fcntl.flock(fp, fcntl.LOCK_UN)
                    except Exception:
                        pass
            except Exception:
                res = run()
                return 0 if res is None else int(res)

        api = ctypes.WinDLL("kernel32", use_last_error=True)

    create_mutex = api.CreateMutexW
    close_handle = api.CloseHandle
    release_mutex = api.ReleaseMutex
    if hasattr(create_mutex, "argtypes"):
        create_mutex.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        create_mutex.restype = ctypes.c_void_p
    if hasattr(close_handle, "argtypes"):
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_bool
    if hasattr(release_mutex, "argtypes"):
        release_mutex.argtypes = [ctypes.c_void_p]
        release_mutex.restype = ctypes.c_bool

    handle = create_mutex(None, True, name)
    last_error = getattr(api, "get_last_error", ctypes.get_last_error)()
    if not handle:
        raise ctypes.WinError(last_error)
    if last_error == ERROR_ALREADY_EXISTS:
        close_handle(handle)
        return 0

    try:
        res = run()
        return 0 if res is None else int(res)
    finally:
        try:
            release_mutex(handle)
        except Exception:
            pass
        try:
            close_handle(handle)
        except Exception:
            pass
