"""While asleep, model audio must be dropped and tool calls refused (the keep-warm
ping made the model talk and open Google by itself)."""
import ast
from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "core" / "audio" / "mixin.py").read_text(encoding="utf-8")
TREE = ast.parse(SRC)


def _method(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def _calls_is_asleep(fn):
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_is_asleep"]


def test_is_asleep_helper_exists():
    assert _method("_is_asleep")


def test_receive_audio_checks_sleep_before_playing_and_before_tools():
    assert len(_calls_is_asleep(_method("_receive_audio"))) >= 2


def test_sleep_refusal_precedes_tool_execution():
    fn = _method("_receive_audio")
    asleep_line = min(c.lineno for c in _calls_is_asleep(fn)
                      if c.lineno > next(n.lineno for n in ast.walk(fn)
                                         if isinstance(n, ast.Attribute) and n.attr == "tool_call"))
    exec_line = next(n.lineno for n in ast.walk(fn)
                     if isinstance(n, ast.Attribute) and n.attr == "_execute_tool")
    assert asleep_line < exec_line
