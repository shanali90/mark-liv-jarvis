from __future__ import annotations

import asyncio
import threading
import time

import pytest

from actions import background_monitor, system_monitor
from actions.proactive import ProactiveEngine
from core import activity
from memory import config_manager


@pytest.fixture
def reset_activity(monkeypatch):
    monkeypatch.setattr(activity, "_last_user_speech", None)
    monkeypatch.setattr(activity, "_last_tool_call", None)


@pytest.mark.anyio
async def test_disabled_proactive_mode_sends_nothing(monkeypatch):
    import main

    monkeypatch.setattr(config_manager, "get_proactive_enabled", lambda: False)
    monkeypatch.setattr(main, "load_memory", lambda: {})
    monkeypatch.setattr(main, "list_monitors", lambda: [])

    sent = []

    class Session:
        async def send_client_content(self, **kwargs):
            sent.append(kwargs)

    class Harness:
        _run_proactive_mode = main.JarvisLive._run_proactive_mode

        def __init__(self):
            self.session = Session()
            self._awake = True
            self._speaking_lock = threading.Lock()
            self._is_speaking = False
            self._proactive = ProactiveEngine(min_silence_secs=0, check_cooldown=0)
            self._last_user_speech = time.monotonic() - 3600
            self._session_log = []

    real_sleep = asyncio.sleep
    sleep_calls = 0

    async def stop_after_one_check(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", stop_after_one_check)
    with pytest.raises(asyncio.CancelledError):
        await Harness()._run_proactive_mode()

    assert sent == []


def test_proactive_defaults_off_and_requires_thirty_minutes(monkeypatch):
    monkeypatch.setattr(config_manager, "load_api_keys", lambda: {})

    assert not config_manager.get_proactive_enabled()
    engine = ProactiveEngine()
    assert engine.min_silence_secs == 1800
    assert not engine.should_trigger(time.monotonic() - 3600)


def test_recent_speech_blocks_system_and_background_monitor_alerts(
    monkeypatch, reset_activity
):
    activity.record_user_speech()
    assert not activity.background_notice_allowed()

    metrics_called = []
    monkeypatch.setattr(system_monitor.psutil, "cpu_percent",
                        lambda **_kwargs: metrics_called.append("cpu") or 100)
    monkeypatch.setattr(system_monitor.psutil, "virtual_memory",
                        lambda: type("Memory", (), {"percent": 100})())
    monkeypatch.setattr(system_monitor, "_get_cpu_temp", lambda: 100)
    monkeypatch.setattr(system_monitor, "_get_gpu_usage", lambda: 100)
    monitor = system_monitor.SystemMonitor(
        {"cpu": 0, "ram": 0, "temp": 0, "gpu": 0}
    )
    assert monitor.check() is None
    assert metrics_called == []

    news_called = []
    monkeypatch.setattr(background_monitor, "_load", lambda: {
        "sample": {"topic": "sample", "last_check": "", "last_hash": ""}
    })
    monkeypatch.setattr(background_monitor, "_save", lambda _monitors: None)

    def fake_news(*_args, **_kwargs):
        news_called.append(True)
        return [{"title": "Sample update", "snippet": "", "source": ""}]

    monkeypatch.setattr("actions.web_search._ddg_news", fake_news)
    assert background_monitor.check_all() == []
    assert news_called == []


def test_recent_tool_call_blocks_system_and_background_alerts(
    monkeypatch, reset_activity
):
    activity.record_tool_call()

    assert not activity.background_notice_allowed()
    metrics_called = []
    monkeypatch.setattr(system_monitor.psutil, "cpu_percent",
                        lambda **_kwargs: metrics_called.append("cpu") or 100)
    monitor = system_monitor.SystemMonitor({"cpu": 0})
    assert monitor.check() is None
    assert metrics_called == []

    news_called = []
    monkeypatch.setattr(background_monitor, "_load", lambda: {
        "sample": {"topic": "sample", "last_check": "", "last_hash": ""}
    })
    monkeypatch.setattr(background_monitor, "_save", lambda _monitors: None)
    monkeypatch.setattr(
        "actions.web_search._ddg_news",
        lambda *_args, **_kwargs: news_called.append(True),
    )
    assert background_monitor.check_all() == []
    assert news_called == []
