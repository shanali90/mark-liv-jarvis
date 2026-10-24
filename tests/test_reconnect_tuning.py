from core.reconnect import (
    DisconnectKind,
    classify_disconnect,
    ReconnectBackoff,
    ErrorLogLimiter,
    unwrap_exception,
)


def test_classify_disconnect_network_errors():
    class ConnectionClosedError(Exception):
        pass

    errors = [
        TimeoutError("timed out during opening handshake"),
        ConnectionClosedError("sent 1011 (internal error) keepalive ping timeout"),
        OSError("[WinError 64] The specified network name is no longer available"),
        RuntimeError("1006 None. abnormal closure [internal]"),
        RuntimeError("Temporary failure in name resolution"),
    ]
    for err in errors:
        assert classify_disconnect(err) == DisconnectKind.NETWORK


def test_reconnect_backoff_progression_and_reset():
    backoff = ReconnectBackoff()
    assert backoff.next_delay() == 2
    assert backoff.next_delay() == 4
    assert backoff.next_delay() == 8
    assert backoff.next_delay() == 15
    assert backoff.next_delay() == 15  # capped at 15

    # Short session (<30s) does not reset backoff
    assert not backoff.reset_after_session(10.0)
    assert backoff.next_delay() == 15

    # Stable session (>30s) resets to minimum (2)
    assert backoff.reset_after_session(35.0)
    assert backoff.next_delay() == 2


def test_error_log_limiter_and_unwrap_exception():
    limiter = ErrorLogLimiter(interval=60.0)
    err1 = OSError("Network name no longer available")
    eg = ExceptionGroup("group", [err1])

    unwrapped = unwrap_exception(eg)
    assert unwrapped is err1

    t0 = 1000.0
    assert limiter.should_log(eg, now=t0) is True
    assert limiter.should_log(err1, now=t0 + 5.0) is False
    assert limiter.should_log(err1, now=t0 + 65.0) is True
