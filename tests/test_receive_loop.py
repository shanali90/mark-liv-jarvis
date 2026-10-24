"""Unit test for the live receive loop in AudioMixin._receive_audio.

Exercises:
(a) user transcript with dashboard enabled
(b) model audio chunk enqueued
(c) tool call execution and response dispatch
(d) turn_complete handling

Validates that current AudioMixin passes with no exception,
and verifies that commit aa4bfe7 fails with UnboundLocalError.
"""
import asyncio
import subprocess
import types as pytypes
from types import SimpleNamespace
import pytest
from google.genai import types
from core.audio.constants import JarvisState
from core.audio.mixin import AudioMixin


class FakeDashboard:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, payload):
        self.broadcasts.append(payload)


class FakeSession:
    def __init__(self, responses):
        self._responses = responses
        self.sent_tool_responses = []

    async def receive(self):
        for r in self._responses:
            yield r
        await asyncio.sleep(0.05)
        raise asyncio.CancelledError()

    async def send_tool_response(self, function_responses):
        self.sent_tool_responses.append(function_responses)


def _make_fake_assistant_class(base_mixin):
    class FakeLiveAssistant(base_mixin):
        def __init__(self, session, dashboard):
            self.session = session
            self.audio_in_queue = asyncio.Queue()
            self.out_queue = asyncio.Queue(maxsize=200)
            self._turn_done_event = asyncio.Event()
            self._interrupted = False
            self._visemes = SimpleNamespace(feed_text=lambda t: None, reset=lambda: None)
            self._last_user_speech = 0.0
            self._last_out_logged = ""
            self._asst_name = "JARVIS"
            self._session_log = []
            self._dashboard = dashboard
            self._vision_close_pending = False
            self._vision_busy = False
            self._resume_handle = None
            self._wake_enabled = False
            self._awake = True
            self.state = JarvisState.AWAKE
            self.tool_calls_executed = []
            self.logged_lines = []
            self.ui = SimpleNamespace(
                write_log=lambda msg: self.logged_lines.append(msg),
                set_emotion_from_text=lambda t: None,
                stop_camera_stream=lambda: None,
            )

        def _handle_voice_shutdown_request(self, text):
            return False

        async def _execute_tool(self, fc):
            self.tool_calls_executed.append(fc)
            return types.FunctionResponse(
                name=fc.name,
                id=fc.id,
                response={"result": "clear and 25C"},
            )

        async def _flush_pending_vision(self):
            return True

    return FakeLiveAssistant


def _build_scripted_responses():
    return [
        # (a) user transcript
        SimpleNamespace(
            session_resumption_update=None,
            data=None,
            server_content=SimpleNamespace(
                output_transcription=None,
                input_transcription=SimpleNamespace(text="What is the forecast?"),
                turn_complete=False,
            ),
            tool_call=None,
        ),
        # (b) model audio
        SimpleNamespace(
            session_resumption_update=None,
            data=b"\x01\x00" * 2400,
            server_content=None,
            tool_call=None,
        ),
        # (d) turn_complete on speech (triggers dashboard broadcast and user log)
        SimpleNamespace(
            session_resumption_update=None,
            data=None,
            server_content=SimpleNamespace(
                output_transcription=SimpleNamespace(text="Let me check the weather."),
                input_transcription=None,
                turn_complete=True,
            ),
            tool_call=None,
        ),
        # (c) tool call
        SimpleNamespace(
            session_resumption_update=None,
            data=None,
            server_content=None,
            tool_call=SimpleNamespace(
                function_calls=[
                    SimpleNamespace(name="weather_report", args={"city": "Larkana"}, id="call_weather_1")
                ]
            ),
        ),
        # (d) final turn_complete after tool execution
        SimpleNamespace(
            session_resumption_update=None,
            data=None,
            server_content=SimpleNamespace(
                output_transcription=SimpleNamespace(text="It is clear and 25C in Larkana."),
                input_transcription=None,
                turn_complete=True,
            ),
            tool_call=None,
        ),
    ]


@pytest.mark.anyio
async def test_receive_audio_loop_scripted_responses():
    dashboard = FakeDashboard()
    session = FakeSession(_build_scripted_responses())
    cls = _make_fake_assistant_class(AudioMixin)
    jarvis = cls(session, dashboard)

    try:
        await jarvis._receive_audio()
    except asyncio.CancelledError:
        pass

    await asyncio.sleep(0.05)

    # 1. Model audio enqueued
    assert jarvis.audio_in_queue.qsize() > 0, "Model audio chunk was not enqueued"

    # 2. Tool call executed
    assert len(jarvis.tool_calls_executed) == 1, "Tool call was not executed"
    assert jarvis.tool_calls_executed[0].name == "weather_report"

    # 3. Tool response sent back to session
    assert len(session.sent_tool_responses) == 1, "Tool response was not sent to session"

    # 4. Dashboard broadcasts sent for user and assistant messages
    assert len(dashboard.broadcasts) >= 2, f"Expected dashboard broadcasts, got {dashboard.broadcasts}"
    speakers = [b.get("speaker") for b in dashboard.broadcasts]
    assert "user" in speakers
    assert "jarvis" in speakers


@pytest.mark.anyio
async def test_receive_audio_loop_fails_on_commit_aa4bfe7():
    """Verify that the previous commit aa4bfe7 fails with UnboundLocalError."""
    res = subprocess.run(
        ["git", "show", "aa4bfe7:core/audio/mixin.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if res.returncode != 0:
        pytest.skip("Commit aa4bfe7 not found in git history")

    mod = pytypes.ModuleType("old_mixin")
    exec(compile(res.stdout, "core/audio/mixin.py", "exec"), mod.__dict__)
    old_mixin = mod.AudioMixin

    dashboard = FakeDashboard()
    session = FakeSession(_build_scripted_responses())
    cls = _make_fake_assistant_class(old_mixin)
    jarvis = cls(session, dashboard)

    with pytest.raises(UnboundLocalError) as exc_info:
        await jarvis._receive_audio()

    assert "datetime" in str(exc_info.value)
