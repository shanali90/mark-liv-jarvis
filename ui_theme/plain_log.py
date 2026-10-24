"""Plain-words activity log mapper for JARVIS UI.

Translates technical diagnostic logs into friendly, concise user messages
while filtering internal audit noise from the visual log view.
"""

from __future__ import annotations

import re


def plain_log_line(text: str) -> str | None:
    """Rewrite known technical log lines into short, plain sentences.

    Returns:
        A rewritten plain sentence,
        None if the message should be hidden from the main UI log,
        or the original text if no pattern matches.
    """
    if not text:
        return text

    # Filter out audit and internal unprompted tool call logs from the UI view
    if "UNPROMPTED TOOL CALL" in text or "[Audit]" in text or "UNPROMPTED TOOL" in text:
        return None

    # NET: Connection failed (...) - retrying in 2s
    if "NET: Connection failed" in text:
        delay_match = re.search(r"retrying in\s*(\d+(?:\.\d+)?)\s*s", text, re.IGNORECASE)
        if delay_match:
            delay = delay_match.group(1)
            return f"Internet dropped. Reconnecting in {delay} s..."
        return "Internet dropped. Reconnecting in 2 s..."

    # ERR: Session error (...) - retrying in 2s
    if "ERR: Session error" in text:
        return "Something went wrong. Reconnecting..."

    # SYS: JARVIS online - sleeping...
    if ("JARVIS online" in text or "online" in text) and "sleeping" in text.lower():
        return "Ready. Say 'Hey Jarvis' to wake me."

    # SYS: Awake - wake word.
    if re.search(r"SYS:\s*Awake\s*[-—]\s*wake word", text, re.IGNORECASE):
        return "I'm listening."

    return text
