import core.net_tuning as net_tuning
import google.genai.live as g_live


def test_net_tuning_applied():
    assert net_tuning.apply_net_tuning() is True
    # Verify wrapped ws_connect supplies default timeouts
    captured = {}
    orig_ws = g_live.ws_connect

    def fake_ws(uri, *args, **kwargs):
        captured.update(kwargs)
        return "connected"

    g_live.ws_connect = fake_ws
    try:
        # Re-apply tuning wrapper on fake_ws
        net_tuning._APPLIED = False
        net_tuning.apply_net_tuning()

        res = g_live.ws_connect("ws://example.com")
        assert res == "connected"
        assert captured.get("open_timeout") == 45
        assert captured.get("ping_interval") == 25
        assert captured.get("ping_timeout") == 60
    finally:
        g_live.ws_connect = orig_ws
