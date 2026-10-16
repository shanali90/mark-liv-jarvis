from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import importlib.metadata
import io
import os
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HOST = "generativelanguage.googleapis.com"
_KEY_PATTERNS = re.compile(
    r"AIza[A-Za-z0-9_-]{12,}|"
    r"sk-ant-[A-Za-z0-9_-]{12,}|"
    r"sk-[A-Za-z0-9_-]{12,}|"
    r"(?i:Bearer\s+)[A-Za-z0-9._~+/-]{8,}=*|"
    r"AQ\.[A-Za-z0-9._~-]{8,}|"
    r"(?i:[?&](?:key|api_key|access_token)=)[^&\s]+"
)


def redact_text(message: object, secret: str = "") -> str:
    text = str(message)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return _KEY_PATTERNS.sub("[REDACTED]", text)


def _read_user_environment(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
        return str(value)
    except (OSError, ImportError):
        return ""


def _read_keyring(name: str) -> str:
    import keyring

    return keyring.get_password("Jarvis", name) or ""


def _sha256_same(left: str, right: str) -> str:
    left_digest = hashlib.sha256(left.encode("utf-8")).digest()
    right_digest = hashlib.sha256(right.encode("utf-8")).digest()
    return "same" if hmac.compare_digest(left_digest, right_digest) else "different"


def _key_prefix_class(value: str) -> str:
    if value.startswith("AIza"):
        return "AIza"
    if value.startswith("AQ."):
        return "AQ."
    return "other"


def _exception_status(error: BaseException) -> int | None:
    for name in ("code", "status_code"):
        value = getattr(error, name, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if isinstance(value, int):
            return value
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    response = getattr(error, "response", None)
    value = getattr(response, "status_code", None)
    if isinstance(value, int):
        return value
    match = re.search(r"\b(400|401|403|429)\b", str(error))
    return int(match.group(1)) if match else None


def _google_error_fields(error: BaseException) -> str:
    text = str(error)
    status = _exception_status(error)
    reason_match = re.search(r"""['"]reason['"]\s*:\s*['"]([^'"]+)""", text)
    google_status_match = re.search(r"""['"]status['"]\s*:\s*['"]([^'"]+)""", text)
    fields = []
    if status is not None:
        fields.append(f"HTTP {status}")
    if reason_match:
        fields.append(f"reason={reason_match.group(1)}")
    if google_status_match:
        fields.append(f"status={google_status_match.group(1)}")
    return ", ".join(fields) if fields else "HTTP status unavailable"


def _dns_lookup(host: str) -> list[tuple]:
    return socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)


def _dns_with_timeout(host: str, timeout: float = 5) -> list[tuple]:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_dns_lookup, host)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError(f"DNS lookup exceeded {timeout:g}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _build_main_live_config() -> tuple[str, Any, str]:
    import main

    class DiagnosticUI:
        def __getattr__(self, _name: str) -> Callable[..., None]:
            return lambda *args, **kwargs: None

    jarvis = main.JarvisLive(DiagnosticUI())
    api_version = "v1alpha" if jarvis._enhanced_live else "v1beta"
    return main.LIVE_MODEL, jarvis._build_config(), api_version


def _close_sync_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


async def _close_async_client(client: Any) -> None:
    close = getattr(getattr(client, "aio", None), "aclose", None)
    if callable(close):
        result = close()
        if hasattr(result, "__await__"):
            await result


def run_diagnostics(
    output: Callable[[str], None] = print,
    *,
    key_reader: Callable[[str], str] | None = None,
    process_env: Callable[[str], str | None] | None = None,
    user_env_reader: Callable[[str], str] | None = None,
    credential_reader: Callable[[str], str] | None = None,
    client_factory: Callable[..., Any] | None = None,
    live_config_factory: Callable[[], tuple[str, Any, str]] | None = None,
    dns_lookup: Callable[[str], list[tuple]] | None = None,
    tcp_connect: Callable[..., Any] | None = None,
) -> None:
    if key_reader is None:
        from core.vault import get_secret

        key_reader = get_secret
    if process_env is None:
        process_env = os.environ.get
    if user_env_reader is None:
        user_env_reader = _read_user_environment
    if credential_reader is None:
        credential_reader = _read_keyring
    if client_factory is None:
        from google import genai

        client_factory = genai.Client
    if live_config_factory is None:
        live_config_factory = _build_main_live_config
    if dns_lookup is None:
        dns_lookup = _dns_with_timeout
    if tcp_connect is None:
        tcp_connect = socket.create_connection

    variable = "GEMINI_API_KEY"
    process_key = process_env(variable) or ""
    user_key = user_env_reader(variable) or ""
    try:
        keyring_key = credential_reader("gemini_api_key") or ""
    except Exception as error:
        keyring_key = ""
        output(f"a) Credential Manager lookup: unavailable ({type(error).__name__})")

    try:
        api_key = key_reader("gemini_api_key") or ""
    except Exception as error:
        api_key = ""
        output(f"a) App credential lookup: failed ({type(error).__name__})")

    if process_key:
        source = "process environment variable"
    elif keyring_key:
        source = "Windows Credential Manager"
    elif api_key:
        source = "other"
    else:
        source = "not found"

    if process_key:
        winner = "process environment variable"
    elif keyring_key:
        winner = "Windows Credential Manager"
    else:
        winner = "none"

    output(
        f"a) Key source: {source}; GEMINI_API_KEY Process={'set' if process_key else 'not set'}; "
        f"User={'set' if user_key else 'not set'}; Credential Manager="
        f"{'holds a key' if keyring_key else 'no key'}; wins={winner}"
    )
    if process_key and keyring_key:
        output(f"a) Process environment vs Credential Manager: {_sha256_same(process_key, keyring_key)}")
    if process_key and user_key:
        output(f"a) Process vs User environment: {_sha256_same(process_key, user_key)}")
    if user_key and keyring_key:
        output(f"a) User environment vs Credential Manager: {_sha256_same(user_key, keyring_key)}")
    if api_key:
        output(f"b) App key shape: length={len(api_key)} chars; prefix={_key_prefix_class(api_key)}")
    else:
        output("b) App key shape: not found")

    dns_started = time.perf_counter()
    try:
        addresses = dns_lookup(HOST)
        output(
            f"c) DNS {HOST}: OK ({(time.perf_counter() - dns_started) * 1000:.0f} ms; "
            f"{len(addresses)} address record(s))"
        )
    except Exception as error:
        output(
            f"c) DNS {HOST}: {type(error).__name__}: "
            f"{redact_text(error, api_key)} "
            f"({(time.perf_counter() - dns_started) * 1000:.0f} ms)"
        )

    tcp_started = time.perf_counter()
    try:
        with tcp_connect((HOST, 443), timeout=5):
            pass
        output(f"c) TCP {HOST}:443: OK ({(time.perf_counter() - tcp_started) * 1000:.0f} ms)")
    except Exception as error:
        output(
            f"c) TCP {HOST}:443: {type(error).__name__}: "
            f"{redact_text(error, api_key)} "
            f"({(time.perf_counter() - tcp_started) * 1000:.0f} ms)"
        )

    if not api_key:
        output("d) Gemini models.list: SKIP (app credential not found)")
        output("e) Live API connect: SKIP (app credential not found)")
    else:
        sync_client = None
        try:
            sync_client = client_factory(
                api_key=api_key,
                http_options={"api_version": "v1beta", "timeout": 10_000},
            )
            call_started = time.perf_counter()
            models = sync_client.models.list(config={"page_size": 1})
            next(iter(models), None)
            output(
                f"d) Gemini models.list: HTTP 200 OK "
                f"({(time.perf_counter() - call_started) * 1000:.0f} ms)"
            )
        except Exception as error:
            output(
                f"d) Gemini models.list: {_google_error_fields(error)}; "
                f"{type(error).__name__}: {redact_text(error, api_key)}"
            )
        finally:
            if sync_client is not None:
                try:
                    _close_sync_client(sync_client)
                except Exception:
                    pass

        async_client = None
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                model, config, api_version = live_config_factory()
            async_client = client_factory(
                api_key=api_key,
                http_options={"api_version": api_version, "timeout": 15_000},
            )

            async def connect_live() -> None:
                context_manager = async_client.aio.live.connect(
                    model=model,
                    config=config,
                )
                await context_manager.__aenter__()
                try:
                    return
                finally:
                    await context_manager.__aexit__(None, None, None)

            async def run_live_probe() -> None:
                try:
                    await asyncio.wait_for(connect_live(), timeout=15)
                finally:
                    await _close_async_client(async_client)

            try:
                asyncio.run(run_live_probe())
                output(f"e) Live API connect ({model}): OK")
            except Exception as error:
                output(
                    f"e) Live API connect ({model}): {type(error).__name__}: "
                    f"{redact_text(error, api_key)}"
                )
        except Exception as error:
            output(
                f"e) Live API connect: {type(error).__name__}: "
                f"{redact_text(error, api_key)}"
            )

    api_key = ""
    process_key = ""
    user_key = ""
    keyring_key = ""
    try:
        google_genai_version = importlib.metadata.version("google-genai")
    except importlib.metadata.PackageNotFoundError:
        google_genai_version = "not installed"
    try:
        websockets_version = importlib.metadata.version("websockets")
    except importlib.metadata.PackageNotFoundError:
        websockets_version = "not installed"
    output(
        f"f) Runtime: Python {sys.version.split()[0]}, "
        f"google-genai {google_genai_version}, websockets {websockets_version}"
    )


def main() -> int:
    run_diagnostics()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
