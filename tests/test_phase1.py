import json
import subprocess
import sys
import time
from pathlib import Path

from core.audit import AUDIT_LOG_FILE, log_action, verify_chain
from core.kill_switch import kill_switch
from core.permissions import SafetyLevel
from core.registry import registry


def uncooperative_task():
    """A task that ignores cooperative cancellation by looping forever."""
    while True:
        try:
            time.sleep(0.1)
        except BaseException:
            pass # ignore cancellation

def test_kill_switch_force_kill():
    # Start task
    p = kill_switch.run_task(uncooperative_task)
    time.sleep(0.5)
    assert p.is_alive()
    
    # Trigger kill switch
    start = time.monotonic()
    kill_switch.trigger()
    end = time.monotonic()
    
    assert not p.is_alive()
    assert (end - start) < 2.0

def test_approval_deny(monkeypatch):
    # Mock MessageBoxW to return IDNO (7)
    import ctypes
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda *args, **kwargs: 7)
    
    def red_tool():
        return "Executed"
        
    registry.register("red_tool", "A dangerous tool", SafetyLevel.RED, red_tool)
    
    import pytest
    with pytest.raises(PermissionError):
        registry.execute("red_tool", {})

def test_approval_expiry(monkeypatch):
    # Mock MessageBoxW to do nothing and hang until timeout
    import ctypes
    def hang_box(*args, **kwargs):
        time.sleep(2)
        return 7
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", hang_box)
    
    def timeout_tool():
        return "Executed"
        
    registry.register("timeout_tool", "A timeout tool", SafetyLevel.RED, timeout_tool)
    
    import pytest
    start = time.monotonic()
    with pytest.raises(PermissionError):
        # Pass a very short timeout for testing
        registry.execute("timeout_tool", {"_short_timeout": 0.5})
    end = time.monotonic()
    
    assert (end - start) < 1.0 # Should timeout well before 2 seconds

def test_audit_log_hash_chain():
    # Clear audit log for test
    if AUDIT_LOG_FILE.exists():
        AUDIT_LOG_FILE.unlink()
        
    log_action("test_actor", "test_action_1", "tool_1", {"arg": "val1"})
    log_action("test_actor", "test_action_2", "tool_2", {"arg": "val2"})
    
    # Verify chain
    assert verify_chain() == True
    
    # Tamper log
    lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[0])
    data["inputs"]["arg"] = "tampered"
    lines[0] = json.dumps(data)
    AUDIT_LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    
    # Verify chain fails
    assert verify_chain() == False

def test_log_secret_redaction():
    if AUDIT_LOG_FILE.exists():
        AUDIT_LOG_FILE.unlink()
        
    fake_sk_key = "sk-" + "a" * 40
    fake_google_key = "AIza" + "A" * 35
    inputs = {
        "normal_arg": "value",
        "api_key": fake_sk_key,
        "my_secret_token": fake_google_key
    }
    
    log_action("test_actor", "secret_test", "tool_1", inputs)
    
    content = AUDIT_LOG_FILE.read_text(encoding="utf-8")
    assert fake_sk_key not in content
    assert fake_google_key not in content
    assert "[REDACTED]" in content
    assert "normal_arg" in content

def test_git_hook_secret_scan(tmp_path):
    # Test the git hook directly by running the script logic in a temporary repo
    # Initialize a dummy git repo
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    
    # Write the hook script to the tmp repo
    hook_path = tmp_path / "hook.sh"
    hook_content = (Path(__file__).parent.parent / "scripts" / "hooks" / "pre-commit").read_text()
    hook_path.write_text(hook_content)
    
    # Stage a file with a fake secret
    fake_sk_key = "sk-" + "a" * 40
    secret_file = tmp_path / "test.py"
    secret_file.write_text("API_KEY = '" + fake_sk_key + "'")
    subprocess.run(["git", "add", "test.py"], cwd=tmp_path, capture_output=True)
    
    # Run the hook using bash. If bash isn't available, we skip.
    # On Windows, Git bash is usually in PATH as 'bash'.
    try:
        command = [sys.executable, str(hook_path)] if sys.platform == "win32" else ["bash", "hook.sh"]
        result = subprocess.run(command, cwd=tmp_path, capture_output=True)
        assert result.returncode == 1
        assert b"Commit blocked" in result.stderr
    except FileNotFoundError:
        # Bash not found in path on Windows runner, skip actual execution
        pass

def test_approval_round_trip(monkeypatch):
    import ctypes
    monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda *args, **kwargs: 6) # IDYES
    
    def approve_tool():
        return "Approved Execute"
        
    registry.register("approve_tool", "Round trip tool", SafetyLevel.RED, approve_tool)
    
    result = registry.execute("approve_tool", {})
    assert result == "Approved Execute"

def test_direct_bypass_blocked():
    def direct_tool():
        return "Bypass"
        
    registry.register("direct_tool", "Direct tool", SafetyLevel.RED, direct_tool)
    
    # We don't export the function directly from registry, but if we did or if they bypassed `execute`:
    import pytest
    with pytest.raises(PermissionError):
        # Extract the wrapped function directly from internal tools dict
        direct_func = registry._tools["direct_tool"]["func"]
        # Call it directly without registry.execute
        direct_func(_short_timeout=0.1)

def test_kill_switch_sentinel_trigger():
    import os
    
    # ensure it's running
    kill_switch.start_listeners()
    
    # create dummy task
    p = kill_switch.run_task(uncooperative_task)
    time.sleep(0.5)
    assert p.is_alive()
    
    # create sentinel file
    sentinel_path = os.path.join(os.path.dirname(__file__), '..', '.kill_sentinel')
    with open(sentinel_path, 'w') as f:
        f.write("KILL")
        
    # wait for sentinel thread to pick it up
    time.sleep(1.0)
    
    assert not p.is_alive()
    assert not os.path.exists(sentinel_path)

def test_kill_switch_hotkey_registration():
    # since we already called start_listeners, the thread is running. 
    # we can't easily simulate keypresses across threads in a headless test without injecting WM_HOTKEY,
    # but we can verify the thread started and doesn't crash.
    assert kill_switch._hotkey_thread.is_alive()
