from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np

from actions import browser_control, computer_control
from core import tab_finder


class FakeMouse:
    def __init__(self, size=(1280, 720), position=(200, 200), stuck=False):
        self._size = size
        self._position = position
        self.stuck = stuck
        self.moves = []
        self.clicks = []
        self.hotkeys = []

    def size(self):
        return self._size

    def position(self):
        return self._position

    def moveTo(self, x, y, duration):
        self.moves.append((x, y, duration))
        if not self.stuck:
            self._position = (x, y)

    def click(self, x, y, button, clicks):
        self.clicks.append((x, y, button, clicks))

    def hotkey(self, *keys):
        self.hotkeys.append(keys)


def _install_mouse(monkeypatch, mouse=None):
    mouse = mouse or FakeMouse()
    monkeypatch.setattr(computer_control, "pyautogui", mouse)
    monkeypatch.setattr(computer_control, "_PYAUTOGUI", True)
    return mouse


def test_screen_coordinates_scale_from_physical_pixels(monkeypatch):
    mouse = _install_mouse(monkeypatch)

    # A 1920x1080 physical monitor rendered to PyAutoGUI's 1280x720 space.
    assert computer_control._screen_to_mouse(
        1600, 800, {"left": 100, "top": 50, "width": 1920, "height": 1080},
    ) == (1000, 500)
    assert mouse.size() == (1280, 720)


def test_click_without_coordinates_refuses(monkeypatch):
    mouse = _install_mouse(monkeypatch)

    result = computer_control.computer_control({"action": "click"})

    assert result == "I need a target. Tell me what to click."
    assert mouse.clicks == []


def test_screen_click_not_found_does_not_click(monkeypatch):
    mouse = _install_mouse(monkeypatch)
    monkeypatch.setattr(computer_control, "_screen_find", lambda _description: None)

    result = computer_control.computer_control(
        {"action": "screen_click", "description": "Save"}
    )

    assert result == "I could not find 'Save' on screen"
    assert mouse.clicks == []


def test_click_verification_reports_unchanged_and_changed(monkeypatch):
    mouse = _install_mouse(monkeypatch)
    monkeypatch.setattr(computer_control.time, "sleep", lambda _seconds: None)
    same = np.zeros((36, 64), dtype=np.uint8)
    changed = np.full((36, 64), 255, dtype=np.uint8)
    frames = iter((same, same, same))
    monkeypatch.setattr(computer_control, "_screen_thumbnail", lambda: next(frames))

    result = computer_control.computer_control(
        {"action": "click", "x": 500, "y": 300}
    )

    assert "NOTHING changed" in result
    assert len(mouse.clicks) == 1

    frames = iter((same, same, changed))
    monkeypatch.setattr(computer_control, "_screen_thumbnail", lambda: next(frames))
    result = computer_control.computer_control(
        {"action": "double_click", "x": 500, "y": 300}
    )
    assert "the screen changed, it worked." in result
    assert mouse.clicks[-1] == (500, 300, "left", 2)


def test_mouse_position_mismatch_retries_once_and_reports_failure(monkeypatch):
    mouse = _install_mouse(monkeypatch, FakeMouse(stuck=True))

    result = computer_control._move(400, 250)

    assert "Mouse move failed" in result
    assert len(mouse.moves) == 2
    assert all(duration == 0.25 for _, _, duration in mouse.moves)
    assert mouse.clicks == []


class FakeWindow:
    def __init__(self, titles):
        self.titles = titles
        self.index = 0
        self.isMinimized = False
        self.activations = 0
        self.restores = 0

    @property
    def title(self):
        return self.titles[self.index]

    def activate(self):
        self.activations += 1

    def restore(self):
        self.restores += 1


def _fake_tab_cycle(monkeypatch, window):
    advances = []
    monkeypatch.setattr(tab_finder.platform, "system", lambda: "Windows")
    monkeypatch.setattr(tab_finder, "_chrome_windows", lambda: [window])
    monkeypatch.setattr(tab_finder, "_window_title", lambda win: win.title)
    monkeypatch.setattr(tab_finder, "_focus_window", lambda _win: True)

    def advance():
        window.index = (window.index + 1) % len(window.titles)
        advances.append(window.index)

    monkeypatch.setattr(tab_finder, "_advance_tab", advance)
    return advances


def test_existing_chrome_tab_match_on_third_ctrl_tab_does_not_launch(monkeypatch):
    window = FakeWindow([
        "New Tab - Google Chrome",
        "Inbox - Gmail - Google Chrome",
        "Instagram - Google Chrome",
        "YouTube - Google Chrome",
    ])
    advances = _fake_tab_cycle(monkeypatch, window)
    launches = []
    monkeypatch.setattr(browser_control, "_OS", "Windows")
    monkeypatch.setattr(browser_control, "_find_chrome", lambda: "chrome.exe")
    monkeypatch.setattr(browser_control.subprocess, "Popen", lambda *a, **k: launches.append(a))
    monkeypatch.setitem(
        sys.modules,
        "actions.window_manager",
        SimpleNamespace(switch_to_window_internal=lambda _target: False),
    )

    assert tab_finder.find_and_focus_existing("https://youtube.com")
    assert len(advances) == 3

    window.index = 0
    advances.clear()
    result = browser_control._open_native("https://youtube.com")

    assert result == "Switched to your already-open YouTube tab"
    assert len(advances) == 3
    assert launches == []


def test_existing_chrome_tab_search_stops_after_wrapping(monkeypatch):
    window = FakeWindow([
        "New Tab - Google Chrome",
        "Calendar - Google Chrome",
        "Docs - Google Chrome",
    ])
    advances = _fake_tab_cycle(monkeypatch, window)

    assert not tab_finder.find_and_focus_existing("https://youtube.com")
    assert len(advances) == 3


def test_no_match_launches_chrome_once(monkeypatch):
    window = FakeWindow([
        "New Tab - Google Chrome",
        "Calendar - Google Chrome",
        "Docs - Google Chrome",
    ])
    _fake_tab_cycle(monkeypatch, window)
    launches = []
    monkeypatch.setattr(browser_control, "_OS", "Windows")
    monkeypatch.setattr(browser_control, "_find_chrome", lambda: "chrome.exe")
    monkeypatch.setattr(browser_control.subprocess, "Popen", lambda *a, **k: launches.append(a))

    result = browser_control._open_native("https://youtube.com")

    assert result == "Opened a new YouTube tab"
    assert len(launches) == 1
