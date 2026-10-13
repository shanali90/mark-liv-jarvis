from __future__ import annotations

import json
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

SECRET_NAME = re.compile(r"(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|secret|token)$", re.I)
ENV_NAME = re.compile(r"(?:API[_-]?KEY|CLIENT[_-]?SECRET|ACCESS[_-]?TOKEN|REFRESH[_-]?TOKEN|PASSWORD|SECRET|TOKEN)$", re.I)


def _json_credentials(value, prefix: str = ""):
    if isinstance(value, dict):
        for name, child in value.items():
            path = f"{prefix}_{name}" if prefix else str(name)
            if isinstance(child, str) and child and SECRET_NAME.search(str(name)):
                yield path, child
            else:
                yield from _json_credentials(child, path)


def _env_credentials(path: Path):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        name, separator, value = line.partition("=")
        if separator and ENV_NAME.search(name.strip()):
            value = value.strip().strip("\"'")
            if value:
                yield name.strip(), value


def _legacy_files() -> list[Path]:
    candidates = {
        ROOT / "config" / "api_keys.json",
        ROOT / "config" / "settings.json",
    }
    for base in (ROOT, ROOT / "config", ROOT / "plugins"):
        if base.exists():
            candidates.update(base.glob(".env*"))
            candidates.update(base.glob("client_secret*.json"))
            candidates.update(base.glob("token*.json"))
    return sorted(path for path in candidates if path.is_file())


def main() -> int:
    from core.vault import set_secret

    parser = argparse.ArgumentParser(
        description="Move local legacy credentials into the OS keychain."
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="legacy credential files; defaults to known project-local locations",
    )
    args = parser.parse_args()
    migrated = 0
    failed = []
    files = sorted(
        path.resolve() for path in args.files
    ) if args.files else _legacy_files()
    for path in files:
        try:
            if path.suffix.lower() == ".json":
                content = json.loads(path.read_text(encoding="utf-8"))
                credentials = _json_credentials(content)
            else:
                credentials = _env_credentials(path)
            for name, value in credentials:
                name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
                if not name:
                    continue
                if not set_secret(name, value):
                    failed.append(str(path))
                else:
                    migrated += 1
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"Could not migrate {path.name} ({type(exc).__name__}); inspect it locally.")
            failed.append(str(path))

    print(f"Migrated credentials: {migrated}")
    if files:
        print("After checking migration locally, delete these legacy files:")
        for path in files:
            try:
                display_path = path.relative_to(ROOT).as_posix()
            except ValueError:
                display_path = str(path)
            print(display_path)
    else:
        print("No legacy credential files found.")
    if failed:
        print("Migration failed for one or more files; do not delete those files yet.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
