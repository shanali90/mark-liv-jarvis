from core.action_loader import discover_actions
from pathlib import Path
import tempfile
import textwrap

def test_red_action_requires_approval(monkeypatch):
    import core.permissions
    import sys
    # Mock approval queue to always DENY
    monkeypatch.setattr(core.permissions.approval_queue, "request_approval", lambda *args, **kwargs: False)

    old_mod = sys.modules.get("actions.file_controller")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            action_file = tmp_path / "file_controller.py"
            # Create a fake RED action (file_controller.py is mapped to RED)
            action_file.write_text(textwrap.dedent("""
            def handle(parameters, **kwargs):
                return "SUCCESS_DELETED"

            TOOL = {
                "name": "delete_file",
                "description": "Delete a file",
                "parameters": {"type": "OBJECT"},
                "handler": handle
            }
            """))

            registry = discover_actions(tmp_path, logger=lambda x: None)
            assert registry.has("delete_file")

            # Execution should return a failure string because approval is denied
            result = registry.run("delete_file", {"file": "test.txt"})
            assert "Execution of delete_file was denied" in result
    finally:
        if old_mod is not None:
            sys.modules["actions.file_controller"] = old_mod
        else:
            sys.modules.pop("actions.file_controller", None)

def test_green_action_bypasses_approval(monkeypatch):
    import core.permissions
    import sys
    # Mock approval queue to always DENY (if it gets called, it would fail)
    monkeypatch.setattr(core.permissions.approval_queue, "request_approval", lambda *args, **kwargs: False)

    old_mod = sys.modules.get("actions.weather_report")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            action_file = tmp_path / "weather_report.py"
            # Create a fake GREEN action (weather_report.py is mapped to GREEN)
            action_file.write_text(textwrap.dedent("""
            def handle(parameters, **kwargs):
                return "SUCCESS_WEATHER"

            TOOL = {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "OBJECT"},
                "handler": handle
            }
            """))

            registry = discover_actions(tmp_path, logger=lambda x: None)
            assert registry.has("get_weather")

            # Execution should succeed because GREEN doesn't ask for approval
            result = registry.run("get_weather", {"city": "London"})
            assert result == "SUCCESS_WEATHER"
    finally:
        if old_mod is not None:
            sys.modules["actions.weather_report"] = old_mod
        else:
            sys.modules.pop("actions.weather_report", None)
