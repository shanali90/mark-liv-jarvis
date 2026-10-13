from types import SimpleNamespace

from scripts import set_key


def test_set_key_hides_input_and_only_prints_saved(monkeypatch, capsys):
    saved = []
    monkeypatch.setitem(
        __import__("sys").modules,
        "keyring",
        SimpleNamespace(set_password=lambda *args: saved.append(args)),
    )
    monkeypatch.setattr("builtins.input", lambda _: "gemini_api_key")
    monkeypatch.setattr("getpass.getpass", lambda _: "mock-secret-value")

    assert set_key.main() == 0
    assert saved == [("Jarvis", "gemini_api_key", "mock-secret-value")]
    assert capsys.readouterr().out.strip() == "saved"


def test_set_key_never_prints_credential_suffix(monkeypatch, capsys):
    from core import vault

    monkeypatch.setattr(vault, "set_secret", lambda *_: True)
    monkeypatch.setattr("builtins.input", lambda _: "gemini_api_key")
    monkeypatch.setattr("getpass.getpass", lambda _: "secret-ending-9876")

    assert set_key.main() == 0
    output = capsys.readouterr().out
    assert "secret-ending-9876" not in output
    assert "9876" not in output
