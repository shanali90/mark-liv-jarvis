"""Verify that no client_content or user turn is sent while JARVIS is sleeping."""
import ast
import asyncio
from pathlib import Path
import pytest
from core.audio.constants import JarvisState


def test_keep_warm_does_not_send_client_content_in_ast():
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    tree = ast.parse(main_path.read_text(encoding="utf-8"))

    keep_warm_fn = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_run_keep_warm":
            keep_warm_fn = n
            break

    assert keep_warm_fn is not None, "_run_keep_warm function must exist"

    # Verify no call to send_client_content exists inside _run_keep_warm
    client_content_calls = [
        c for c in ast.walk(keep_warm_fn)
        if isinstance(c, ast.Call)
        and (
            (isinstance(c.func, ast.Attribute) and c.func.attr == "send_client_content")
            or (isinstance(c.func, ast.Name) and c.func.id == "send_client_content")
        )
    ]
    assert len(client_content_calls) == 0, (
        f"Found {len(client_content_calls)} send_client_content call(s) inside _run_keep_warm. "
        "Keep-warm must not send user turns to the model."
    )


@pytest.mark.anyio
async def test_keep_warm_runtime_does_not_call_session_send_content():
    from main import JarvisLive

    sent_turns = []

    class MockSession:
        async def send_client_content(self, *args, **kwargs):
            sent_turns.append((args, kwargs))

    class MockLive(JarvisLive):
        def __init__(self):
            self.session = MockSession()
            self.state = JarvisState.SLEEPING

    live = MockLive()

    # Run _run_keep_warm for a short duration
    task = asyncio.create_task(live._run_keep_warm())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(sent_turns) == 0, f"Expected 0 client turns while sleeping, got {sent_turns}"
