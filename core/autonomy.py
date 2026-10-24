"""core/autonomy.py - Autonomy policy and announce-then-do execution.

Tiers:
  - TIER_JUST_DO_IT: Reversible/harmless actions executed immediately without asking or banners.
  - TIER_ANNOUNCE_THEN_DO: Announce short sentence, 4-second cancel window by voice or ESC, then do.
  - TIER_ALWAYS_ASK: Irreversible/dangerous actions require spoken yes/no confirmation.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from core.audit import log_action

TIER_JUST_DO_IT = "just_do_it"
TIER_ANNOUNCE_THEN_DO = "announce_then_do"
TIER_ALWAYS_ASK = "always_ask"

_SETTINGS_FILE = Path("config") / "settings.json"
logger = logging.getLogger(__name__)


def is_ask_before_acting() -> bool:
    """Master switch: when True, restores old behaviour (asking for everything)."""
    try:
        if _SETTINGS_FILE.exists():
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return bool(data.get("ask_before_acting", False))
    except Exception:
        pass
    return False


def set_ask_before_acting(enabled: bool) -> None:
    """Save the master switch setting."""
    try:
        data = {}
        if _SETTINGS_FILE.exists():
            try:
                data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["ask_before_acting"] = bool(enabled)
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not persist ask_before_acting: {e}")


# Dangerous operations that always require explicit confirmation
_ALWAYS_ASK_TOOLS = {
    "shutdown_jarvis", "restart_jarvis", "payment", "security_settings",
    "permanent_delete",
}
_ALWAYS_ASK_OPERATIONS = {
    "restart", "shutdown", "power_off", "execute_code", "run_code",
    "payment", "pay", "purchase", "buy", "checkout", "place_order",
    "transfer", "transfer_money", "install", "install_software",
}
_SENSITIVE_UI_TEXT = {
    "pay", "buy", "transfer", "delete", "shutdown", "checkout", "purchase",
}

# Operations that announce then wait 4s for cancel
_ANNOUNCE_TOOLS = {
    "send_message", "mail_send", "send_email", "send_mail", "social_post",
}
_ANNOUNCE_OPERATIONS = {
    "delete", "delete_file", "remove", "toggle_wifi", "wifi_off",
    "close_window", "close_app", "force_quit", "mail_trash",
}


def _normalise(val) -> str:
    return str(val or "").strip().lower().replace("-", "_").replace(" ", "_")


def get_autonomy_tier(tool_name: str, action: str = None, args: dict | None = None) -> str:
    """Classify tool action into JUST_DO_IT, ANNOUNCE_THEN_DO, or ALWAYS_ASK."""
    tool = _normalise(tool_name)
    op = _normalise(action)
    args = args or {}

    # If master switch is ON, restore old strict asking behavior
    if is_ask_before_acting():
        from core.safety.trust import get_trust_level, LEVEL_ASK
        lvl = get_trust_level(tool_name, action, args=args)
        if lvl == LEVEL_ASK:
            return TIER_ALWAYS_ASK
        return TIER_JUST_DO_IT

    # 1. ALWAYS ASK
    if tool in _ALWAYS_ASK_TOOLS or tool in _ALWAYS_ASK_OPERATIONS or op in _ALWAYS_ASK_TOOLS or op in _ALWAYS_ASK_OPERATIONS:
        return TIER_ALWAYS_ASK

    if tool == "file_processor" and op in {"execute_code"}:
        return TIER_ALWAYS_ASK

    if tool in {"computer_control", "browser_control"}:
        if op in {"click", "smart_click", "screen_click", "submit"}:
            ui_text = " ".join(
                str(args.get(k, "")) for k in
                ("description", "selector", "button", "label", "target", "intent", "text")
            ).lower()
            if any(w in ui_text for w in _SENSITIVE_UI_TEXT):
                return TIER_ALWAYS_ASK

    # 2. ANNOUNCE, THEN DO
    if tool in _ANNOUNCE_TOOLS or tool in _ANNOUNCE_OPERATIONS or op in _ANNOUNCE_TOOLS or op in _ANNOUNCE_OPERATIONS:
        return TIER_ANNOUNCE_THEN_DO

    if tool == "computer_settings" and op in {"toggle_wifi", "wifi_off", "close_window", "close_app"}:
        return TIER_ANNOUNCE_THEN_DO

    # 3. JUST DO IT (default for all other actions)
    return TIER_JUST_DO_IT


def format_announcement(name: str, action: str, args: dict) -> str:
    """Generate the one short sentence announcement before executing."""
    tool = _normalise(name)
    op = _normalise(action)

    if tool == "send_message":
        rcv = args.get("receiver") or "contact"
        txt = args.get("message_text") or ""
        prev = (txt[:25] + "...") if len(txt) > 25 else txt
        plat = args.get("platform", "WhatsApp").title()
        return f"Sending '{prev}' to {rcv} on {plat} - say cancel to stop."

    if tool in ("mail_send", "send_email", "send_mail"):
        rcv = args.get("recipient") or args.get("to") or "recipient"
        return f"Sending email to {rcv} - say cancel to stop."

    if tool == "social_post":
        plat = args.get("platform", "social media").title()
        return f"Posting update to {plat} - say cancel to stop."

    if op in ("delete", "delete_file", "remove", "mail_trash"):
        fname = args.get("name") or args.get("path") or "file"
        return f"Deleting '{fname}' to Recycle Bin - say cancel to stop."

    if op in ("toggle_wifi", "wifi_off"):
        return "Turning Wi-Fi off - say cancel to stop."

    if op in ("close_window", "close_app", "force_quit"):
        app = args.get("app_name") or args.get("name") or "window"
        return f"Closing {app} - say cancel to stop."

    return f"Performing {name} {action or ''} - say cancel to stop."


def announce_and_wait(
    name: str,
    action: str,
    args: dict,
    speak_cb: Optional[Callable[[str], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    timeout: float = 4.0,
) -> tuple[bool, str]:
    """Announce action, wait 4 seconds for voice or ESC cancellation.
    
    Returns (True, "proceed") or (False, "NOT DONE: action cancelled by user").
    """
    from actions.send_message import (
        set_action_pending, reset_action_abort, is_action_aborted, abort_current_action
    )

    announcement = format_announcement(name, action, args)

    if log_cb:
        try:
            log_cb(f"SYS: {announcement}")
        except Exception:
            pass

    if speak_cb:
        try:
            speak_cb(announcement)
        except Exception as e:
            logger.warning(f"Could not speak announcement: {e}")

    # Set pending action flag for cancel word detection
    set_action_pending(True)
    reset_action_abort()

    log_action("JARVIS", "action_announced", name, args, "AWAITING_CANCEL")

    end = time.monotonic() + timeout
    cancelled = False

    while time.monotonic() < end:
        # Check voice abort
        if is_action_aborted():
            cancelled = True
            break

        # Check ESC keypress on Windows
        if sys.platform == "win32":
            try:
                import ctypes
                if ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000:
                    abort_current_action()
                    cancelled = True
                    break
            except Exception:
                pass

        time.sleep(0.05)

    set_action_pending(False)

    if cancelled:
        log_action("JARVIS", "action_cancelled_by_user", name, args, "CANCELLED")
        return False, "NOT DONE: action cancelled by user"

    log_action("JARVIS", "action_confirmed_no_cancel", name, args, "PROCEED")
    return True, "proceed"
