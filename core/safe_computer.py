import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SafeComputer:
    """Wrapper around PyAutoGUI that enforces safety limits."""
    
    def __init__(self):
        try:
            import pyautogui
            # Failsafe: moving mouse to any corner of the screen throws pyautogui.FailSafeException
            pyautogui.FAILSAFE = True
            # Add a slight pause after every PyAutoGUI call for safety and interruptibility
            pyautogui.PAUSE = 0.5
            self.p = pyautogui
        except ImportError:
            self.p = None
            logger.warning("pyautogui not installed. SafeComputer will run in dummy mode.")

    def _check(self):
        if not self.p:
            raise RuntimeError("pyautogui is not installed.")

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1):
        self._check()
        try:
            self.p.click(x=x, y=y, button=button, clicks=clicks)
        except self.p.FailSafeException:
            logger.error("Safety Halt triggered during click! Mouse was moved to a corner.")
            raise PermissionError("Safety Halt triggered: Mouse reached screen corner.")

    def move(self, x: int, y: int, duration: float = 0.3):
        self._check()
        try:
            self.p.moveTo(x, y, duration)
        except self.p.FailSafeException:
            logger.error("Safety Halt triggered during move!")
            raise PermissionError("Safety Halt triggered.")

    def type_text(self, text: str, interval: float = 0.05):
        self._check()
        try:
            self.p.write(text, interval=interval)
        except self.p.FailSafeException:
            logger.error("Safety Halt triggered during typing!")
            raise PermissionError("Safety Halt triggered.")

    def press(self, key: str):
        self._check()
        try:
            self.p.press(key)
        except self.p.FailSafeException:
            logger.error("Safety Halt triggered during key press!")
            raise PermissionError("Safety Halt triggered.")

    def hotkey(self, *keys):
        self._check()
        try:
            self.p.hotkey(*keys)
        except self.p.FailSafeException:
            logger.error("Safety Halt triggered during hotkey!")
            raise PermissionError("Safety Halt triggered.")
            
safe_computer = SafeComputer()
