from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main() -> int:
    from core.vault import set_secret

    name = input("Credential name [gemini_api_key]: ").strip() or "gemini_api_key"
    if not name.replace("_", "").isalnum():
        print("Credential names may contain letters, digits, and underscores only.")
        return 2
    value = getpass.getpass(f"Enter {name} (input hidden): ").strip()
    if not value:
        print("No credential entered; nothing saved.")
        return 2
    if not set_secret(name, value):
        print("Could not save credential to Windows Credential Manager/keyring.")
        return 1
    print("saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
