import pytest
import asyncio
import threading
from core.tools.mixin import ToolMixin
from google.genai import types
from core import audit
from core import confirm as confirm_gate
import json

class MockUI:
    def __init__(self):
        self.muted = False
        self.confirmations = []
        self.logs = []
    def set_state(self, state): pass
    def show_content(self, a, b): pass
    def write_log(self, msg): self.logs.append(msg)
    def show_confirm(self, t, d): self.confirmations.append((t, d))
    def hide_confirm(self): pass
    def click_confirm(self, accepted):
        confirm_gate.resolve(accepted)

class MockReg:
    def has(self, n): return False
    def scheduling(self, n): return None

class MockPlug:
    def has(self, n): return False
    def scheduling(self, n): return None

class MockJARVIS(ToolMixin):
    def __init__(self):
        self.ui = MockUI()
        self._action_registry = MockReg()
        self._plugin_registry = MockPlug()
        confirm_gate.bind(self.ui.show_confirm, self.ui.hide_confirm, self.ui.write_log)

    def set_processing(self, state): pass
    def speak_error(self, name, e): pass

@pytest.fixture(autouse=True)
def isolate_audit_log(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "LOG_DIR", tmp_path)
    monkeypatch.setattr(audit, "AUDIT_LOG_FILE", tmp_path / "audit.jsonl")
    from core import autonomy
    monkeypatch.setattr(autonomy, "is_ask_before_acting", lambda: True)

def test_blocked_action_is_refused():
    async def run_test():
        jarvis = MockJARVIS()
        fc = types.FunctionCall(id="1", name="shutdown_jarvis", args={})
        res = await jarvis._execute_tool(fc)
        assert "User must explicitly confirm" in res.response["result"] or "I cannot confirm" in res.response["result"]
        assert "blocked_trust_ask" in audit.AUDIT_LOG_FILE.read_text(encoding="utf-8")
        confirm_gate.resolve(False)
    asyncio.run(run_test())

def test_audit_record_hash_chain():
    async def run_test():
        jarvis = MockJARVIS()
        fc = types.FunctionCall(id="2", name="system_status", args={})
        await jarvis._execute_tool(fc)

        lines = [json.loads(line) for line in audit.AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) > 0
        for i in range(1, len(lines)):
            assert lines[i]["prev_hash"] == lines[i-1]["hash"]
    asyncio.run(run_test())

def _make_delete_registry(executed, completed):
    class ActionReg:
        def has(self, name): return name == "file_controller"
        def scheduling(self, name): return None
        def run(self, name, args, context):
            executed.append((name, args))
            completed.set()
            return "File deleted."
    return ActionReg()


def test_level_ask_requests_confirmation_before_running():
    async def run_test():
        executed = []
        completed = threading.Event()

        jarvis = MockJARVIS()
        jarvis._action_registry = _make_delete_registry(executed, completed)

        fc = types.FunctionCall(id="3", name="file_controller", args={"action": "delete", "path": "sensitive.txt"})
        res = await jarvis._execute_tool(fc)
        assert "[CONFIRMATION_PENDING]" in res.response["result"]
        assert confirm_gate.pending_title() == "file_controller delete"
        assert jarvis.ui.confirmations == [("file_controller delete", "{'action': 'delete', 'path': 'sensitive.txt'}")]
        assert executed == []
        confirm_gate.resolve(False)
        assert not completed.is_set()
    asyncio.run(run_test())


def test_confirmed_action_runs_from_voice_yes():
    async def run_test():
        executed = []
        completed = threading.Event()
        jarvis = MockJARVIS()
        jarvis._action_registry = _make_delete_registry(executed, completed)

        fc = types.FunctionCall(id="4", name="file_controller", args={"action": "delete", "path": "sensitive.txt"})
        await jarvis._execute_tool(fc)
        assert confirm_gate.resolve_from_text("yes") is True
        assert completed.wait(timeout=2)
        assert len(executed) == 1
        assert executed[0] == ("file_controller", {"action": "delete", "path": "sensitive.txt"})
    asyncio.run(run_test())


def test_confirmed_action_runs_from_ui_button():
    async def run_test():
        executed = []
        completed = threading.Event()
        jarvis = MockJARVIS()
        jarvis._action_registry = _make_delete_registry(executed, completed)

        fc = types.FunctionCall(id="6", name="file_controller", args={"action": "delete", "path": "sensitive.txt"})
        await jarvis._execute_tool(fc)
        jarvis.ui.click_confirm(True)
        assert completed.wait(timeout=2)
        assert len(executed) == 1
        assert executed[0] == ("file_controller", {"action": "delete", "path": "sensitive.txt"})
    asyncio.run(run_test())


def test_voice_no_cancels_pending_action():
    async def run_test():
        executed = []
        completed = threading.Event()
        jarvis = MockJARVIS()
        jarvis._action_registry = _make_delete_registry(executed, completed)

        fc = types.FunctionCall(id="5", name="file_controller", args={"action": "delete", "path": "sensitive.txt"})
        await jarvis._execute_tool(fc)
        assert confirm_gate.resolve_from_text("no") is True
        assert not completed.wait(timeout=0.1)
        assert executed == []
    asyncio.run(run_test())


def test_voice_shutdown_uses_confirmation_and_voice_yes_no():
    async def run_test():
        jarvis = MockJARVIS()
        scheduled = threading.Event()
        jarvis._schedule_confirmed_shutdown = lambda: scheduled.set() or "scheduled"

        assert jarvis._handle_voice_shutdown_request("exit jarvis")
        assert confirm_gate.pending_title() == "Shut down JARVIS"
        assert jarvis.ui.confirmations[-1][0] == "Shut down JARVIS"
        assert confirm_gate.resolve_from_text("no")
        assert not scheduled.wait(timeout=0.1)

        assert jarvis._handle_voice_shutdown_request("quit jarvis")
        assert confirm_gate.resolve_from_text("yes")
        assert scheduled.wait(timeout=2)
    asyncio.run(run_test())
