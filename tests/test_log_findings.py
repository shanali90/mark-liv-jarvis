"""Bugs found in the owner's own log (2026-10-24)."""
import ast
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_wake_owner_name_function_exists():
    """wake() imports get_owner_name; it did not exist, so the wake handler crashed
    right after the state change: no greeting and the window never appeared."""
    from memory import config_manager
    assert callable(config_manager.get_owner_name)
    assert isinstance(config_manager.get_owner_name(), str) and config_manager.get_owner_name()


def test_pending_flag_expires_so_kill_switch_does_not_fire_for_ever():
    from actions import send_message as sm
    sm.set_action_pending(True)
    assert sm.is_action_pending()
    sm._ACTION_SINCE = time.monotonic() - sm._ACTION_PENDING_TTL - 1
    assert not sm.is_action_pending()
    assert sm.abort_current_action() is False
    sm.set_action_pending(True)
    sm.reset_action_abort()              # a new action starting clears it
    assert not sm.is_action_pending()


def test_real_desktop_is_used_not_home_slash_desktop(tmp_path, monkeypatch):
    from core import paths
    onedrive_desktop = tmp_path / "OneDrive" / "Desktop"
    onedrive_desktop.mkdir(parents=True)
    monkeypatch.setattr(paths, "_windows_known_folder", lambda name: onedrive_desktop)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    assert paths.user_folder("desktop") == onedrive_desktop
    assert paths.desktop() == onedrive_desktop


def test_file_controller_and_screenshots_use_the_real_desktop():
    for rel in ("actions/file_controller.py", "actions/computer_control.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        assert "core.paths" in src, rel
    assert 'Path.home() / "Desktop"' not in (ROOT / "actions/file_controller.py").read_text(encoding="utf-8")


def test_create_folder_says_where_and_whether_it_already_existed(tmp_path, monkeypatch):
    from actions import file_controller as fc
    monkeypatch.setattr(fc, "_resolve_path", lambda p: tmp_path)
    monkeypatch.setattr(fc, "_is_safe_path", lambda p: True)
    first = fc.create_folder("x", "My Folder")
    assert str(tmp_path / "My Folder") in first and "created" in first.lower()
    second = fc.create_folder("x", "My Folder")
    assert "already existed" in second.lower() and str(tmp_path / "My Folder") in second


def test_goaway_triggers_a_reconnect_in_the_receive_loop():
    tree = ast.parse((ROOT / "core/audio/mixin.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_receive_audio")
    src = ast.unparse(fn)
    assert "go_away" in src and "request_reconnect" in src
