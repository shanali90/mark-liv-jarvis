"""
MARK LIV Auto-Start Controller.
Gives the owner total manual control over when JARVIS starts and stops.
By default, auto-start is DISABLED. Only runs when explicitly requested.
"""
from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def disable_autostart() -> bool:
    """Remove JARVIS from Windows Registry Run key and Startup folder."""
    removed = False
    # 1. Registry HKCU Run
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_ALL_ACCESS,
        )
        try:
            winreg.DeleteValue(key, "JARVIS_AI")
            print("[AutoStart] ✅ Successfully removed 'JARVIS_AI' from Windows Registry CurrentVersion\\Run.")
            removed = True
        except FileNotFoundError:
            print("[AutoStart] 'JARVIS_AI' not present in Windows Registry CurrentVersion\\Run.")
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        print(f"[AutoStart] Registry access error: {e}")

    # 2. Windows Startup folder check
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if startup_dir.is_dir():
            for f in startup_dir.glob("*jarvis*"):
                try:
                    f.unlink()
                    print(f"[AutoStart] ✅ Removed startup shortcut: {f.name}")
                    removed = True
                except Exception as e:
                    print(f"[AutoStart] Could not remove {f.name}: {e}")

    return removed


def enable_autostart() -> bool:
    """Explicit opt-in: register JARVIS to launch on boot silently."""
    script = str(Path(__file__).resolve().parent / "main.py")
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    exe = str(pythonw if pythonw.exists() else sys.executable)

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_ALL_ACCESS,
        )
        winreg.SetValueEx(key, "JARVIS_AI", 0, winreg.REG_SZ, f'"{exe}" "{script}"')
        winreg.CloseKey(key)
        print("[AutoStart] ✅ Auto-start enabled in Windows Registry under CurrentVersion\\Run.")
        return True
    except Exception as e:
        print(f"[AutoStart] ❌ Failed to enable auto-start: {e}")
        return False


def status_autostart() -> bool:
    """Check whether auto-start is registered."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            val, _ = winreg.QueryValueEx(key, "JARVIS_AI")
            print(f"[AutoStart] Auto-start is currently ACTIVE: {val}")
            return True
        except FileNotFoundError:
            print("[AutoStart] Auto-start is currently DISABLED (clean).")
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        print(f"[AutoStart] Could not read registry: {e}")
        return False


if __name__ == "__main__":
    if "--enable" in sys.argv:
        enable_autostart()
    elif "--status" in sys.argv:
        status_autostart()
    else:
        # Default action is always DISABLE to guarantee the owner's full manual control
        disable_autostart()
