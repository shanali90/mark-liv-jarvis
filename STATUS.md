# Phase 1 checkpoint — trust, integrity, and verification

## Trust and shutdown

- Browser navigation, reading, scrolling, normal typing, and computer controls
  remain do-and-tell. Sending/posting, file delete/move/rename, computer
  settings changes, shutdown/restart, and payments require confirmation.
- Voice shutdown requests and shutdown tool calls use the same pending
  confirmation. A standalone spoken “yes” / “no” and the HUD buttons resolve
  the pending action; voice decisions are consumed so they cannot trigger an
  unrelated model action.
- Confirmed shutdown schedules the existing graceful shutdown sequence on the
  app event loop.

## Integrity and secrets

- Startup checks SHA-256 pins for `main.py`, `core/confirm.py`,
  `core/safety/trust.py`, `core/tools/mixin.py`, and the active pre-commit hook;
  missing or changed files stop startup.
- `scripts/hooks/pre-commit` retains the original API-key scans (AIza, sk-,
  sk-ant-, Bearer, 40-character hex, and api_key assignment patterns) and
  rejects staged `client_secret`, `token`, and `.db` files.
- `.gitignore` excludes personal JSON, database, and backup files in memory;
  tracked memory contains source files only.

## Verification results

- Pytest: 50 passed, 3 skipped. `verify.ps1` invokes `pytest -v -rs`, rejects
  zero collected tests, and reports the skip reasons.
- Skips: `tests/test_live.py::test_live_gemini` and
  `tests/test_live.py::test_live_offline_provider` require the explicit
  `--live` opt-in because they make external service calls. The wake-word test
  skips only if openwakeword/model startup fails; this checkout's model could
  not start, so the detector integration cannot be exercised here.
- Full-project pyflakes was initially reporting unused imports, unused
  locals/globals, missing f-string placeholders, and one undefined `Any`.
  Those warnings were fixed without blanket ignores; the project-wide lint
  command now checks files one by one, avoiding Windows command-line limits.
- Pyflakes comparison: revision `105a1b7` reported 96 warnings across 99
  files; the current tree reports 0 warnings across 101 files.
- Assertion audit against `phase0-ok`: no assertion was weakened or removed
  from `tests/test_tool_execution.py` or `tests/test_smoke_startup.py`. The
  audit-log assertion now reads through `audit.AUDIT_LOG_FILE` so it follows
  the test's temporary-path monkeypatch; its condition is unchanged. New
  assertions cover LEVEL_ASK, voice/UI approval, denial, and voice shutdown.
- Hash-integrity and fake-key secret scanner tests are included in the suite.
- The startup verifier checks `State:\s*CONNECTED\b`, cleans up and checks the
  started process tree, identifies remaining project Python processes by
  command line, requires a clean Git status, enforces prompt numstat limits,
  validates required hook checks, and prints all skip reasons.
- `verify.ps1` is intended to be run from this committed clean checkout. Its
  full terminal output, including startup and remaining-process checks, is the
  source of truth; do not substitute a hand-written summary for that output.
