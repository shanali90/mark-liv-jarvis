"""Reconnect classification, bounded backoff, and network readiness checks."""
from __future__ import annotations

import asyncio
import re
import socket
import time
from enum import Enum

from core.conn_errors import is_auth_error


class DisconnectKind(str, Enum):
    AUTH = "auth"
    RESUMPTION = "resumption"
    PLANNED = "planned"
    NETWORK = "network"
    PROTOCOL = "protocol"
    SERVER = "server"
    OTHER = "other"


def unwrap_exception(error: BaseException) -> BaseException:
    """Extract the primary cause from an ExceptionGroup or wrapper."""
    curr = error
    while isinstance(curr, BaseExceptionGroup):
        # Look for non-cancelled exception first
        real_excs = [e for e in curr.exceptions if not isinstance(e, asyncio.CancelledError)]
        if real_excs:
            curr = real_excs[0]
        elif curr.exceptions:
            curr = curr.exceptions[0]
        else:
            break
    return curr


def _error_text(error: BaseException) -> str:
    unwrapped = unwrap_exception(error)
    parts = [str(unwrapped), type(unwrapped).__name__]
    if isinstance(error, BaseExceptionGroup):
        parts.extend(_error_text(child) for child in error.exceptions)
    return " ".join(parts).lower()


def _error_codes(error: BaseException) -> set[int]:
    codes: set[int] = set()
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            codes.update(_error_codes(child))
    for field in ("code", "status_code", "close_code"):
        value = getattr(error, field, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        try:
            codes.add(int(value))
        except (TypeError, ValueError):
            pass
    # Only numbers that are actually a websocket close code ("received 1000",
    # "sent 1011", "code = 1006") - a bare "1000" in a quota message or a byte
    # count must not be taken for a planned close (that retried instantly, forever).
    codes.update(int(value) for value in re.findall(
        r"(?:received|sent|code\s*[=:]?)\s*(1000|1001|1006|1007|1011)\b", str(error), re.I))
    return codes


def classify_disconnect(error: BaseException, *, resuming: bool = False) -> DisconnectKind:
    """Classify Live API errors without mistaking an abnormal close for bad auth."""
    text = _error_text(error)
    if is_auth_error(text):
        return DisconnectKind.AUTH
    if resuming and any(
        marker in text for marker in ("resum", "session handle", "handle rejected", "not_found")
    ):
        return DisconnectKind.RESUMPTION
    codes = _error_codes(error)
    if 1000 in codes or 1001 in codes or "goaway" in text or "planned session end" in text:
        return DisconnectKind.PLANNED

    # Network errors: TimeoutError, "keepalive ping timeout", "1011", "1006",
    # ConnectionClosedError, "timed out", "getaddrinfo", "Temporary failure", OSError
    if any(
        marker in text for marker in (
            "timeout", "timed out", "getaddrinfo", "winerror 64",
            "network name is no longer available", "connection reset",
            "connection refused", "connectionclosed", "abnormal closure",
            "keepalive", "dns", "temporary failure", "oserror",
            "1011", "1006", "keepalive ping timeout",
        )
    ) or 1006 in codes or 1011 in codes:
        return DisconnectKind.NETWORK

    if 1007 in codes or "invalid frame" in text or "protocol error" in text:
        return DisconnectKind.PROTOCOL
    if "internal server error" in text or "service unavailable" in text:
        return DisconnectKind.SERVER
    return DisconnectKind.OTHER


class ReconnectBackoff:
    """Progress through 2, 4, 8, 15 seconds, resetting after a stable session."""

    _DELAYS = (2, 4, 8, 15)

    def __init__(self):
        self._index = 0

    def next_delay(self) -> int:
        delay = self._DELAYS[self._index]
        self._index = min(self._index + 1, len(self._DELAYS) - 1)
        return delay

    def reset(self) -> None:
        self._index = 0

    def reset_after_session(self, connected_seconds: float) -> bool:
        if connected_seconds > 30:
            self.reset()
            return True
        return False


class ErrorLogLimiter:
    """Allow a distinct connection error to be logged at most once per minute,
    and only print full traceback once per error type."""

    def __init__(self, interval: float = 60.0):
        self.interval = interval
        self._last_logged: dict[str, float] = {}
        self._seen_types: set[str] = set()

    def should_log(self, error: BaseException, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        unwrapped = unwrap_exception(error)
        key = f"{type(unwrapped).__name__}:{_error_text(unwrapped)}"
        previous = self._last_logged.get(key)
        if previous is not None and now - previous < self.interval:
            return False
        self._last_logged[key] = now
        self._last_logged = {
            item: timestamp for item, timestamp in self._last_logged.items()
            if now - timestamp < self.interval * 10
        }
        return True

    def should_print_traceback(self, error: BaseException) -> bool:
        unwrapped = unwrap_exception(error)
        name = type(unwrapped).__name__
        if name in self._seen_types:
            return False
        self._seen_types.add(name)
        return True


def format_disconnect_reason(error: BaseException, max_message_len: int = 150) -> str:
    """Describe a connection error: class, HTTP/close code, and first 150 chars of server message (never the key)."""
    unwrapped = unwrap_exception(error)
    cls_name = type(unwrapped).__name__

    codes = _error_codes(unwrapped)
    code_val = getattr(unwrapped, "code", getattr(unwrapped, "status_code", getattr(unwrapped, "close_code", None)))
    if code_val is not None:
        try:
            codes.add(int(code_val))
        except (ValueError, TypeError):
            pass

    code_str = f" [{', '.join(str(c) for c in sorted(codes))}]" if codes else ""

    raw_text = getattr(unwrapped, "message", None) or str(unwrapped)
    text = str(raw_text)
    for pattern in (
        r"AIza[A-Za-z0-9_-]{12,}",
        r"sk-ant-[A-Za-z0-9_-]{12,}",
        r"sk-[A-Za-z0-9_-]{12,}",
        r"(?i:Bearer\s+)[A-Za-z0-9._~+/-]{8,}=*",
        r"AQ\.[A-Za-z0-9._~-]{8,}",
        r"(?i:[?&](?:key|api_key|access_token)=)[^&\s]+",
    ):
        text = re.sub(pattern, "[REDACTED]", text)

    clean_msg = " ".join(text.strip().split())[:max_message_len]
    return f"{cls_name}{code_str}: {clean_msg}"


def safe_error_summary(error: BaseException) -> str:
    """Describe a connection error without exposing credential-shaped strings."""
    return format_disconnect_reason(error, max_message_len=240)


class PlannedReconnectLimiter:
    """Rate-limit planned reconnects: allow up to 3 within 20s; beyond that, apply normal backoff."""

    def __init__(self, max_count: int = 3, window_seconds: float = 20.0):
        self.max_count = max_count
        self.window_seconds = window_seconds
        self._timestamps: list[float] = []

    def record_and_should_backoff(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._timestamps = [t for t in self._timestamps if now - t <= self.window_seconds]
        self._timestamps.append(now)
        return len(self._timestamps) > self.max_count

    def reset(self) -> None:
        self._timestamps.clear()


async def wait_for_api_dns(
    host: str = "generativelanguage.googleapis.com",
    *,
    resolver=socket.getaddrinfo,
    poll_seconds: float = 1.0,
    timeout: float = 20.0,
) -> bool:
    """Wait for DNS resolution up to `timeout` seconds before giving up and trying anyway."""
    loop = asyncio.get_running_loop()
    start = time.monotonic()
    while True:
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, resolver, host, 443),
                timeout=min(poll_seconds * 2, max(0.5, timeout - (time.monotonic() - start))),
            )
            return True
        except (OSError, asyncio.TimeoutError):
            pass

        if (time.monotonic() - start) >= timeout:
            # Give up waiting and try anyway
            return False
        await asyncio.sleep(poll_seconds)
