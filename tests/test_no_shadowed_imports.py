"""A local `import X` inside a function makes X local for the WHOLE function, so
any use of X earlier in that function raises UnboundLocalError at run time.
pyflakes does not report it. This happened in core/audio/mixin.py _receive_audio
(a local `from datetime import datetime` added after an earlier datetime use) and
made the live session crash with 'Session error (UnboundLocalError)'."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".venv", "venv", "__pycache__", "tests", "node_modules", ".git"}


def _offenders():
    for p in ROOT.rglob("*.py"):
        if SKIP & set(p.relative_to(ROOT).parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            imps = {}
            for n in ast.walk(fn):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    for a in n.names:
                        imps.setdefault((a.asname or a.name).split(".")[0], []).append(n.lineno)
            for name, lines in imps.items():
                first = min(lines)
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Name) and n.id == name
                            and isinstance(n.ctx, ast.Load) and n.lineno < first):
                        yield f"{p.relative_to(ROOT)}:{n.lineno} uses '{name}' in {fn.name}() before local import at {first}"
                        break


def test_no_name_is_used_before_its_local_import():
    assert list(_offenders()) == []
