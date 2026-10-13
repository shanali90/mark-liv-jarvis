import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

# ── Global Action Kill-Switch ────────────────────────────────────────────────
_ABORT_EVENT = threading.Event()

def abort_current_action() -> None:
    """Set the kill-switch flag to abort any running automation immediately."""
    _ABORT_EVENT.set()
    print("[SendMessage] 🛑 Kill-switch activated! Aborting pending action.")

def reset_action_abort() -> None:
    """Reset the kill-switch flag before starting a new action."""
    _ABORT_EVENT.clear()

def is_action_aborted() -> bool:
    """Return True if an abort has been requested."""
    return _ABORT_EVENT.is_set()


def _sleep_interruptible(seconds: float) -> bool:
    """Sleep in short 50ms slices checking for abort. Returns True if aborted."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if is_action_aborted():
            return True
        time.sleep(0.05)
    return is_action_aborted()


def _is_window_focused(expected_keywords: list[str]) -> bool:
    """Verify that the currently active/foreground window matches expected app keywords."""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return False
        title = win32gui.GetWindowText(hwnd).lower()
        return any(k.lower() in title for k in expected_keywords)
    except Exception:
        # Fallback to pygetwindow if win32gui is unavailable
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            if active and active.title:
                title = active.title.lower()
                return any(k.lower() in title for k in expected_keywords)
        except Exception:
            pass
        return True  # Soft pass if neither inspection library works


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    from config import get_os

    return get_os()


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> bool:
    """Paste text safely into the active field."""
    if is_action_aborted():
        return False
    _require_pyautogui()

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        if _sleep_interruptible(0.15):
            return False
        pyautogui.hotkey(*paste_hotkey)
        if _sleep_interruptible(0.1):
            return False
    else:
        pyautogui.write(text, interval=0.03)
    return True


def _clear_and_paste(text: str) -> bool:
    if is_action_aborted():
        return False
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    if _sleep_interruptible(0.1):
        return False
    pyautogui.press("delete")
    if _sleep_interruptible(0.1):
        return False
    return _paste_text(text)


def _open_app(app_name: str) -> bool:
    if is_action_aborted():
        return False
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            pyautogui.press("win")
            if _sleep_interruptible(0.5):
                return False
            _paste_text(app_name)
            if _sleep_interruptible(0.6):
                return False
            pyautogui.press("enter")
            if _sleep_interruptible(2.5):
                return False
            return True

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            if _sleep_interruptible(2.5):
                return False
            return result.returncode == 0

        else:
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            if _sleep_interruptible(2.5):
                return False
            return launched

    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False


def _search_in_app(query: str) -> bool:
    if is_action_aborted():
        return False
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    if _sleep_interruptible(0.5):
        return False
    _clear_and_paste(query)
    if _sleep_interruptible(1.0):
        return False
    return True


def _send_whatsapp(receiver: str, message: str) -> str:
    """Send a WhatsApp message using Playwright DOM selectors (Section 17)."""
    if is_action_aborted():
        return "Aborted: Action cancelled by user."

    try:
        from actions.browser_control import _registry
        sess = _registry.get("chrome")
    except Exception as e:
        return f"Could not get Chrome session: {e}"

    async def _wa_flow():
        page = await sess._get_page()
        if "web.whatsapp.com" not in page.url:
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            # Wait for the main page to load
            await page.wait_for_timeout(3000)
        
        # Look for search box
        try:
            search_box = page.locator('div[contenteditable="true"][data-tab="3"]')
            await search_box.wait_for(timeout=20_000)
            await search_box.click()
            await search_box.fill(receiver)
            await page.wait_for_timeout(1000) # Wait for results
            await page.keyboard.press("Enter")
        except Exception as e:
            return f"Failed to search for contact: {e}"

        # Look for message box
        try:
            msg_box = page.locator('div[contenteditable="true"][data-tab="10"], div[title="Type a message"]')
            await msg_box.first.wait_for(timeout=10_000)
            await msg_box.first.click()
            await msg_box.first.fill(message)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
        except Exception as e:
            return f"Failed to type message: {e}"
            
        await page.wait_for_timeout(500)
        return f"Message sent to {receiver} via WhatsApp Web."

    try:
        return sess.run(_wa_flow(), timeout=60)
    except Exception as e:
        return f"Playwright WhatsApp flow failed: {e}"


def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if is_action_aborted():
        return "Aborted: Action cancelled by user."

    if not _open_app(app_name):
        return f"Could not open {app_name}."

    if _sleep_interruptible(1.0):
        return "Aborted: Action cancelled by user."

    if not _is_window_focused([app_name]):
        return f"Aborted: {app_name} is not in foreground. Message not sent."

    if not _search_in_app(receiver):
        return "Aborted: Search interrupted."

    if is_action_aborted():
        return "Aborted: Action cancelled by user."

    pyautogui.press("enter")
    if _sleep_interruptible(0.8):
        return "Aborted: Action cancelled by user."

    if not _is_window_focused([app_name]):
        return f"Aborted: {app_name} lost focus. Message not sent."

    if not _paste_text(message):
        return "Aborted: Text pasting interrupted."

    if _sleep_interruptible(0.3):
        return "Aborted: Action cancelled by user."

    if not _is_window_focused([app_name]):
        return f"Aborted: {app_name} lost focus. Message not sent."

    if is_action_aborted():
        return "Aborted: Action cancelled by user."

    pyautogui.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."


_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp),
    ({"telegram", "tg"},                      lambda r, m: _desktop_send("Telegram", r, m)),
    ({"signal"},                               lambda r, m: _desktop_send("Signal", r, m)),
    ({"discord"},                              lambda r, m: _desktop_send("Discord", r, m)),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip()
    confirmed    = params.get("confirmed", False)

    if not receiver:
        return "Please specify a recipient."
    if not message_text:
        return "Please specify the message content."
    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    from core.voice_auth import is_guest_mode
    if is_guest_mode():
        return "Action restricted: Messaging capabilities are reserved exclusively for the owner."

    # Mandatory user confirmation check
    if not confirmed:
        return (
            f"[CONFIRMATION_PENDING] Sending message to {receiver} via {platform}: "
            f"\"{message_text}\". Say yes to confirm or cancel to abort."
        )

    # Reset kill-switch before execution
    reset_action_abort()

    preview = message_text[:50] + ("…" if len(message_text) > 50 else "")
    print(f"[SendMessage] 📨 {platform} → {receiver}: {preview}")
    if player:
        player.write_log(f"[msg] {platform} → {receiver}")

    try:
        handler = _resolve_platform(platform)
        result  = handler(receiver, message_text)
    except Exception as e:
        result = f"Could not send message: {e}"

    print(f"[SendMessage] {'✅' if 'sent' in result.lower() else '❌'} {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "send_message",
    "description": (
        "Sends a text message via WhatsApp, Telegram, or other messaging platform. "
        "MANDATORY CONFIRMATION: You MUST ask the owner to confirm "
        "('Sending message to [Contact/Number]: [Message text]. Say yes to confirm or cancel to abort.') "
        "before calling this tool with confirmed=True. If confirmed is False, it will request confirmation."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {
                "type": "STRING",
                "description": "Recipient contact name or phone number"
            },
            "message_text": {
                "type": "STRING",
                "description": "The message to send"
            },
            "platform": {
                "type": "STRING",
                "description": "Platform: WhatsApp, Telegram, etc."
            },
            "confirmed": {
                "type": "BOOLEAN",
                "description": "Must be True ONLY if user explicitly confirmed sending this message."
            }
        },
        "required": [
            "receiver",
            "message_text",
            "platform"
        ]
    },
    "handler": send_message,
}
