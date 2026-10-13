import main
from core import safety, vault


def test_missing_gemini_key_prints_setup_instructions_and_returns(
    monkeypatch, capsys
):
    monkeypatch.setattr(safety.integrity, "verify_pinned_files", lambda *_: None)
    monkeypatch.setattr(vault, "get_secret", lambda *_: "")
    monkeypatch.setattr(
        main,
        "JarvisUI",
        lambda *_: (_ for _ in ()).throw(AssertionError("UI must not start")),
    )

    assert main.main() is None
    message = capsys.readouterr().err
    assert "GEMINI_API_KEY" in message
    assert "scripts/set_key.py" in message
