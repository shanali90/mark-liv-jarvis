from types import SimpleNamespace

from scripts import diagnose_connection


def test_diagnostic_redacts_keys_and_reports_environment_precedence(capsys):
    process_key = "AIza" + "A" * 35
    keyring_key = "AQ." + "b" * 40

    class FakeApiError(RuntimeError):
        code = 401

    class FakeModels:
        @staticmethod
        def list(config):
            raise FakeApiError(
                f"API key not valid {process_key}; "
                "{'reason': 'API_KEY_INVALID', 'status': 'UNAUTHENTICATED'}"
            )

    class FakeSessionContext:
        async def __aenter__(self):
            raise RuntimeError(f"Live rejected {keyring_key}")

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()
            self.aio = SimpleNamespace(
                live=SimpleNamespace(
                    connect=lambda **kwargs: FakeSessionContext()
                ),
                aclose=lambda: _async_noop(),
            )

        def close(self):
            return None

    async def _async_noop():
        return None

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    diagnose_connection.run_diagnostics(
        key_reader=lambda _name: process_key,
        process_env=lambda name: process_key if name == "GEMINI_API_KEY" else None,
        user_env_reader=lambda _name: "user-level-value",
        credential_reader=lambda _name: keyring_key,
        client_factory=FakeClient,
        live_config_factory=lambda: ("models/test-live", object(), "v1alpha"),
        dns_lookup=lambda _host: [(2, 1, 6, "", ("127.0.0.1", 443))],
        tcp_connect=lambda *args, **kwargs: FakeSocket(),
    )

    output = capsys.readouterr().out
    assert process_key not in output
    assert keyring_key not in output
    assert "a) Key source: process environment variable" in output
    assert "Process=set; User=set; Credential Manager=holds a key" in output
    assert "wins=process environment variable" in output
    assert "Process environment vs Credential Manager: different" in output
    assert "b) App key shape: length=39 chars; prefix=AIza" in output
    assert "HTTP 401" in output
    assert "reason=API_KEY_INVALID" in output
    assert "status=UNAUTHENTICATED" in output
    assert "[REDACTED]" in output


def test_diagnostic_keyring_wins_when_process_environment_is_unset(capsys):
    keyring_key = "AQ." + "c" * 40

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    diagnose_connection.run_diagnostics(
        key_reader=lambda _name: keyring_key,
        process_env=lambda _name: None,
        user_env_reader=lambda _name: None,
        credential_reader=lambda _name: keyring_key,
        client_factory=lambda **kwargs: None,
        live_config_factory=lambda: ("models/test-live", object(), "v1alpha"),
        dns_lookup=lambda _host: [(2, 1, 6, "", ("127.0.0.1", 443))],
        tcp_connect=lambda *args, **kwargs: FakeSocket(),
    )

    output = capsys.readouterr().out
    assert keyring_key not in output
    assert "a) Key source: Windows Credential Manager" in output
    assert "Process=not set; User=not set; Credential Manager=holds a key" in output
    assert "wins=Windows Credential Manager" in output
