"""Tests for the JARVIS UI redesign (dark purple, plain log, animations, clock, migration)."""

import json
import os
import re

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

# Ensure Qt runs offscreen in headless test runs
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_removed_widgets(qapp):
    """(a) No widget named SYS MONITOR / AI CORE / SEC CLEARED / PROTOCOL / Made by exists on main window."""
    from ui import MainWindow

    win = MainWindow("face.png")
    win.show()

    forbidden_patterns = [
        "SYS MONITOR",
        "AI CORE",
        "SEC CLEARED",
        "PROTOCOL",
        "Made by",
    ]

    labels = win.findChildren(QLabel)
    found_violations = []

    for lbl in labels:
        txt = lbl.text() or ""
        for pat in forbidden_patterns:
            if pat in txt:
                found_violations.append((pat, txt, lbl.objectName()))

    win.close()
    assert not found_violations, f"Found forbidden widgets on main window: {found_violations}"


def test_clock_format(qapp):
    """(b) Simple clock format: big '2:36 PM' (12-hour, no seconds, no leading zero), small 'Saturday, 24 October'."""
    from ui import MainWindow

    win = MainWindow("face.png")
    win._tick_clock()

    clock_text = win._clock_lbl.text().strip()
    date_text = win._date_lbl.text().strip()

    win.close()

    # 12-hour time: e.g. "2:36 PM", "12:05 AM" (no leading zero on hour, 2 digits on minute, AM/PM)
    clock_pattern = r"^(1[0-2]|[1-9]):[0-5][0-9]\s+[AP]M$"
    assert re.match(clock_pattern, clock_text), f"Clock format '{clock_text}' does not match '2:36 PM' format"

    # Full weekday, day of month, full month: e.g. "Saturday, 24 October"
    date_pattern = r"^[A-Z][a-z]+,\s+\d{1,2}\s+[A-Z][a-z]+$"
    assert re.match(date_pattern, date_text), f"Date format '{date_text}' does not match 'Saturday, 24 October' format"


def test_plain_log_line():
    """(c) plain_log_line rewrites known technical messages and hides audit lines."""
    from ui import plain_log_line

    # NET connection failure
    net_line = "NET: Connection failed (APIError [1006]: 1006 None. Abnormal closure.) - retrying in 2s"
    assert plain_log_line(net_line) == "Internet dropped. Reconnecting in 2 s..."

    # ERR session error
    err_line = "ERR: Session error (APIError: invalid session) - retrying in 2s"
    assert plain_log_line(err_line) == "Something went wrong. Reconnecting..."

    # SYS online sleeping
    sys_sleep = "SYS: JARVIS online - sleeping. Say 'Hey Jarvis' to wake me."
    assert plain_log_line(sys_sleep) == "Ready. Say 'Hey Jarvis' to wake me."

    # SYS awake wake word
    sys_awake = "SYS: Awake - wake word."
    assert plain_log_line(sys_awake) == "I'm listening."

    # Audit / unprompted tool call lines are hidden (returns None)
    assert plain_log_line("UNPROMPTED TOOL CALL: manage_monitor") is None
    assert plain_log_line("[Audit] Action recorded for file") is None

    # Unknown lines pass through unchanged
    assert plain_log_line("You: Hello JARVIS") == "You: Hello JARVIS"
    assert plain_log_line("SYS: Camera preview started.") == "SYS: Camera preview started."


def test_animation_timer_stops_when_hidden(qapp):
    """(d) Animation timer pauses/stops when window is hidden and resumes when shown."""
    from ui import MainWindow

    win = MainWindow("face.png")
    win.show()
    assert hasattr(win, "_anim_timer"), "MainWindow must have an animation timer _anim_timer"
    assert win._anim_timer.isActive() is True, "Animation timer should be active when window is visible"

    win.hide()
    assert win._anim_timer.isActive() is False, "Animation timer must stop when window is hidden"

    win.show()
    assert win._anim_timer.isActive() is True, "Animation timer must resume when window is shown"

    win.close()


def test_window_builds_and_closes_offscreen(qapp):
    """(e) Window builds, renders offscreen, and closes cleanly without exceptions."""
    from ui import MainWindow

    win = MainWindow("face.png")
    win.show()
    pix = win.grab()
    assert not pix.isNull()
    assert pix.width() > 100
    assert pix.height() > 100
    win.close()


def test_saved_accent_migration_runs_once(tmp_path):
    """(f) Saved accent migration runs once, backs up old gold color, and sets new violet default."""
    from ui_theme.migration import migrate_saved_accent

    config_file = tmp_path / "settings.json"
    initial_data = {
        "assistant_name": "JARVIS",
        "ui_color": "#ffb300",
        "voice_name": "Charon",
    }
    config_file.write_text(json.dumps(initial_data, indent=4), encoding="utf-8")

    # First run: should migrate
    first_run = migrate_saved_accent(config_file, default_accent="#a78bfa")
    assert first_run is True

    migrated = json.loads(config_file.read_text(encoding="utf-8"))
    assert migrated["ui_color"] == "#a78bfa"
    assert migrated["previous_ui_color"] == "#ffb300"
    assert migrated["ui_color_migrated"] is True

    # User picks a different color later
    migrated["ui_color"] = "#10b981"
    config_file.write_text(json.dumps(migrated, indent=4), encoding="utf-8")

    # Second run: must NOT overwrite because migration already ran once
    second_run = migrate_saved_accent(config_file, default_accent="#a78bfa")
    assert second_run is False

    unchanged = json.loads(config_file.read_text(encoding="utf-8"))
    assert unchanged["ui_color"] == "#10b981"
    assert unchanged["previous_ui_color"] == "#ffb300"
