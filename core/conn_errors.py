"""Classify connection errors so the reconnect loop can react correctly."""

# Text the Gemini API puts in the error when the key itself is the problem.
# Deliberately NOT the bare close code 1007: Live also closes with 1007 for a
# malformed request, and calling that an "invalid key" sends the user off to
# re-enter a perfectly good key.
_AUTH_MARKERS = (
    "api key not valid",
    "api_key_invalid",
    "api key expired",
    "api key not found",
    "invalid api key",
    "api key is invalid",
    "unregistered callers",
    "unauthenticated",
)


def is_auth_error(text: str) -> bool:
    """True if the error text says the API key was rejected."""
    low = str(text or "").lower()
    if any(marker in low for marker in _AUTH_MARKERS):
        return True
    return "permission_denied" in low and "api key" in low
