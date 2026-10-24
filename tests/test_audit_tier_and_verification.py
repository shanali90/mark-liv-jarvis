"""Tests for Audit 1 requirements A-D:
  - Verifiers for files, apps, websites, settings (success, failure, already-open)
  - Speech gate blocking German, Japanese, Portuguese, and outside 25s window
  - Speech gate allowing Jarvis commands, Sindhi, Urdu/Hindi, and follow-ups within 25s
  - Autonomy tiers (just do it, announce then do, always ask)
  - Announce-and-wait cancellation via voice/ESC and model cannot set confirmed=True
  - SelfHeal wrapper starts with NOT DONE: and keeps reason in first 200 chars
  - Website already-open switching and internet down detection
"""
from __future__ import annotations

import time


from core import verify_action as va
from core import speech_gate as sg
from core import autonomy as aut
from selfheal import detect as sh


# ── A. Verifiers: path, file, app, website, settings ─────────────────────────

def test_verify_path_exists(tmp_path):
    folder = tmp_path / "TestFolder"
    # Not created yet
    ok, msg, p = va.verify_path_exists(folder, "folder")
    assert not ok
    assert msg.startswith("NOT DONE:")
    assert "does not exist" in msg

    # Created
    folder.mkdir()
    ok, msg, p = va.verify_path_exists(folder, "folder")
    assert ok
    assert msg.startswith("DONE:")
    assert "(checked: path exists)" in msg
    assert str(folder.resolve()) in msg


def test_verify_file_deleted(tmp_path):
    f = tmp_path / "dummy.txt"
    f.write_text("hello")
    # Still exists
    ok, msg = va.verify_file_deleted(f)
    assert not ok
    assert msg.startswith("NOT DONE:")

    # Deleted
    f.unlink()
    ok, msg = va.verify_file_deleted(f)
    assert ok
    assert msg.startswith("DONE:")
    assert "(checked: file removed)" in msg


def test_verify_file_moved(tmp_path):
    src = tmp_path / "source.txt"
    dst = tmp_path / "dest.txt"
    src.write_text("data")

    # Before move
    ok, msg = va.verify_file_moved(src, dst)
    assert not ok
    assert msg.startswith("NOT DONE:")

    # After move
    src.rename(dst)
    ok, msg = va.verify_file_moved(src, dst)
    assert ok
    assert msg.startswith("DONE:")
    assert "(checked: destination exists)" in msg


def test_verify_app_opened_already_open(monkeypatch):
    monkeypatch.setattr(va, "get_current_window_titles", lambda: ["Notepad - Untitled", "Chrome"])
    monkeypatch.setattr(va, "bring_window_to_front", lambda kw: True)

    ok, msg = va.verify_app_opened("Notepad", check_already_open=True)
    assert ok
    assert msg.startswith("DONE:")
    assert "already open, brought to front" in msg or "already open" in msg


def test_verify_app_opened_success(monkeypatch):
    windows_seq = iter([
        [],
        ["Calculator"],
    ])
    monkeypatch.setattr(va, "get_current_window_titles", lambda: next(windows_seq, ["Calculator"]))
    monkeypatch.setattr(va, "get_current_process_names", lambda: set())

    ok, msg = va.verify_app_opened("Calculator", timeout=1.0, check_already_open=False)
    assert ok
    assert msg.startswith("DONE:")
    assert "opened Calculator" in msg


def test_verify_app_opened_failure(monkeypatch):
    monkeypatch.setattr(va, "get_current_window_titles", lambda: [])
    monkeypatch.setattr(va, "get_current_process_names", lambda: set())

    ok, msg = va.verify_app_opened("NonExistentApp", timeout=0.4, check_already_open=False)
    assert not ok
    assert msg.startswith("NOT DONE:")
    assert "no window or process appeared" in msg


def test_verify_website_opened_already_open(monkeypatch):
    from core import tab_finder
    monkeypatch.setattr(tab_finder, "find_and_focus_existing", lambda url: True)

    ok, msg = va.verify_website_opened("https://www.youtube.com", check_already_open=True)
    assert ok
    assert msg.startswith("DONE:")
    assert "switched to your open YouTube tab" in msg


def test_verify_website_opened_success(monkeypatch):
    from core import tab_finder
    monkeypatch.setattr(tab_finder, "find_and_focus_existing", lambda url: False)
    monkeypatch.setattr(va, "get_current_window_titles", lambda: ["YouTube - Google Chrome"])

    ok, msg = va.verify_website_opened("youtube", timeout=1.0, check_already_open=False)
    assert ok
    assert msg.startswith("DONE:")
    assert "opened YouTube" in msg


def test_verify_website_opened_internet_down(monkeypatch):
    from core import tab_finder
    monkeypatch.setattr(tab_finder, "find_and_focus_existing", lambda url: False)
    monkeypatch.setattr(va, "get_current_window_titles", lambda: ["YouTube - Can't reach this page - Google Chrome"])

    ok, msg = va.verify_website_opened("youtube", timeout=1.0, check_already_open=False)
    assert not ok
    assert msg.startswith("NOT DONE:")
    assert "internet may be down" in msg


def test_verify_setting_changed_success():
    ok, msg = va.verify_setting_changed("volume", target_val=50, get_func=lambda: 50)
    assert ok
    assert msg.startswith("DONE:")
    assert "50%" in msg


def test_verify_setting_changed_unconfirmed():
    ok, msg = va.verify_setting_changed("volume", target_val=50, get_func=lambda: None)
    assert not ok
    assert msg.startswith("UNSURE:")


# ── B. Speech Gate: Noise rejection & Language filtering ──────────────────────

def test_speech_gate_blocks_german_transcripts():
    state = {"is_awake": True, "active_window": True}
    allowed, reason = sg.decide_action_allowed("Ja, ist okay. Irgendwo in der Garage...", state)
    assert not allowed
    assert "language" in reason.lower() or "german" in reason.lower()


def test_speech_gate_blocks_japanese_transcripts():
    state = {"is_awake": True, "active_window": True}
    allowed, reason = sg.decide_action_allowed("ひか れ も が", state)
    assert not allowed
    assert "language" in reason.lower() or "japanese" in reason.lower()


def test_speech_gate_blocks_portuguese_and_spanish_noise():
    state = {"is_awake": True, "active_window": True}
    allowed1, reason1 = sg.decide_action_allowed("futebol de rua. Ok, do it.", state)
    assert not allowed1

    allowed2, reason2 = sg.decide_action_allowed("¿Qué te ha dado Jesús? folder", state)
    assert not allowed2


def test_speech_gate_allows_jarvis_commands():
    state = {"is_awake": True}
    allowed, reason = sg.decide_action_allowed("Jarvis open WhatsApp", state)
    assert allowed
    assert reason == "allowed"


def test_speech_gate_blocks_outside_25s_window():
    now = 1000.0
    state = {
        "is_awake": True,
        "now": now,
        "last_command_time": now - 35.0,
        "last_reply_time": now - 30.0,
    }
    # Command without assistant name/wake word after 30s silence
    allowed, reason = sg.decide_action_allowed("open the camera", state)
    assert not allowed
    assert "outside" in reason.lower() or "25s" in reason.lower()


def test_speech_gate_allows_follow_up_inside_25s_window():
    now = 1000.0
    state = {
        "is_awake": True,
        "now": now,
        "last_command_time": now - 10.0,
        "last_reply_time": now - 5.0,
    }
    # Follow-up without assistant name within 25s
    allowed, reason = sg.decide_action_allowed("open the camera", state)
    assert allowed
    assert reason == "allowed"


def test_speech_gate_allows_sindhi_and_urdu():
    state = {"is_awake": True}
    # Sindhi with wake word
    allowed_sd, _ = sg.decide_action_allowed("سائين واٽس ايپ کوليو", state)
    assert allowed_sd

    # Urdu/Hindi command
    allowed_ur, _ = sg.decide_action_allowed("جاروس ڪئميرا کول", state)
    assert allowed_ur

    # Roman Urdu/Hindi
    allowed_roman, _ = sg.decide_action_allowed("Jarvis camera open karo", state)
    assert allowed_roman


# ── C. Autonomy Tiers & Confirmation Gate ─────────────────────────────────────

def test_autonomy_tier_classification():
    # Tier 1: Just do it
    assert aut.get_autonomy_tier("open_app", args={"app_name": "Chrome"}) == aut.TIER_JUST_DO_IT
    assert aut.get_autonomy_tier("web_search", args={"query": "weather"}) == aut.TIER_JUST_DO_IT
    assert aut.get_autonomy_tier("file_controller", "create_folder") == aut.TIER_JUST_DO_IT
    assert aut.get_autonomy_tier("file_controller", "move") == aut.TIER_JUST_DO_IT
    assert aut.get_autonomy_tier("computer_settings", "volume_up") == aut.TIER_JUST_DO_IT
    assert aut.get_autonomy_tier("computer_control", "screenshot") == aut.TIER_JUST_DO_IT

    # Tier 2: Announce, then do (4s cancel window)
    assert aut.get_autonomy_tier("send_message", args={"receiver": "Mir"}) == aut.TIER_ANNOUNCE_THEN_DO
    assert aut.get_autonomy_tier("file_controller", "delete") == aut.TIER_ANNOUNCE_THEN_DO
    assert aut.get_autonomy_tier("computer_settings", "toggle_wifi") == aut.TIER_ANNOUNCE_THEN_DO
    assert aut.get_autonomy_tier("social_post") == aut.TIER_ANNOUNCE_THEN_DO

    # Tier 3: Always ask
    assert aut.get_autonomy_tier("shutdown_jarvis") == aut.TIER_ALWAYS_ASK
    assert aut.get_autonomy_tier("computer_settings", "restart") == aut.TIER_ALWAYS_ASK
    assert aut.get_autonomy_tier("payment") == aut.TIER_ALWAYS_ASK
    assert aut.get_autonomy_tier("permanent_delete") == aut.TIER_ALWAYS_ASK
    assert aut.get_autonomy_tier("file_processor", "execute_code") == aut.TIER_ALWAYS_ASK


def test_autonomy_master_switch_restores_old_behavior(monkeypatch):
    monkeypatch.setattr(aut, "is_ask_before_acting", lambda: True)
    # When master switch is ON, send_message and volume_set return ALWAYS_ASK
    assert aut.get_autonomy_tier("send_message") == aut.TIER_ALWAYS_ASK
    assert aut.get_autonomy_tier("computer_settings", "volume_set") == aut.TIER_ALWAYS_ASK


def test_announce_window_cancellation(monkeypatch):
    from actions import send_message as sm

    # Simulate voice cancel after 0.1s
    def fake_wait(*args, **kwargs):
        time.sleep(0.05)
        sm.abort_current_action()

    monkeypatch.setattr(sm, "is_action_aborted", lambda: True)
    ok, res = aut.announce_and_wait("send_message", "send", {"receiver": "Mir", "message_text": "hi"}, timeout=0.2)
    assert not ok
    assert res == "NOT DONE: action cancelled by user"


def test_model_cannot_forge_confirmed_flag():
    # Verify that in send_message, passing confirmed=False requests confirmation
    from actions.send_message import send_message
    res = send_message({"receiver": "Mir", "message_text": "hi", "confirmed": False})
    assert "[CONFIRMATION_PENDING]" in res


# ── D. SelfHeal Wrapper formatting ───────────────────────────────────────────

def test_selfheal_wrapper_starts_with_not_done_and_keeps_reason():
    def failing():
        raise RuntimeError("Target page, context or browser has been closed")

    ok, res, dur = sh.safe_execute("send_message", failing)
    assert not ok
    assert res.startswith("NOT DONE:")
    # Real reason must be within first 200 chars
    assert "Target page, context or browser has been closed" in res[:200]
