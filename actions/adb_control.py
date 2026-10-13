import subprocess
import logging

logger = logging.getLogger(__name__)

def _run_adb(args: list[str]) -> str:
    try:
        res = subprocess.run(["adb"] + args, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except FileNotFoundError:
        return "ADB is not installed or not in PATH."
    except subprocess.CalledProcessError as e:
        return f"ADB command failed: {e.stderr}"

def adb_control(parameters: dict, **kwargs) -> str:
    action = parameters.get("action")
    
    if action == "list_devices":
        return _run_adb(["devices"])
    elif action == "shell":
        cmd = parameters.get("command", "")
        return _run_adb(["shell", cmd])
    elif action == "tap":
        x = parameters.get("x")
        y = parameters.get("y")
        return _run_adb(["shell", "input", "tap", str(x), str(y)])
    elif action == "type":
        text = parameters.get("text", "")
        # replace spaces with %s for adb input
        text = text.replace(" ", "%s")
        return _run_adb(["shell", "input", "text", text])
    elif action == "swipe":
        x1, y1 = parameters.get("x1"), parameters.get("y1")
        x2, y2 = parameters.get("x2"), parameters.get("y2")
        duration = parameters.get("duration", 300)
        return _run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
    elif action == "home":
        return _run_adb(["shell", "input", "keyevent", "3"])
    elif action == "back":
        return _run_adb(["shell", "input", "keyevent", "4"])
    else:
        return f"Unknown ADB action: {action}"

TOOL = {
    "name": "adb_control",
    "description": "Control an Android device via ADB (list_devices, tap, type, swipe, home, back, shell).",
    "safety": "YELLOW",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list_devices, tap, type, swipe, home, back, or shell"},
            "x": {"type": "INTEGER"},
            "y": {"type": "INTEGER"},
            "x1": {"type": "INTEGER"},
            "y1": {"type": "INTEGER"},
            "x2": {"type": "INTEGER"},
            "y2": {"type": "INTEGER"},
            "text": {"type": "STRING"},
            "command": {"type": "STRING", "description": "Shell command to run"},
            "duration": {"type": "INTEGER", "description": "Swipe duration in ms"}
        },
        "required": ["action"]
    },
    "handler": adb_control
}
