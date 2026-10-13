# Repository preparation status

## Safety

- Existing history is not publishable: it contains a tracked
  `config/voice_profile.tmp.npy` biometric artifact and secret-shaped test
  fixtures. The new private repository must use a fresh Git history with one
  initial commit; do not push the existing master branch or old tags.
- The Desktop backup is `C:\Users\shana\OneDrive\Desktop\Mark-LIV-baseline
  backup`; `.git` exists there. It is not being modified.
- Gemini/OpenAI credentials now resolve from environment variables first and
  Windows Credential Manager via `keyring` second. Settings files are scrubbed
  of credential-like fields on read/write. API secrets are not read from
  project config files by runtime code.
- Use `python scripts\set_key.py` to store an API key interactively, or run
  `python scripts\migrate_secrets.py <legacy-file>` yourself to migrate a local
  legacy credential file. Neither script was run by this preparation.
- Startup reports a clear `GEMINI_API_KEY` / `scripts/set_key.py` instruction
  when the key is missing; it returns cleanly instead of starting the app.

## Diagnostics

- `DIAGNOSTICS.md` and `diagnostics/` contain redacted log evidence,
  environment details, observed connection transitions, and evidence-ranked
  investigation leads.
- `JARVIS_DEBUG_WATCHDOG=1` enables a five-second Qt UI heartbeat watchdog.
  It dumps thread and asyncio task stacks to ignored `logs/` files and redacts
  source paths outside the project.
- Historical log timestamps lack dates. The log has 222 connection records,
  73 CONNECTED states, 44 RECONNECTING states, no captured exception, close
  code, quota, or timeout signatures, and the last recorded state is
  CONNECTING. See `diagnostics/runtime_evidence.txt`.
- Full verifier output will be added at `diagnostics/verify_output.txt` from
  the clean-history verification checkout before its single initial commit.

## Verification

- Focused tests last run: 40 passed, 22 dependency/deprecation warnings.
- Full-project pyflakes previously exposed an undefined `logger` after the
  credential refactor; that name was fixed. Final full lint and
  `verify.ps1` remain to be run after the final code edits.
- The final fresh repository will contain one initial commit only. It will
  exclude local databases, identity/settings JSON, logs, credentials, TLS
  private keys, voice biometric data, and all old Git history.

## PINNED FILE CHANGES (needs owner review)

- `main.py` changed to load credentials through the vault, use non-secret
  settings for assistant customization, and return a clear setup message when
  the Gemini key is absent. Its pin was recalculated after restoring the
  original owner name references.
- `scripts/hooks/pre-commit` retains the API-key patterns and adds sensitive
  filename checks; its pin was recalculated for that reviewed scanner change.
- `core/confirm.py`, `core/safety/trust.py`, and `core/tools/mixin.py` are
  unchanged; their existing pins were retained.
- `core/prompt.txt` was restored from `pre-refactor`; its comparison is 0
  added and 0 deleted lines.
- The UI window title remains generic; its tests and safety pin references
  were checked and do not depend on the previous title.
