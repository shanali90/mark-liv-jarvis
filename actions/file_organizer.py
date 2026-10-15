"""
actions/file_organizer.py - find duplicates and clutter, then tidy a folder safely.

Three steps, and nothing is changed until the third:

    scan   read-only report: file counts by type, duplicate groups, space a
           cleanup would free. Changes nothing.
    plan   builds a list of MOVES and saves it under a plan id. Changes nothing.
    apply  carries out a saved plan, after the owner has confirmed.
    restore puts every file of an applied plan back where it was.

Safety rules (each one has a test):
    * Nothing is ever deleted. Duplicates are MOVED into a review folder.
    * Only folders inside the safe roots of file_controller are touched; secrets,
      browser profiles, the Startup folder and the project folder never are.
    * Duplicates are proven identical by full SHA-256, not by name or size.
    * Files modified in the last 10 minutes are left alone (probably in use).
    * apply re-checks every file first. If a file changed after the plan was made,
      that move is skipped and reported, never forced.
    * Nothing is overwritten: a name clash gets a numeric suffix.
    * Every applied plan writes a journal, so "restore" works in a later session
      too, not only through the in-memory undo stack.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.undo import push_undo

_STATE_DIR = Path(__file__).resolve().parent.parent / "memory" / "organizer"

SORT_FOLDER = "Sorted"
DUP_FOLDER = "_JARVIS_Duplicates"
MAX_FILES = 20000          # scan stops here, and says so
MAX_MOVES = 500            # one plan never moves more than this
RECENT_SECONDS = 600       # skip files touched in the last 10 minutes
MIN_DUP_BYTES = 1          # empty files are not "duplicates" of each other

_SKIP_DIRS = {".git", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
              "$recycle.bin", "system volume information", "appdata", "windows",
              "program files", "program files (x86)", SORT_FOLDER.lower(), DUP_FOLDER.lower()}

_TYPES = {
    "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic", ".tiff"},
    "Videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Music":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods"},
    "Presentations": {".ppt", ".pptx", ".odp"},
    "Archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Installers": {".exe", ".msi", ".dmg", ".apk", ".iso"},
    "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".cpp", ".java",
                  ".cs", ".go", ".rs", ".sh", ".ipynb"},
}
_EXT_TO_TYPE = {ext: kind for kind, exts in _TYPES.items() for ext in exts}


# ── Safety ──────────────────────────────────────────────────────────────────
def _allowed(path: Path) -> bool:
    """May JARVIS touch this path? Same rule as file_controller (tests replace this)."""
    from actions.file_controller import _is_safe_path
    return _is_safe_path(path)


def _resolve_root(raw: str) -> Path:
    from actions.file_controller import _resolve_path
    return _resolve_path(raw or "downloads")


# ── Scanning ────────────────────────────────────────────────────────────────
def _walk(root: Path):
    """Yield regular files under root. Skips symlinks, hidden/system folders."""
    stack = [root]
    seen = 0
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for p in entries:
            try:
                if p.is_symlink():
                    continue
                if p.is_dir():
                    if p.name.lower() in _SKIP_DIRS or p.name.startswith("."):
                        continue
                    stack.append(p)
                elif p.is_file() and not p.name.startswith("."):
                    seen += 1
                    if seen > MAX_FILES:
                        return
                    yield p
            except OSError:
                continue


def _sha256(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        remaining = limit
        while True:
            n = 1 << 20 if remaining is None else min(1 << 20, remaining)
            if n == 0:
                break
            chunk = f.read(n)
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return h.hexdigest()


def find_duplicates(files: list[Path]) -> list[list[Path]]:
    """Groups of byte-identical files. Size, then first 64 KB, then full SHA-256."""
    by_size: dict[int, list[Path]] = {}
    for p in files:
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size >= MIN_DUP_BYTES:
            by_size.setdefault(size, []).append(p)

    groups: list[list[Path]] = []
    for same_size in by_size.values():
        if len(same_size) < 2:
            continue
        by_head: dict[str, list[Path]] = {}
        for p in same_size:
            try:
                by_head.setdefault(_sha256(p, 65536), []).append(p)
            except OSError:
                continue
        for same_head in by_head.values():
            if len(same_head) < 2:
                continue
            by_full: dict[str, list[Path]] = {}
            for p in same_head:
                try:
                    by_full.setdefault(_sha256(p), []).append(p)
                except OSError:
                    continue
            groups += [sorted(g, key=_keep_order) for g in by_full.values() if len(g) > 1]
    return groups


def _keep_order(p: Path):
    """The copy to KEEP sorts first: oldest, then shortest path, then name."""
    try:
        m = p.stat().st_mtime
    except OSError:
        m = float("inf")
    return (m, len(str(p)), str(p))


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def scan(root: Path) -> dict:
    files = list(_walk(root))
    counts: dict[str, int] = {}
    for p in files:
        kind = _EXT_TO_TYPE.get(p.suffix.lower(), "Other")
        counts[kind] = counts.get(kind, 0) + 1
    dups = find_duplicates(files)
    wasted = 0
    for g in dups:
        for extra in g[1:]:
            try:
                wasted += extra.stat().st_size
            except OSError:
                pass
    return {"files": files, "counts": counts, "dups": dups, "wasted": wasted,
            "truncated": len(files) >= MAX_FILES}


# ── Planning ────────────────────────────────────────────────────────────────
def _unique(dst: Path) -> Path:
    if not dst.exists():
        return dst
    for i in range(1, 1000):
        cand = dst.with_name(f"{dst.stem} ({i}){dst.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(dst)


def build_plan(root: Path, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    result = scan(root)
    moves: list[dict] = []
    claimed: set[Path] = set()
    review = root / DUP_FOLDER / datetime.fromtimestamp(now).strftime("%Y-%m-%d")

    def recent(p: Path) -> bool:
        try:
            return now - p.stat().st_mtime < RECENT_SECONDS
        except OSError:
            return True

    def add(src: Path, dst: Path, reason: str):
        if len(moves) >= MAX_MOVES or src in claimed or recent(src):
            return
        if not (_allowed(src) and _allowed(dst.parent)):
            return
        st = src.stat()
        claimed.add(src)
        moves.append({"src": str(src), "dst": str(dst), "reason": reason,
                      "size": st.st_size, "mtime": st.st_mtime})

    # 1. Duplicates: keep the first copy, move the rest to a review folder.
    for group in result["dups"]:
        for extra in group[1:]:
            add(extra, review / extra.name, f"duplicate of {group[0].name}")

    # 2. Loose top-level files: sort by type into Sorted/<Type>/. Files already in
    #    sub-folders are left where the owner put them.
    for p in root.iterdir():
        try:
            if p.is_file() and not p.is_symlink() and not p.name.startswith(".") and p not in claimed:
                kind = _EXT_TO_TYPE.get(p.suffix.lower(), "Other")
                add(p, root / SORT_FOLDER / kind / p.name, f"sort into {kind}")
        except OSError:
            continue

    return {"id": uuid.uuid4().hex[:8], "root": str(root), "created": now,
            "moves": moves, "wasted": result["wasted"], "truncated": result["truncated"]}


def _save(kind: str, data: dict) -> Path:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _STATE_DIR / f"{kind}_{data['id']}.json"
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def _load(kind: str, plan_id: str) -> dict | None:
    if not plan_id or not plan_id.isalnum():
        return None                      # ids are hex; never build a path from text
    path = _STATE_DIR / f"{kind}_{plan_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ── Applying and restoring ──────────────────────────────────────────────────
def apply_plan(plan: dict) -> dict:
    done, skipped = [], []
    for m in plan["moves"]:
        src, dst = Path(m["src"]), Path(m["dst"])
        try:
            st = src.stat()
            if not src.is_file() or src.is_symlink():
                raise OSError("no longer a regular file")
            if st.st_size != m["size"] or abs(st.st_mtime - m["mtime"]) > 1:
                raise OSError("changed since the plan was made")
            if not (_allowed(src) and _allowed(dst.parent)):
                raise OSError("outside the safe folders")
            dst.parent.mkdir(parents=True, exist_ok=True)
            final = _unique(dst)
            shutil.move(str(src), str(final))
            done.append({"src": str(src), "dst": str(final)})
        except Exception as e:
            skipped.append({"src": str(src), "why": str(e)})
    journal = {"id": plan["id"], "root": plan["root"], "applied": time.time(),
               "done": done, "skipped": skipped}
    if done:
        _save("applied", journal)
        push_undo(f"organized {len(done)} files in {Path(plan['root']).name}",
                  lambda: restore(plan["id"]))
    return journal


def restore(plan_id: str) -> str:
    journal = _load("applied", plan_id)
    if not journal:
        return f"No applied plan '{plan_id}' to restore."
    back, stuck = 0, 0
    for item in reversed(journal["done"]):
        src, cur = Path(item["src"]), Path(item["dst"])
        try:
            if cur.is_file() and not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(cur), str(src))
                back += 1
            else:
                stuck += 1
        except OSError:
            stuck += 1
    note = f" {stuck} could not be moved back (already moved or the original name is taken)." if stuck else ""
    return f"Restored {back} files to where they were.{note}"


# ── Tool entry point ────────────────────────────────────────────────────────
def _describe(plan: dict) -> str:
    dups = [m for m in plan["moves"] if m["reason"].startswith("duplicate")]
    sorts = len(plan["moves"]) - len(dups)
    lines = [f"Plan {plan['id']} for {Path(plan['root']).name}: {len(plan['moves'])} moves "
             f"({len(dups)} duplicates to a review folder, {sorts} files sorted by type). "
             f"Duplicates would free about {_human(plan['wasted'])}. Nothing is deleted."]
    for m in plan["moves"][:5]:
        lines.append(f"  {Path(m['src']).name}  ->  {Path(m['dst']).parent.name}/  ({m['reason']})")
    if len(plan["moves"]) > 5:
        lines.append(f"  ... and {len(plan['moves']) - 5} more")
    if plan["truncated"]:
        lines.append(f"Note: only the first {MAX_FILES} files were scanned.")
    lines.append("To go ahead, say 'apply plan " + plan["id"] + "'.")
    return "\n".join(lines)


def file_organizer(parameters=None, response=None, player=None, session_memory=None) -> str:
    p = parameters or {}
    action = str(p.get("action", "scan")).lower()

    from core.voice_auth import is_guest_mode
    if is_guest_mode():
        return "Action restricted: organizing files is reserved for the owner."

    if action == "restore":
        return restore(str(p.get("plan_id", "")))

    if action == "apply":
        plan = _load("plan", str(p.get("plan_id", "")))
        if not plan:
            return "I don't have that plan. Ask me to plan a cleanup first."
        j = apply_plan(plan)
        msg = f"Moved {len(j['done'])} files."
        if j["skipped"]:
            msg += f" Skipped {len(j['skipped'])} that changed or were not safe to move."
        return msg + " Say 'undo' to put everything back."

    root = _resolve_root(str(p.get("path", "downloads")))
    if not root.is_dir() or not _allowed(root):
        return f"I can't organize {root}: it is not an allowed folder."

    if action == "plan":
        plan = build_plan(root)
        if not plan["moves"]:
            return "Nothing to tidy: no duplicates and no loose files to sort."
        _save("plan", plan)
        return _describe(plan)

    r = scan(root)
    kinds = ", ".join(f"{n} {k}" for k, n in sorted(r["counts"].items(), key=lambda x: -x[1])[:6])
    dup_files = sum(len(g) - 1 for g in r["dups"])
    return (f"{root.name}: {len(r['files'])} files ({kinds or 'none'}). "
            f"{len(r['dups'])} groups of exact duplicates, {dup_files} extra copies, "
            f"about {_human(r['wasted'])} reclaimable. Nothing was changed. "
            f"Ask me to plan a cleanup to see what I would move.")


TOOL = {
    "name": "file_organizer",
    "description": (
        "Finds duplicate and cluttered files and tidies a folder safely. Use for 'clean up my "
        "downloads', 'find duplicate files', 'sort my desktop'. Work in steps: action='scan' "
        "reports duplicates and file types (changes nothing); action='plan' proposes moves and "
        "returns a plan id (changes nothing); read the plan to the owner and ONLY after they say "
        "yes call action='apply' with that plan_id; action='restore' with a plan_id puts files "
        "back. It never deletes: duplicates are moved to a review folder."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "scan, plan, apply or restore"},
            "path": {"type": "STRING", "description": "Folder to work on: downloads (default), desktop, documents, pictures, videos, music, or a path"},
            "plan_id": {"type": "STRING", "description": "Plan id from a previous plan (for apply or restore)"},
        },
        "required": ["action"],
    },
    "handler": file_organizer,
}
