import subprocess
import pytest

def run_hook_on_content(tmp_path, content, filename="test.py"):
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    hook_path = tmp_path / "hook.sh"
    from pathlib import Path
    hook_content = (Path(__file__).parent.parent / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    hook_path.write_text(hook_content, encoding="utf-8")

    test_file = tmp_path / filename
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=tmp_path, capture_output=True)

    res = subprocess.run(["python", str(hook_path)], cwd=tmp_path, capture_output=True, text=True)
    return "Commit blocked." in res.stderr

def test_hook_blocks_aiza(tmp_path):
    assert run_hook_on_content(tmp_path, 'AI' + 'za' + 'a'*35)

def test_hook_blocks_sk(tmp_path):
    assert run_hook_on_content(tmp_path, 's' + 'k-' + 'a'*40)

def test_hook_blocks_sk_ant(tmp_path):
    assert run_hook_on_content(tmp_path, 's' + 'k-ant-' + 'a'*40)

def test_hook_blocks_api_key_assignment(tmp_path):
    assert run_hook_on_content(tmp_path, 'api_key = "' + '1234567890abcdef1234567890abcdef"')

def test_hook_blocks_bearer(tmp_path):
    assert run_hook_on_content(tmp_path, 'Authorization: Bearer ' + 'a'*40)

def test_hook_blocks_40_hex(tmp_path):
    hex_key = "".join(("abcdef1234567890", "1234567890", "1234567890", "1234"))
    assert run_hook_on_content(tmp_path, hex_key)

def test_hook_allows_normal_function(tmp_path):
    assert not run_hook_on_content(tmp_path, 'def get_secret(name):')

@pytest.mark.parametrize(
    "filename",
    [
        "client_secret.json",
        "token.json",
        "memory\\private.db",
        "config\\api_keys.json",
        ".env",
        "config\\voice_profile.npy",
    ],
)
def test_hook_blocks_sensitive_files(tmp_path, filename):
    assert run_hook_on_content(tmp_path, "private data", filename)

def test_hook_blocks_fake_api_key_string(tmp_path):
    fake_key = "AIza" + "A" * 35
    assert run_hook_on_content(tmp_path, fake_key)
