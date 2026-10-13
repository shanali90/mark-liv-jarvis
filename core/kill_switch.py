import ctypes
import ctypes.wintypes
import logging
import multiprocessing
import os
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

class KillSwitch:
    def __init__(self):
        self._active_processes = []
        self._hotkey_thread = None
        self._sentinel_thread = None
        self._running = False
        
    def run_task(self, target: Callable, args: tuple = ()) -> multiprocessing.Process:
        """Runs a task in a separate process so it can be force-killed."""
        p = multiprocessing.Process(target=target, args=args, daemon=True)
        p.start()
        self._active_processes.append(p)
        return p
        
    def trigger(self):
        """Triggers the kill switch, force-killing all active tasks."""
        logger.warning("KILL SWITCH TRIGGERED!")
        for p in self._active_processes:
            if p.is_alive():
                logger.warning(f"Force killing process {p.pid}")
                p.terminate()
                p.join(timeout=2.0)
                if p.is_alive():
                    p.kill() # Hard kill
        self._active_processes = [p for p in self._active_processes if p.is_alive()]

    def start_listeners(self):
        if self._running:
            return
        self._running = True
        self._hotkey_thread = threading.Thread(target=self._win32_hotkey_loop, daemon=True)
        self._hotkey_thread.start()
        
        self._sentinel_thread = threading.Thread(target=self._sentinel_loop, daemon=True)
        self._sentinel_thread.start()

    def _sentinel_loop(self):
        """Monitors a sentinel file created by kill.py"""
        sentinel_path = os.path.join(os.path.dirname(__file__), '..', '.kill_sentinel')
        while self._running:
            if os.path.exists(sentinel_path):
                self.trigger()
                try:
                    os.remove(sentinel_path)
                except Exception:
                    pass
            time.sleep(0.2)

    def _win32_hotkey_loop(self):
        user32 = ctypes.windll.user32
        # Constants
        MOD_ALT = 0x0001
        MOD_CTRL = 0x0002
        MOD_SHIFT = 0x0004
        WM_HOTKEY = 0x0312
        
        # Ctrl + Alt + Shift + K
        HOTKEY_ID = 1
        VK_K = 0x4B
        
        modifiers = MOD_CTRL | MOD_ALT | MOD_SHIFT
        
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, VK_K):
            logger.error("Failed to register kill-switch hotkey")
            return
            
        logger.info("Kill-switch hotkey registered (Ctrl+Alt+Shift+K)")
        
        msg = ctypes.wintypes.MSG()
        while self._running:
            # PeekMessage allows us to not block forever so we can exit cleanly
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1): # PM_REMOVE = 1
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.trigger()
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.05)
                
        user32.UnregisterHotKey(None, HOTKEY_ID)

kill_switch = KillSwitch()
