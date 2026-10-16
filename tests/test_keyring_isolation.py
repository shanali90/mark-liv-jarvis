import os

import keyring
import keyring.core


def test_autouse_fixture_blocks_system_keyring_and_environment(memory_keyring):
    assert "GEMINI_API_KEY" not in os.environ
    assert keyring.get_keyring() is memory_keyring

    keyring.set_password("Jarvis", "test-only", "in-memory-only")
    assert keyring.get_password("Jarvis", "test-only") == "in-memory-only"

    try:
        keyring.core.init_backend()
    except AssertionError as error:
        assert str(error) == "Tests must not initialize a system keyring backend"
    else:
        raise AssertionError("System keyring initialization was not blocked")
