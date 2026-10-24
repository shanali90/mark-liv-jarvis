"""Settings migration utilities for JARVIS UI theme updates."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_ACCENT = "#a78bfa"


def migrate_saved_accent(settings_path: Path | str | None = None,
                         default_accent: str = DEFAULT_ACCENT) -> bool:
    """Migrate saved legacy/gold accent in settings to the new default violet accent.

    Runs exactly once:
    - Backs up the old saved accent as 'previous_ui_color' so the user can select it
      again in Customize.
    - Sets 'ui_color' to default_accent.
    - Sets 'ui_color_migrated' to True.

    Returns:
        True if migration was executed and saved, False if already migrated or file invalid.
    """
    if settings_path is None:
        from ui import SETTINGS_FILE
        target_path = Path(SETTINGS_FILE)
    else:
        target_path = Path(settings_path)

    if not target_path.exists():
        return False

    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    if not isinstance(data, dict):
        return False

    if data.get("ui_color_migrated") is True:
        return False

    # Check for existing accent
    old_color = (data.get("ui_color") or "").strip()
    if old_color:
        data["previous_ui_color"] = old_color

    data["ui_color"] = default_accent.strip().lower()
    data["ui_color_migrated"] = True

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return True
    except Exception:
        return False
