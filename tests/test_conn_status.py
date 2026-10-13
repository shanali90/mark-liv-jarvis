import sys
import asyncio
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class DummyUI:
    def __init__(self):
        self.muted = False
        self.current_file = None
        self.state_history = []
        self.conn_status_history = []
        self._win = self
        self._ready = True

    def set_state(self, state: str):
        self.state_history.append(("set_state", state))

    def write_log(self, text: str):
        pass

    def set_connection_status(self, status: str, color: str):
        self.conn_status_history.append(status)

    def prompt_reconfig(self):
        pass

    def show_confirm(self, title, text):
        return False

    def hide_confirm(self):
        pass

    def set_audio_level(self, level): pass
    def show_content(self, title, text): pass
    def on_wake_transition(self, state): pass

class MockSession:
    def __init__(self):
        self._receive_queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def send_realtime_input(self, audio):
        pass

    async def receive(self):
        while True:
            msg = await self._receive_queue.get()
            if isinstance(msg, Exception):
                raise msg
            yield msg

class MockClient:
    def __init__(self, **kwargs):
        pass
    class Aio:
        class live:
            @staticmethod
            def connect(model, config):
                # Only return the session initially, then fail the second time
                if getattr(MockClient, "fail_connect", False):
                    raise ConnectionError("Mock network drop")
                return MockSession()
    aio = Aio()

import main
import google.genai
google.genai.Client = MockClient
main.genai.Client = MockClient
main.audio_devices.prefetch = lambda: None
main.get_wake_word_enabled = lambda: False
main._get_api_key = lambda: "mock_key"
try:
    import dashboard.server
    dashboard.server.DashboardServer = lambda *a, **k: None
except Exception:
    pass

def test_conn_status():
    async def _impl():
        ui = DummyUI()
        jarvis = main.JarvisLive(ui)
        jarvis._listen_audio = lambda: asyncio.sleep(3600)
        jarvis._play_audio = lambda: asyncio.sleep(3600)

        # Run jarvis.run() as a background task
        jarvis_task = asyncio.create_task(jarvis.run())

        print("Waiting for initial CONNECTED state...")
        # Wait for the first connection
        for _ in range(50):
            if any("CONNECTED" in s for s in ui.conn_status_history):
                break
            await asyncio.sleep(0.1)

        assert any("CONNECTED" in s for s in ui.conn_status_history), "Never reached CONNECTED state"
        print("PASS: Reached CONNECTED state.")

        print("Simulating network drop...")
        # Cause the connect to fail on the next attempt
        MockClient.fail_connect = True

        # Cancel the active session's task group to force a reconnect loop
        if hasattr(jarvis, "_reconnect_event") and jarvis._reconnect_event:
            jarvis.request_reconnect(keep_context=False, reason="mock drop")

        # Wait for RECONNECTING
        print("Waiting for RECONNECTING state...")
        reconnecting = False
        for _ in range(50):
            if any("RECONNECTING" in s for s in ui.conn_status_history):
                reconnecting = True
                break
            await asyncio.sleep(0.1)

        assert reconnecting, "Did not change to RECONNECTING state after drop"
        print("PASS: Reached RECONNECTING state.")

        print("Simulating network restore...")
        # Restore network and clear backoff so it reconnects quickly in test
        MockClient.fail_connect = False
        jarvis._conn_backoff = 0

        # Wait for it to reconnect
        print("Waiting for restored CONNECTED state...")
        ui.conn_status_history.clear()

        connected_again = False
        for _ in range(100):
            if any("CONNECTED" in s for s in ui.conn_status_history):
                connected_again = True
                break
            await asyncio.sleep(0.1)

        assert connected_again, "Did not change back to CONNECTED state after network restore"
        print("PASS: Reached CONNECTED state after restore.")
        print("test_conn_status: ALL PASS")

        jarvis_task.cancel()
        try:
            await jarvis_task
        except (asyncio.CancelledError, BaseException):
            pass

    asyncio.run(_impl())

if __name__ == "__main__":
    test_conn_status()
