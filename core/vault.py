import logging
import os
import re

logger = logging.getLogger(__name__)

_WARNING_LOGGED = False
_SECRET_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_KEYRING_CACHE: dict[str, str] = {}

def clear_cache() -> None:
    """Clear cached secrets (useful in tests and re-authentication)."""
    _KEYRING_CACHE.clear()

def get_secret(key_name: str) -> str:
    """Retrieve a secret from the environment or the OS keychain."""
    global _WARNING_LOGGED
    if not _SECRET_NAME.fullmatch(key_name):
        raise ValueError("Credential names may contain letters, digits, and underscores only.")

    environment_name = key_name.upper()
    secret = os.environ.get(environment_name)
    if secret:
        return secret

    if key_name in _KEYRING_CACHE:
        return _KEYRING_CACHE[key_name]

    try:
        import keyring
        secret = keyring.get_password("Jarvis", key_name)
    except Exception as exc:
        if not _WARNING_LOGGED:
            logger.warning(
                "OS keychain lookup failed (%s); set %s or configure the keychain.",
                type(exc).__name__,
                environment_name,
            )
            _WARNING_LOGGED = True

    if secret:
        _KEYRING_CACHE[key_name] = secret
        return secret

    return ""

def set_secret(key_name: str, secret_value: str) -> bool:
    """Save a secret to the OS Keychain."""
    if not _SECRET_NAME.fullmatch(key_name):
        raise ValueError("Credential names may contain letters, digits, and underscores only.")
    if not secret_value:
        return False
    try:
        import keyring
        keyring.set_password("Jarvis", key_name, secret_value)
        _KEYRING_CACHE[key_name] = secret_value
        return True
    except Exception as exc:
        logger.error(
            "Failed to set secret %s in the OS keychain (%s).",
            key_name,
            type(exc).__name__,
        )
        return False
