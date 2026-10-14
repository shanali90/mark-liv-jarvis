import json
import logging
from pathlib import Path

# Autonomy levels per action type
LEVEL_ASK = "L0_ASK"           # Always asks and shows the content first
LEVEL_DRAFT = "L1_DRAFT"       # Prepares everything, owner approves with one word
LEVEL_DO_TELL = "L2_DO_TELL"   # Acts, then reports immediately; undo is available
LEVEL_SILENT = "L3_SILENT"     # Acts and logs, reports in the summary

DEFAULT_POLICY = {
    # Default trust levels as defined in the master plan
        # Base tools
    "web_search": LEVEL_SILENT,
    "screen_process": LEVEL_SILENT,
    "save_memory": LEVEL_SILENT,
    "recall_memory": LEVEL_SILENT,
    "system_status": LEVEL_SILENT,
    "manage_monitor": LEVEL_DO_TELL,
    "change_voice": LEVEL_DO_TELL,
    "enroll_voice": LEVEL_DO_TELL,
    "close_camera": LEVEL_SILENT,
    "undo": LEVEL_DO_TELL,
    "shutdown_jarvis": LEVEL_ASK,
    "computer_control": LEVEL_ASK,
    "browser_control": LEVEL_ASK,
    "file_controller": LEVEL_ASK,
    "file_processor": LEVEL_SILENT,
    # Everyday read-only or low-impact tools. Tools missing from this table fall
    # back to ASK, which made "weather in Karachi" and "open Chrome" wait for a
    # spoken yes every time.
    "weather_report": LEVEL_SILENT,
    "flight_finder": LEVEL_SILENT,
    "open_app": LEVEL_DO_TELL,
    "switch_to_window": LEVEL_DO_TELL,
    "youtube_video": LEVEL_DO_TELL,
    "reminder": LEVEL_DO_TELL,
    "mail_read": LEVEL_SILENT,
    "mail_search": LEVEL_SILENT,
    "mail_triage_run": LEVEL_SILENT,
    "mail_organize": LEVEL_DO_TELL,
    "mail_draft": LEVEL_DO_TELL,
    "mail_send": LEVEL_ASK,
    "mail_trash": LEVEL_DO_TELL,
    "mail_trash_bulk": LEVEL_ASK,
    "calendar_read": LEVEL_SILENT,
    "calendar_create_self": LEVEL_DO_TELL,
    "calendar_create_others": LEVEL_ASK,
    "social_post": LEVEL_ASK,
    "security_settings": LEVEL_ASK,
    "payment": LEVEL_ASK,
    "permanent_delete": LEVEL_ASK,
}

_TRUST_PATH = Path("memory") / "trust_policy.json"

_SETTINGS_ACTIONS = {
    "volume_up", "volume_down", "volume_set", "mute", "unmute",
    "toggle_mute", "brightness_up", "brightness_down", "brightness_set",
    "dark_mode", "toggle_wifi",
}
_FILE_CHANGE_ACTIONS = {"delete", "delete_file", "remove", "move", "move_file", "rename", "rename_file"}
_SENSITIVE_ACTIONS = {
    "send", "send_email", "send_message", "send_mail", "mail_send",
    "social_post", "payment", "pay", "purchase", "buy", "checkout",
    "place_order", "transfer", "transfer_money",
}
_SENSITIVE_UI_TEXT = {
    "send", "send email", "send message", "send now", "post",
    "pay", "pay now", "payment", "purchase", "purchase now", "buy",
    "buy now", "checkout", "place order", "complete purchase", "transfer",
}


def _normalise(value) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def get_trust_level(
    tool_name: str,
    action: str = None,
    account: str = None,
    recipient: str = None,
    args: dict | None = None,
) -> str:
    """Gets the defined trust level for an action."""
    policy = DEFAULT_POLICY.copy()
    try:
        if _TRUST_PATH.exists():
            user_policy = json.loads(_TRUST_PATH.read_text(encoding="utf-8"))
            if not isinstance(user_policy, dict):
                raise ValueError("trust policy must contain a JSON object")
            policy.update(user_policy)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logging.getLogger(__name__).warning(
            "Could not load trust policy from %s; using safe defaults: %s",
            _TRUST_PATH, e,
        )

    tool = _normalise(tool_name)
    operation = _normalise(action)
    if tool in {
        "shutdown_jarvis", "restart_jarvis", "mail_send", "send_email",
        "send_message", "send_mail", "social_post", "payment",
        "permanent_delete",
    }:
        return LEVEL_ASK

    if operation in _SENSITIVE_ACTIONS:
        return LEVEL_ASK

    if tool == "computer_settings":
        if operation in _SETTINGS_ACTIONS or operation in {"restart", "shutdown"}:
            return LEVEL_ASK
        return LEVEL_DO_TELL

    if tool == "file_controller":
        return LEVEL_ASK if operation in _FILE_CHANGE_ACTIONS else LEVEL_DO_TELL

    if tool in {"computer_control", "browser_control"}:
        if args and operation in {
            "click", "smart_click", "submit", "press", "press_key",
            "screen_click",
        }:
            ui_text = " ".join(
                str(args.get(key, "")) for key in
                ("description", "selector", "button", "label", "target", "intent", "text")
            ).strip().lower()
            if any(label in ui_text for label in _SENSITIVE_UI_TEXT):
                return LEVEL_ASK
        return LEVEL_DO_TELL

    if tool == "file_processor":
        return LEVEL_ASK if operation in {"execute_code"} else LEVEL_DO_TELL

    action_type = tool
    if tool in {"shutdown_jarvis", "restart_jarvis", "payment", "social_post"}:
        action_type = tool
    elif tool == "security_settings":
        return LEVEL_ASK

    return policy.get(action_type, LEVEL_ASK)

def promote_trust(action_type: str, new_level: str) -> bool:
    """Updates the trust policy after owner approval."""
    if action_type in ("permanent_delete", "payment", "security_settings"):
        return False

    policy = {}
    if _TRUST_PATH.exists():
        try:
            policy = json.loads(_TRUST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logging.getLogger(__name__).warning(
                "Could not read trust policy from %s: %s", _TRUST_PATH, e,
            )
            return False

    policy[action_type] = new_level
    _TRUST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TRUST_PATH.write_text(json.dumps(policy, indent=4), encoding="utf-8")
    return True

def get_policy_summary() -> str:
    """Returns a readable summary of current trust levels."""
    policy = DEFAULT_POLICY.copy()
    try:
        if _TRUST_PATH.exists():
            user_policy = json.loads(_TRUST_PATH.read_text(encoding="utf-8"))
            policy.update(user_policy)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logging.getLogger(__name__).warning(
            "Could not load trust policy from %s; using safe defaults: %s",
            _TRUST_PATH, e,
        )

    summary = ["Current Trust Policy:"]
    for k, v in policy.items():
        summary.append(f" - {k}: {v}")
    return "\n".join(summary)
