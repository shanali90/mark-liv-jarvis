import json
from dataclasses import dataclass, fields
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "settings.json"

@dataclass
class AppConfig:
    os_system: str
    assistant_name: str
    voice_name: str
    wake_word_enabled: bool
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    llm_provider: str = "ollama"
    llm_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"

def validate_config() -> AppConfig:
    """Validates the config file against the AppConfig schema."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
        
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    from core.vault import get_secret

    _remove_secret_fields(data)
    data["gemini_api_key"] = get_secret("gemini_api_key") or None
    data["openai_api_key"] = get_secret("openai_api_key") or None

    valid_fields = {f.name for f in fields(AppConfig)}
    filtered_data = {k: v for k, v in data.items() if k in valid_fields}
    
    # Simple required fields check based on the default dataclass definition
    config = AppConfig(**filtered_data)
    
    if config.os_system not in ["windows", "mac", "linux"]:
        raise ValueError(f"Invalid os_system: {config.os_system}")
        
    return config


def _remove_secret_fields(data: dict) -> None:
    for key in list(data):
        value = data[key]
        if any(marker in key.lower() for marker in ("key", "token", "secret", "password")):
            del data[key]
        elif isinstance(value, dict):
            _remove_secret_fields(value)
