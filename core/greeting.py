"""Short, varied wake acknowledgements."""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_LAST_GREETING: str | None = None


def pick_greeting(hour: int, name: str = "") -> str:
    """Choose a short time-appropriate greeting without repeating consecutively."""
    global _LAST_GREETING
    hour = int(hour) % 24
    owner = " ".join(str(name or "").split()).strip() or "sir"

    if 5 <= hour < 12:
        options = (
            f"Good morning {owner}, ready when you are.",
            f"Yes {owner}, I'm here.",
            f"At your service, {owner}.",
            f"Morning {owner}. Ready when you are.",
        )
    elif 12 <= hour < 18:
        options = (
            f"Good afternoon {owner}, ready when you are.",
            f"Yes {owner}, I'm here.",
            f"At your service, {owner}.",
            f"Good afternoon {owner}, I'm here.",
        )
    elif 18 <= hour < 22:
        options = (
            f"Good evening {owner}, ready when you are.",
            f"Yes {owner}, I'm here.",
            f"At your service, {owner}.",
            f"Good evening {owner}, I'm here.",
        )
    else:
        options = (
            f"Yes {owner}, I'm here.",
            f"At your service, {owner}.",
            f"Ready when you are, {owner}.",
            f"I'm here, {owner}.",
        )

    with _LOCK:
        available = [item for item in options if item != _LAST_GREETING]
        if not available:
            available = list(options)
        greeting = available[0]
        _LAST_GREETING = greeting
    return greeting
