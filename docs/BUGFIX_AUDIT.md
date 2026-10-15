# Bug-fix audit (branch fix/audit-1)

Scope: bugs only, no new features. Every fix has a regression test in
`tests/test_audit_fixes.py` (or an amended existing test) that fails on the old code.

| # | Where | Problem | Fix | Pinned file? |
|---|-------|---------|-----|--------------|
| 1 | `main.py`, `core/audio/mixin.py` | **Wake word hang.** If the wake-word model is missing, JARVIS still went to sleep and listened only to the broken detector, so nothing could ever wake it ("waiting for wake word", no response). | `_wake_available()` starts the detector; if it cannot start, wake-word mode is switched off for this run only (saved preference kept) and JARVIS stays awake, with a message saying why. | main.py |
| 2 | `main.py`, `core/conn_errors.py` | **Rejected key never reported.** An expired, revoked or deleted key did not match the old "API key not valid" text, so the app retried every few seconds forever with a traceback each time. A bad key worded as INVALID_ARGUMENT was swallowed by the "live tuning rejected" branches first. A bare close code 1007 was wrongly treated as a bad key. A local `_conn_backoff` was never stored. | Auth errors are classified first by `is_auth_error()`; the app says the key was rejected, shows the key prompt, and waits instead of retrying. | main.py |
| 3 | `tests/test_regression_phase1.py` | **Opened your real Chrome on example.com.** `test_browser_loop_budget` called the real `go_to` ten times per run. | `_open_native` is stubbed; the test also asserts nothing opened after the budget stopped it. New test fails any test that calls `browser_control()` without `monkeypatch`, uses `webbrowser.open`, or launches a visible browser. | no |
| 4 | `actions/open_app.py` | **Command injection.** The app name (from the model) was run with `shell=True` after a PATH check that only looked at the text before the first dot, so `calc.exe & del x` ran two commands. `start <name>` had the same hole. Fuzzy alias matching used bare substrings, so "knowledge" opened Edge. | No shell; the resolved executable is launched as a list. URI names open only from an allow-list of schemes. Alias matching is whole-word. | no |
| 5 | `actions/desktop.py` | **Sandbox escape.** Model-written code was run with `getattr` and a live `Path`, enough to reach `os`/`subprocess` through `Path.__init__.__globals__`. The prompt says "inspection only" but `unlink`/`write_text` were callable. | Code is parsed and refused if it imports, touches `_`-prefixed attributes, uses `getattr`/`type`/`open`, or calls delete/write/rename methods. | no |
| 6 | `actions/file_controller.py` | **Whole home folder was "safe".** A request carried in a web page could read `~/.ssh` or browser profiles, drop a file in the Startup folder, or edit JARVIS's own files. | Protected locations (secrets, browser profiles, Startup folder, the project folder) are refused for every file operation. | no |
| 7 | `actions/dev_agent.py` | `shell=True` when opening VS Code with a model-chosen folder name. | Resolved path, no shell. | no |
| 8 | `core/safety/trust.py` | Tools missing from the policy table defaulted to ASK, so "weather in Karachi" and "open Chrome" needed a spoken yes every time. | Added `weather_report`, `flight_finder` (silent) and `open_app`, `switch_to_window`, `youtube_video`, `reminder` (do-and-tell). Risky tools still ask. | trust.py |
| 9 | `core/offline_engine.py` | **Offline "close <app>" built a shell string and always said "Closed".** `os.system(f"taskkill /f /im {name}")` took the spoken name unquoted (a name with spaces split into extra taskkill arguments), could close Explorer or JARVIS itself ("close python"), and replied "Closed X" even when nothing was running. | `_close_app()`: name reduced to one safe executable name, run as a list with no shell, system/JARVIS processes protected, reply reflects taskkill's real result. | no |
| 10 | `actions/gmail.py`, `.gitignore` | **Gmail login stored as a pickle file, and not git-ignored.** Loading a tampered `gmail_token.pickle` runs arbitrary code, and no ignore rule matched `gmail_token.*`, so `git add .` would commit a live Gmail token. | Token stored as JSON (`Credentials.from_authorized_user_file`); an old pickle token is ignored and you sign in again. `.gitignore` now covers `**/*token*.json`, `*.pickle`, `*.pkl`. | no |
| 11 | `actions/open_app.py` | **"Open WhatsApp / Instagram / a website" did nothing useful.** The tool description told the model never to use it for websites. For a name with no installed app, Windows typed it into the Start menu (landing on a web search) and still reported "Opened". | A web address opens in Chrome (http/https only). A known service (WhatsApp, Instagram, Facebook, YouTube, Gmail, ...) opens its installed app if Windows lists one, otherwise its website, and the reply says which. Tool description updated. | no |

## Checked, no bug found
- `_save_config_key`: the only caller is `screen_processor` (`camera_index`), so the credential-name restriction blocks nothing legitimate.
- Tool execution: every unknown tool, shutdown, send, payment and file change reaches the confirmation gate; an exception inside a tool is caught and reported, it does not stop the session.
- Secrets: the key comes only from `GEMINI_API_KEY` or Windows Credential Manager; `config/api_keys.json` is no longer read.
- `actions/computer_control.py` starts with a UTF-8 BOM. Python reads that correctly; left alone.

- `ui.py` "duplicate def" hits are `@property` / `.setter` pairs, not duplicates.
- `core/tts.py` ElevenLabs call already has `timeout=30`.

## Not changed on purpose
- `computer_settings.py` and `dashboard/server.py` use `shell=True` only with fixed, non-user text.
- `ui.py` (5,500 lines) was not refactored; no bug was found in the paths checked.
- Wake phrase is "Hey Jarvis", not "wake up".

## Could not verify here
The work machine for this pass is Linux without PyQt6, sounddevice, google-genai, keyring or pytest, and has no package access. The new tests were run with a small shim against stubbed modules (all pass; all fail on the old code). The full `verify.ps1` run, including CONNECTED, must be done on your Windows PC.
