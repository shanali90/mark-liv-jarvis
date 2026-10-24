"""Network tuning for weak/unstable internet connections."""
from __future__ import annotations

import functools
import logging

logger = logging.getLogger(__name__)

_APPLIED = False


def apply_net_tuning() -> bool:
    """Wrap google.genai.live websocket connect to use relaxed timeouts."""
    global _APPLIED
    if _APPLIED:
        return True

    try:
        import google.genai.live as g_live
    except ImportError:
        return False

    orig_ws_connect = getattr(g_live, "ws_connect", None)
    if orig_ws_connect is None:
        return False

    @functools.wraps(orig_ws_connect)
    def tuned_ws_connect(uri: str, *args, **kwargs):
        kwargs.setdefault("open_timeout", 45)
        kwargs.setdefault("ping_interval", 25)
        kwargs.setdefault("ping_timeout", 60)
        return orig_ws_connect(uri, *args, **kwargs)

    g_live.ws_connect = tuned_ws_connect

    # Also wrap websockets.asyncio.client.connect if present so any direct usage is tuned
    try:
        import websockets.asyncio.client as ws_client
        if hasattr(ws_client, "connect"):
            orig_ws_client_connect = ws_client.connect

            @functools.wraps(orig_ws_client_connect)
            def tuned_client_connect(uri: str, *args, **kwargs):
                kwargs.setdefault("open_timeout", 45)
                kwargs.setdefault("ping_interval", 25)
                kwargs.setdefault("ping_timeout", 60)
                return orig_ws_client_connect(uri, *args, **kwargs)

            ws_client.connect = tuned_client_connect
    except Exception:
        pass

    _APPLIED = True
    return True


# Apply immediately upon module import
apply_net_tuning()
