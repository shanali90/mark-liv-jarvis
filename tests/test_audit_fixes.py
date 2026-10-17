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


# ── Offline "close <app>": no shell string, honest reply, protected processes ─
def test_offline_close_app_never_uses_a_shell_and_reports_truthfully(monkeypatch):
    import subprocess
    import core.offline_engine as oe

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return types.SimpleNamespace(returncode=128)   # taskkill: not running

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, reply = oe._close_app("chrome")
    assert ok is False and "Closed" not in reply, "a failed taskkill must not be reported as success"
    args, kwargs = calls[-1]
    assert args == ["taskkill", "/f", "/im", "chrome.exe"]
    assert not kwargs.get("shell")

    # Shell characters and flags never reach taskkill.
    before = len(calls)
    for bad in ("chrome & del x", "chrome /im lsass", "../x", "", "   "):
        ok, _ = oe._close_app(bad)
        assert ok is False
    assert len(calls) == before, "unsafe names must be refused before running anything"

    # System processes and JARVIS itself are protected.
    for protected in ("explorer", "python", "python.exe", "winlogon"):
        ok, reply = oe._close_app(protected)
        assert ok is False and "won't close" in reply
    assert len(calls) == before

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert oe._close_app("notepad.exe") == (True, "Closed notepad.")


# ── Gmail token: JSON, never pickle; and never committed ────────────────────
def test_gmail_token_is_not_pickled():
    src = (ROOT / "actions" / "gmail.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "pickle" not in imported and "pickle." not in src.replace("# JSON, not pickle", "")
    assert "gmail_token.json" in src


def test_gitignore_covers_oauth_token_files():
    import subprocess
    for name in (
        "config/gmail_token.json",
        "config/gmail_token.pickle",
        "config/api_keys.json",
        "config/settings.json",
    ):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT)
        assert r.returncode == 0, f"{name} must be git-ignored"


# ── open_app: "open WhatsApp" is the app if installed, else the website ─────
def _smart_env(monkeypatch, start_app=None):
    import actions.open_app as oa
    opened = {"urls": [], "apps": []}
    monkeypatch.setattr(oa, "_open_url", lambda url: opened["urls"].append(url) or True)
    monkeypatch.setattr(oa, "_find_start_app", lambda name: start_app)
    monkeypatch.setattr(oa, "_launch_start_app", lambda appid: opened["apps"].append(appid) or True)
    return oa, opened


def test_open_known_service_uses_website_when_app_not_installed(monkeypatch):
    oa, opened = _smart_env(monkeypatch, start_app=None)
    msg = oa._resolve_and_open("WhatsApp")
    assert opened["urls"] == ["https://web.whatsapp.com"] and opened["apps"] == []
    assert "not installed" in msg


def test_open_known_service_prefers_installed_app(monkeypatch):
    oa, opened = _smart_env(monkeypatch, start_app="5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")
    oa._resolve_and_open("whatsapp")
    assert opened["apps"] and opened["urls"] == []


def test_open_domain_opens_https_and_unsafe_names_are_not_urls(monkeypatch):
    import actions.open_app as real
    real_open_url = real._open_url          # before _smart_env replaces it
    oa, opened = _smart_env(monkeypatch)
    oa._resolve_and_open("github dot com")
    assert opened["urls"] == ["https://github.com"]
    for bad in ("file:///etc/passwd", "javascript:alert(1)", "calc.exe & del x", "notepad.exe"):
        assert oa._as_url(bad) is None, bad
    assert real_open_url("file:///c:/windows/system32/calc.exe") is False  # refused before any launch
    # an ordinary app name is not handled by the resolver
    assert oa._resolve_and_open("Calculator") is None


# ── file_organizer: finds duplicates, never deletes, always reversible ──────
def _organizer_env(monkeypatch):
    """A temp folder with old files in it; all state kept in the temp folder."""
    import os
    import tempfile
    import time
    import actions.file_organizer as fo

    tmp = Path(tempfile.mkdtemp(prefix="org_test_"))
    monkeypatch.setattr(fo, "_STATE_DIR", tmp / "_state")
    monkeypatch.setattr(fo, "_allowed", lambda p: str(p).startswith(str(tmp)) and "_blocked" not in str(p))
    root = tmp / "dl"
    root.mkdir()
    old = time.time() - 86400

    def make(rel, data):
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        os.utime(f, (old, old))
        return f
    return fo, root, make


def _all_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_duplicates_are_found_by_content_not_name(monkeypatch):
    fo, root, make = _organizer_env(monkeypatch)
    a = make("report.pdf", b"same bytes " * 100)
    b = make("copy of report (1).pdf", b"same bytes " * 100)
    make("other.pdf", b"different " * 110)          # same size class, different content
    make("empty1.txt", b"")
    make("empty2.txt", b"")
    # Same size and identical first 64 KB, different last byte: NOT duplicates.
    big = b"x" * 70000
    make("video1.mp4", big + b"A")
    make("video2.mp4", big + b"B")
    twin = make("video3.mp4", big + b"A")
    groups = fo.find_duplicates(list(fo._walk(root)))
    names = sorted(sorted(p.name for p in g) for g in groups)
    assert names == sorted([sorted([a.name, b.name]), sorted(["video1.mp4", twin.name])]), names


def test_plan_apply_never_deletes_and_restore_puts_everything_back(monkeypatch):
    fo, root, make = _organizer_env(monkeypatch)
    make("a.jpg", b"img" * 50)
    make("a copy.jpg", b"img" * 50)
    make("notes.txt", b"hello")
    make("setup.exe", b"exe" * 9)
    sub = make("projects/keep/readme.md", b"nested file stays put")
    before = _all_files(root)

    plan = fo.build_plan(root)
    assert plan["moves"], "expected duplicate and sort moves"
    assert all(Path(m["src"]).exists() for m in plan["moves"]), "planning must not move anything"
    assert _all_files(root) == before
    assert any(m["reason"].startswith("duplicate") for m in plan["moves"])
    assert all(Path(m["src"]) != sub for m in plan["moves"]), "files in sub-folders are left alone"

    journal = fo.apply_plan(plan)
    after = _all_files(root)
    assert len(after) == len(before), "no file may be deleted"
    assert sub.exists()
    assert any(f.startswith("_JARVIS_Duplicates") for f in after)
    assert any(f.startswith("Sorted") for f in after)

    msg = fo.restore(plan["id"])
    assert "Restored" in msg and len(journal["done"]) > 0
    assert [f for f in _all_files(root) if not f.startswith(("Sorted", "_JARVIS"))] == before


def test_apply_skips_files_changed_after_planning_and_never_overwrites(monkeypatch):
    fo, root, make = _organizer_env(monkeypatch)
    f = make("notes.txt", b"hello")
    plan = fo.build_plan(root)
    f.write_bytes(b"edited after the plan was made")           # size changed
    journal = fo.apply_plan(plan)
    assert f.exists() and journal["done"] == []
    assert journal["skipped"] and "changed" in journal["skipped"][0]["why"]

    # A name already taken at the destination gets a suffix, never an overwrite.
    fo2, root2, make2 = _organizer_env(monkeypatch)
    make2("notes.txt", b"one")
    taken = make2("Sorted/Documents/notes.txt", b"already here")
    plan2 = fo2.build_plan(root2)
    fo2.apply_plan(plan2)
    assert taken.read_bytes() == b"already here"
    assert (root2 / "Sorted" / "Documents" / "notes (1).txt").read_bytes() == b"one"


def test_organizer_skips_recent_and_protected_files(monkeypatch):
    import os
    import time
    fo, root, make = _organizer_env(monkeypatch)
    fresh = make("download.part.txt", b"still downloading")
    os.utime(fresh, (time.time(), time.time()))               # modified just now
    make("_blocked/secret.txt", b"x")
    make("ok.txt", b"y")
    plan = fo.build_plan(root)
    srcs = {Path(m["src"]).name for m in plan["moves"]}
    assert "download.part.txt" not in srcs, "recently changed files may be in use"
    assert "secret.txt" not in srcs
    assert "ok.txt" in srcs


def test_organizer_plan_ids_cannot_reach_other_paths(monkeypatch):
    fo, root, make = _organizer_env(monkeypatch)
    for bad in ("../../etc/passwd", "..\\x", "a/b", "", "x y"):
        assert fo._load("plan", bad) is None


# ── ui.py: a rejected key must show the key box, and must not wipe settings ──
def _ui_method(name):
    tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in ui.py")


def test_key_prompt_shows_the_window_even_in_stealth_boot():
    fn = _ui_method("_show_setup")
    calls = [n.func.attr for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "show" in calls and "raise_" in calls and "activateWindow" in calls
    first_overlay = min(n.lineno for n in ast.walk(fn)
                        if isinstance(n, ast.Name) and n.id == "SetupOverlay")
    first_show = min(n.lineno for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "show")
    assert first_show < first_overlay, "the window must be shown before the overlay is built"


def test_jarvis_window_remains_visible_while_wake_word_is_enabled():
    tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
    jarvis_ui = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "JarvisUI"
    )
    init = next(
        node for node in jarvis_ui.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    init_calls = [
        node.func.attr
        for node in ast.walk(init)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "showNormal" in init_calls
    assert "activateWindow" in init_calls
    assert not any(
        isinstance(node, ast.Name) and node.id == "get_wake_word_enabled"
        for node in ast.walk(init)
    ), "wake gating must not suppress the visible UI"

    transition = next(
        node for node in jarvis_ui.body
        if isinstance(node, ast.FunctionDef) and node.name == "on_wake_transition"
    )
    transition_text = ast.unparse(transition)
    assert "SHOW_WINDOW" in transition_text
    assert '"HIDE"' not in transition_text


def test_connection_status_uses_a_qt_signal_for_cross_thread_updates():
    tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
    main_window = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
    )
    connection_signal = next(
        node for node in main_window.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_connection_sig"
            for target in node.targets
        )
    )
    assert isinstance(connection_signal.value, ast.Call)
    assert isinstance(connection_signal.value.func, ast.Name)
    assert connection_signal.value.func.id == "pyqtSignal"

    init = next(
        node for node in main_window.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_connection_sig"
        for node in ast.walk(init)
    )

    setter = _ui_method("set_connection_status")
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "emit"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "_connection_sig"
        for node in ast.walk(setter)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "singleShot"
        for node in ast.walk(setter)
    )


def test_saving_a_key_keeps_the_other_settings():
    src = ast.unparse(_ui_method("_on_setup_done"))
    assert "json.dumps({'os_system': os_name}" not in src.replace('"', "'"), \
        "settings.json must be merged, not replaced"
    assert "settings['os_system'] = os_name" in src.replace('"', "'")


def test_wake_shows_a_normal_window_not_forced_fullscreen():
    """Waking JARVIS must not force fullscreen: the user wants the window's own
    minimise / maximise buttons. F11 still toggles fullscreen on request."""
    import ast
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_apply_visibility")
    calls = {c.func.attr for c in ast.walk(fn)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
    assert "showFullScreen" not in calls
    assert "show" in calls and "raise_" in calls
