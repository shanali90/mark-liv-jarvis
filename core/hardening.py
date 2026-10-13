import os
import platform
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def check_system_security() -> dict:
    """Phase 8-10 Hardening Check"""
    issues = []
    
    # Check OS
    if platform.system() == "Windows":
        # Check if running as admin (generally discouraged for AI)
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            issues.append("WARNING: Running as Administrator. Sandboxing is reduced.")
            
    # Check pre-commit hook
    base_dir = Path(__file__).resolve().parent.parent
    hook_path = base_dir / "scripts" / "hooks" / "pre-commit"
    if not hook_path.exists():
        issues.append("ERROR: Pre-commit hook missing.")
        
    # Check venv
    if "VIRTUAL_ENV" not in os.environ and sys.prefix == sys.base_prefix:
         issues.append("WARNING: Not running inside a virtual environment.")
         
    return {
        "status": "SECURE" if not issues else "VULNERABLE",
        "issues": issues
    }

if __name__ == "__main__":
    import sys
    res = check_system_security()
    for i in res["issues"]:
        print(i)
    if res["issues"]:
        sys.exit(1)
    print("System Hardened.")
