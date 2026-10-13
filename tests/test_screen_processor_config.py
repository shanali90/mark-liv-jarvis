import pytest

from actions import screen_processor


@pytest.mark.parametrize(
    "setting",
    ["api_key", "access_token", "client_secret", "user_password"],
)
def test_save_config_key_rejects_credential_settings(tmp_path, monkeypatch, setting):
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(screen_processor, "_CONFIG_PATH", config_path)

    with pytest.raises(ValueError, match="OS keychain"):
        screen_processor._save_config_key(setting, "placeholder")

    assert not config_path.exists()


def test_save_config_key_persists_camera_index(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.json"
    monkeypatch.setattr(screen_processor, "_CONFIG_PATH", config_path)

    screen_processor._save_config_key("camera_index", 2)

    assert screen_processor._load_config() == {"camera_index": 2}
