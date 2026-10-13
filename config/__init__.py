# config/__init__.py
import json
import platform
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "settings.json"

def _platform_os() -> str:
    """Auto-detect OS when config file is absent."""
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def get_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        return {}
    _remove_secrets(config)
    return config

def _remove_secrets(data: dict) -> None:
    for key in list(data):
        value = data[key]
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            del data[key]
        elif isinstance(value, dict):
            _remove_secrets(value)

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    return get_config().get("os_system", _platform_os()).lower()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
