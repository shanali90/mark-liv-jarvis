from core.reconnect import classify_disconnect, DisconnectKind


def test_bare_1000_in_a_quota_message_is_not_a_planned_close():
    e = RuntimeError("429 RESOURCE_EXHAUSTED: limit is 1000 requests per day")
    assert classify_disconnect(e) != DisconnectKind.PLANNED


def test_real_close_codes_still_recognised():
    assert classify_disconnect(RuntimeError("received 1000 (OK); then sent 1000 (OK)")) == DisconnectKind.PLANNED
    assert classify_disconnect(RuntimeError("sent 1011 (internal error) keepalive ping timeout")) == DisconnectKind.NETWORK
