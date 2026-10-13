import ctypes
import enum
import logging
import threading
import time

logger = logging.getLogger(__name__)

class SafetyLevel(enum.Enum):
    GREEN = "GREEN"     # Read-only, run freely
    YELLOW = "YELLOW"   # Reversible, logged
    RED = "RED"         # Requires explicit approval

class ApprovalQueue:
    def __init__(self, timeout_secs: int = 600):
        self.timeout_secs = timeout_secs
        
    def request_approval(self, action_name: str, details: str, short_timeout: int | None = None) -> bool:
        """
        Request approval via Windows desktop prompt (Phase 1-4).
        Blocks until approved, denied, or timeout.
        """
        timeout = short_timeout if short_timeout is not None else self.timeout_secs
        logger.info(f"Requesting RED approval for: {action_name}")
        
        # We will use ctypes MessageBox with a timeout loop
        # MessageBoxW blocks, so we run it in a thread and wait with timeout
        
        MB_YESNO = 0x04
        MB_ICONWARNING = 0x30
        IDYES = 6
        
        result_container = [None]
        
        def show_msgbox():
            msg = f"JARVIS Action Requires Approval:\n\nAction: {action_name}\nDetails: {details}\n\nApprove?"
            # Using MB_YESNO | MB_ICONWARNING | MB_SYSTEMMODAL (0x1000)
            res = ctypes.windll.user32.MessageBoxW(0, msg, "Jarvis Approval Request", MB_YESNO | MB_ICONWARNING | 0x1000)
            result_container[0] = (res == IDYES)
            
        t = threading.Thread(target=show_msgbox, daemon=True)
        t.start()
        
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if result_container[0] is not None:
                approved = result_container[0]
                logger.info(f"Approval for {action_name}: {'GRANTED' if approved else 'DENIED'}")
                return approved
            time.sleep(0.5)
            
        logger.warning(f"Approval for {action_name} timed out after {timeout}s.")
        # If timeout, we cannot close the MessageBox cleanly from Python without sending messages, 
        # but it will remain. We just return False.
        return False

# Global instance
approval_queue = ApprovalQueue()
