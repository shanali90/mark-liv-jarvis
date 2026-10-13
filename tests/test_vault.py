import json
import sys
from types import SimpleNamespace

from core import vault
from memory import config_manager


def test_get_secret_prefers_environment_over_keyring(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "environment-fixture")
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(get_password=lambda *_: "keyring-fixture"),
    )

    assert vault.get_secret("gemini_api_key") == "environment-fixture"


def test_get_secret_uses_keyring_and_does_not_read_json(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "keyring",
        SimpleNamespace(get_password=lambda *_: "keyring-fixture"),
    )
    monkeypatch.setattr(config_manager, "CONFIG_FILE", tmp_path / "api_keys.json")
    config_manager.CONFIG_FILE.write_text(
        json.dumps({"gemini_api_key": "legacy-file-fixture"}),
        encoding="utf-8",
    )

    assert vault.get_secret("gemini_api_key") == "keyring-fixture"


def test_api_key_save_uses_keyring_and_never_writes_json(monkeypatch, tmp_path):
    config_path = tmp_path / "api_keys.json"
    config_manager.CONFIG_FILE = config_path
    saved = []
    monkeypatch.setattr(vault, "set_secret", lambda name, value: saved.append((name, value)) or True)

    config_manager.save_api_keys("new-fixture")

    assert saved == [("gemini_api_key", "new-fixture")]
    assert not config_path.exists()


def test_settings_updates_remove_legacy_keys_from_json(monkeypatch, tmp_path):
    config_path = tmp_path / "api_keys.json"
    config_path.write_text(
        json.dumps(
            {
                "gemini_api_key": "legacy-file-fixture",
                "openai_api_key": "legacy-openai-fixture",
                "os_system": "windows",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_FILE", config_path)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)

    config_manager.save_assistant_config("JARVIS", "")

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert "gemini_api_key" not in saved
    assert "openai_api_key" not in saved
    assert saved["os_system"] == "windows"


def test_settings_updates_remove_nested_credentials(monkeypatch, tmp_path):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "plugin_config": {
                    "mail": {
                        "client_secret": "legacy-fixture",
                        "region": "test-region",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config_manager, "CONFIG_FILE", config_path)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)

    config_manager.save_assistant_config("JARVIS", "")

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["plugin_config"]["mail"] == {"region": "test-region"}
