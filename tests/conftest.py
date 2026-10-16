import pytest


class InMemoryKeyring:
    priority = 1

    def __init__(self):
        self._secrets = {}

    def get_password(self, service, username):
        return self._secrets.get((service, username))

    def set_password(self, service, username, password):
        self._secrets[(service, username)] = password

    def delete_password(self, service, username):
        del self._secrets[(service, username)]


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    import keyring
    import keyring.core

    backend = InMemoryKeyring()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(keyring.core, "_keyring_backend", backend)

    def reject_backend_initialization():
        raise AssertionError("Tests must not initialize a system keyring backend")

    monkeypatch.setattr(keyring.core, "init_backend", reject_backend_initialization)
    return backend


def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", default=False, help="run live tests"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "live: mark test as requiring live API")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        # --live given in cli: do not skip live tests
        return
    skip_live = pytest.mark.skip(reason="need --live option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
