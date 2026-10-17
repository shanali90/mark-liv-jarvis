"""Recent user and tool activity timestamps used to gate background notices."""
from __future__ import annotations

import threading
import time


USER_SPEECH_COOLDOWN_SECS = 600
TOOL_CALL_COOLDOWN_SECS = 180

_lock = threading.Lock()
_last_user_speech: float | None = None
_last_tool_call: float | None = None


def record_user_speech() -> None:
    global _last_user_speech
    with _lock:
        _last_user_speech = time.monotonic()


def record_tool_call() -> None:
    global _last_tool_call
    with _lock:
        _last_tool_call = time.monotonic()


def background_notice_allowed(now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        speech_at = _last_user_speech
        tool_at = _last_tool_call
    return (
        (speech_at is None or now - speech_at >= USER_SPEECH_COOLDOWN_SECS)
        and (tool_at is None or now - tool_at >= TOOL_CALL_COOLDOWN_SECS)
    )
