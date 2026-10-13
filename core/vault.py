import logging
import os
import re

logger = logging.getLogger(__name__)

_WARNING_LOGGED = False
_SECRET_NAME = re.compile(r"^[A-Za-z0-9_]+$")

def get_secret(key_name: str) -> str:
    """Retrieve a secret from the environment or the OS keychain."""
    global _WARNING_LOGGED
    if not _SECRET_NAME.fullmatch(key_name):
        raise ValueError("Credential names may contain letters, digits, and underscores only.")

    environment_name = key_name.upper()
    secret = os.environ.get(environment_name)
    if secret:
        return secret

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
        return True
    except Exception as exc:
        logger.error(
            "Failed to set secret %s in the OS keychain (%s).",
            key_name,
            type(exc).__name__,
        )
        return False
