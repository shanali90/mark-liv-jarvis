# JARVIS / Mark-LIV - instructions for Claude Code

Owner: Shan Ali. Final-year project. NOT a programmer: explain in plain words, one
step at a time, give exact PowerShell commands. He is in Pakistan on a slow, unstable
village connection (Asia/Karachi, UTC+5) - everything must tolerate weak internet.

## What this is
Voice-controlled Windows assistant: Python 3.14, PyQt6 UI, Gemini Live API (main.py),
~20 tools in actions/*.py (auto-discovered, each has a module-level TOOL dict),
3-tier safety, SQLite memory, local wake word ("Hey Jarvis", openwakeword).

## Hard rules (the owner set these; never break them)
- NEVER ask for, paste, print or log the Gemini API key. It lives only in the Windows
  keyring via `.\.venv\Scripts\python.exe scripts\set_key.py` (getpass). Do not
  read config/secrets. If a key appears in a chat or log, tell him to revoke it.
- Work on branch `fix/audit-1`. Never push `master`. No force-push, no `--no-verify`.
  Do not touch the other folders/repos: baseline, main, Nova-Ai-chatboat.
- Pinned files are hash-checked (core/safety/integrity.py): main.py, core/confirm.py,
  core/safety/trust.py, core/tools/mixin.py, scripts/hooks/pre-commit. Edit them only
  when the owner agreed, in ONE separate commit titled "PINNED: ...", as small as
  possible, then re-pin through the documented process and show him the diff.
- Do not rewrite other people's commits (the agent's commits use the owner's email).
- Destructive or irreversible actions (deleting files, sending messages) stay behind
  the confirm flow. New tools default to LEVEL_ASK.

## How to work
- Diagnose from logs/jarvis_activity.log and console output BEFORE changing code.
- Every fix gets a test that FAILS on the old code and PASSES on the new
  (git stash to prove it). Never say "fixed" for anything you did not test; say
  "NOT tested" instead.
- Finish with `.\verify.ps1` run TWICE (pytest, pyflakes, 40 s startup must show
  CONNECTED, process cleanup, git clean). Paste the real output.
- pyflakes does NOT catch a local `import X` placed after an earlier use of X in the
  same function (UnboundLocalError). tests/test_no_shadowed_imports.py guards this.
- Add a row to docs/BUGFIX_AUDIT.md for each fix. Commit normally, push, then show
  `git rev-parse HEAD origin/fix/audit-1`.

## Known open problems (check these first)
1. keep_warm task in main.py sends a typed "[SYSTEM: STAY ALIVE...]" user turn every
   2 min while asleep; the model answers it aloud and has opened Google by itself.
   Sleeping now drops model audio and refuses tool calls (core/audio/mixin.py
   _is_asleep) but the task itself should be removed (PINNED commit).
2. "Session error (APIError)" appears in the UI log - find the real cause.
3. Mouse accuracy: pyautogui vs mss coordinates on scaled displays; click results
   are not verified (actions/computer_control.py). Honest "it worked / nothing
   changed / not found" results are wanted.
4. "Switch to the WhatsApp/Facebook tab" by voice: core/tab_finder.py exists; check
   it works end to end.
5. Slow internet: websocket tuning is in core/net_tuning.py, reconnect logic in
   core/reconnect.py. Verify on a real weak connection.
6. Voice interruption quality: parked for later.
7. Old memory embeddings (text-embedding-004) are in a different vector space; a
   re-embed script is a follow-up. The key shown in chat earlier should be rotated.
