"""Tests for planned reconnect rate limiting and formatted disconnect reasons."""
from core.reconnect import PlannedReconnectLimiter, format_disconnect_reason


def test_planned_reconnect_limiter_rate_limits_after_three_in_20s():
    limiter = PlannedReconnectLimiter(max_count=3, window_seconds=20.0)
    t0 = 1000.0

    # First 3 within 20s should NOT back off (they are allowed immediate retry)
    assert limiter.record_and_should_backoff(now=t0) is False
    assert limiter.record_and_should_backoff(now=t0 + 2.0) is False
    assert limiter.record_and_should_backoff(now=t0 + 5.0) is False

    # 4th within 20s MUST back off
    assert limiter.record_and_should_backoff(now=t0 + 8.0) is True

    # 5th within 20s also backs off
    assert limiter.record_and_should_backoff(now=t0 + 10.0) is True

    # After window passes (>20s), counter clears and immediate retries allowed again
    assert limiter.record_and_should_backoff(now=t0 + 35.0) is False


def test_format_disconnect_reason_includes_class_code_and_redacts_keys():
    class DummyAPIError(Exception):
        def __init__(self, code, msg):
            super().__init__(msg)
            self.code = code
            self.message = msg

    # Sensitive key inside message
    err = DummyAPIError(
        429,
        "RESOURCE_EXHAUSTED: quota exceeded for key AIzaSyD9876543210123456789012345678901 on model gemini-pro "
        "details: rate limit 15 RPM exceeded"
    )

    reason = format_disconnect_reason(err, max_message_len=150)
    assert "DummyAPIError" in reason
    assert "429" in reason
    assert "AIza" not in reason
    assert "[REDACTED]" in reason
    assert len(reason) <= 200


def test_format_disconnect_reason_websocket_close_code_1006():
    class DummyCloseError(Exception):
        def __init__(self, code, msg):
            super().__init__(msg)
            self.code = code

    err = DummyCloseError(1006, "1006 None. abnormal closure [internal]")
    reason = format_disconnect_reason(err)
    assert "DummyCloseError" in reason
    assert "1006" in reason
    assert "abnormal closure" in reason
