"""Regression tests for the bugs fixed in the fix/audit-1 pass.

Every test here failed before its fix. None of them touches the network, a real
browser, the microphone, or any file outside the temp folder.
"""
import ast
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── Key errors ──────────────────────────────────────────────────────────────
def test_auth_errors_are_recognised():
    from core.conn_errors import is_auth_error

    assert is_auth_error("received 1007 (invalid frame payload data) API key not valid. Please pass a valid API key.")
    assert is_auth_error("400 INVALID_ARGUMENT. {'message': 'API key not valid.'}")
    assert is_auth_error("API key expired. Please renew the API key.")
    assert is_auth_error("403 PERMISSION_DENIED: API key not found")


def test_other_errors_are_not_blamed_on_the_key():
    from core.conn_errors import is_auth_error

    # A bare 1007 is a malformed-request close, not a bad key.
    assert not is_auth_error("received 1007 (invalid frame payload data) realtime_input.media_chunks is deprecated")
    assert not is_auth_error("TimeoutError: timed out")
    assert not is_auth_error("getaddrinfo failed")
    assert not is_auth_error("")
    assert not is_auth_error(None)


# ── Wake word must never leave JARVIS asleep with nothing able to wake it ───
def _stub_audio_deps(monkeypatch):
    for name in ("sounddevice",):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))


def test_wake_falls_back_to_awake_when_detector_cannot_start(monkeypatch):
    _stub_audio_deps(monkeypatch)
    from core.audio.mixin import AudioMixin
    from core.audio.constants import JarvisState

    logs = []

    class Ui:
        def write_log(self, text):
            logs.append(text)

    class Fake(AudioMixin):
        def __init__(self):
            self.ui = Ui()
            self._wake_enabled = True
            self.state = JarvisState.SLEEPING
            self._awake = False

        def _ensure_wake_detector(self):
            return False          # model missing

    j = Fake()
    assert j._wake_available() is False
    assert j._wake_enabled is False, "wake-word mode must switch off for this run"
    assert j._awake is True
    assert j.state == JarvisState.AWAKE
    assert any("Wake word" in line for line in logs), "the user must be told why"


def test_wake_stays_on_when_detector_starts(monkeypatch):
    _stub_audio_deps(monkeypatch)
    from core.audio.mixin import AudioMixin
    from core.audio.constants import JarvisState

    class Fake(AudioMixin):
        def __init__(self):
            self.ui = types.SimpleNamespace(write_log=lambda t: None)
            self._wake_enabled = True
            self.state = JarvisState.SLEEPING
            self._awake = False

        def _ensure_wake_detector(self):
            return True

    j = Fake()
    assert j._wake_available() is True
    assert j._wake_enabled is True and j._awake is False


def test_wake_detector_exception_also_falls_back(monkeypatch):
    _stub_audio_deps(monkeypatch)
    from core.audio.mixin import AudioMixin
    from core.audio.constants import JarvisState

    class Fake(AudioMixin):
        def __init__(self):
            self.ui = types.SimpleNamespace(write_log=lambda t: None)
            self._wake_enabled = True
            self.state = JarvisState.SLEEPING
            self._awake = False

        def _ensure_wake_detector(self):
            raise RuntimeError("onnx exploded")

    j = Fake()
    assert j._wake_available() is False
    assert j._awake is True


# ── open_app: the app name comes from the model and must never reach a shell ─
def test_open_app_never_uses_a_shell(monkeypatch):
    import actions.open_app as oa

    popen_calls = []
    monkeypatch.setattr(oa.subprocess, "Popen", lambda *a, **k: popen_calls.append((a, k)))
    monkeypatch.setattr(oa.time, "sleep", lambda *_: None)
    # Treat any name whose part before the first "." is calc as being on PATH,
    # which is exactly what the old check did.
    monkeypatch.setattr(oa.shutil, "which",
                        lambda n: r"C:\Windows\calc.exe" if n in ("calc.exe", "calc") else None)
    # The Start-menu fallback types real keystrokes; never let a test do that.
    fake_gui = types.SimpleNamespace(PAUSE=0, press=lambda *a: None, write=lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "pyautogui", fake_gui)

    oa._launch_windows("calc.exe & del important.txt")
    assert popen_calls == [], "a name with shell characters must not be executed"

    assert oa._launch_windows("calc.exe") is True
    args, kwargs = popen_calls[-1]
    assert args[0] == [r"C:\Windows\calc.exe"]
    assert not kwargs.get("shell")


def test_open_app_refuses_unsafe_uri_schemes(monkeypatch):
    import actions.open_app as oa

    started = []
    monkeypatch.setattr(oa.os, "startfile", lambda u: started.append(u), raising=False)
    monkeypatch.setattr(oa.shutil, "which", lambda n: None)
    monkeypatch.setattr(oa.time, "sleep", lambda *_: None)
    monkeypatch.setitem(sys.modules, "pyautogui",
                        types.SimpleNamespace(PAUSE=0, press=lambda *a: None, write=lambda *a, **k: None))

    oa._launch_windows("ms-msdt:/id PCWDiagnostic")
    assert started == []
    assert oa._launch_windows("ms-settings:display") is True
    assert started == ["ms-settings:display"]


def test_open_app_alias_match_is_whole_word(monkeypatch):
    import actions.open_app as oa

    monkeypatch.setattr(oa, "_SYSTEM", "Windows")
    assert oa._normalize("edge") == "msedge"
    assert oa._normalize("open google chrome") == "chrome"
    assert oa._normalize("knowledge") == "knowledge"   # used to match "edge"
    assert oa._normalize("a") == "a"                   # used to match anything


# ── desktop_control: model-written code must not be able to escape ──────────
def test_desktop_sandbox_blocks_escapes():
    from actions.desktop import _validate_generated_code as check

    assert check("g = getattr(Path, '__init__')\nprint(g)")
    assert check("print(Path.__init__.__globals__)")
    assert check("print('{0.__class__}'.format(Path))")
    assert check("Path('x').unlink()")
    assert check("Path('x').write_text('a')")
    assert check("import os\nprint(os.getcwd())")
    assert check("print(type(Path))")
    assert check("def broken(:")


def test_desktop_sandbox_allows_plain_inspection():
    from actions.desktop import _validate_generated_code as check, _execute_generated_code

    assert check("p = Path('.')\nprint(sorted(x.name for x in p.iterdir())[:2])") is None
    assert _execute_generated_code("print(len('abc'))") == "3"
    assert "cannot be performed safely" in _execute_generated_code("print(Path.__init__.__globals__)")


# ── file_controller: the home folder is not all fair game ───────────────────
def test_file_controller_protects_secrets_and_the_project():
    from actions import file_controller as fc

    home = Path.home()
    assert not fc._is_safe_path(home / ".ssh" / "id_rsa")
    assert not fc._is_safe_path(home / "AppData" / "Roaming" / "Microsoft" / "Windows"
                                / "Start Menu" / "Programs" / "Startup" / "x.bat")
    assert not fc._is_safe_path(home / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default")
    assert not fc._is_safe_path(ROOT / "main.py")
    assert not fc._is_safe_path(ROOT / "config" / "api_keys.json")
    assert fc._is_safe_path(home / "Desktop" / "notes.txt")
    assert fc._is_safe_path(home / "Downloads" / "a.zip")
    assert "Access denied" in fc.read_file(str(home / ".ssh" / "id_rsa"))


# ── trust: everyday tools do not wait for a spoken yes ──────────────────────
def test_everyday_tools_do_not_ask_but_risky_ones_do():
    from core.safety.trust import get_trust_level, LEVEL_ASK, LEVEL_SILENT, LEVEL_DO_TELL

    assert get_trust_level("weather_report") == LEVEL_SILENT
    assert get_trust_level("open_app") == LEVEL_DO_TELL
    for risky in ("desktop_control", "dev_agent", "code_helper", "adb_control",
                  "game_updater", "social_manager", "send_message", "some_new_tool"):
        assert get_trust_level(risky) == LEVEL_ASK, risky


# ── tests themselves must never open a real browser ─────────────────────────
def test_no_test_opens_a_real_browser():
    """A test that calls browser_control() must take `monkeypatch`, and none may
    call webbrowser.open or launch a visible browser. Opening example.com in the
    owner's real Chrome on every pytest run is what this guards against."""
    offenders = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        if path.name == Path(__file__).name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            params = {a.arg for a in fn.args.args}
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name == "browser_control" and "monkeypatch" not in params:
                    offenders.append(f"{path.name}:{node.lineno} browser_control() without monkeypatch")
                if (name == "open" and isinstance(f, ast.Attribute)
                        and getattr(f.value, "id", "") == "webbrowser"):
                    offenders.append(f"{path.name}:{node.lineno} webbrowser.open")
                for kw in node.keywords:
                    if kw.arg == "headless" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                        offenders.append(f"{path.name}:{node.lineno} visible browser")
    assert not offenders, offenders
