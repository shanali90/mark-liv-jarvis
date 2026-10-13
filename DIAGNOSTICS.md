# JARVIS debugging diagnostics

## Scope and privacy

These notes summarize only the existing activity log and captured startup
stderr. Log timestamps contain time-of-day only (no dates). No conversation
transcripts, message bodies, contact names, credentials, biometric samples, or
paths outside the project are included. The three run windows below are the
last three groups separated by more than ten minutes in the activity log.

## Reported symptoms

### JARVIS stops in the middle of a conversation

- **Symptom reported:** The live conversation stops unexpectedly.
- **When/reproduction:** Not recoverable from the available logs; the activity
  log records connection transitions only.
- **Evidence:** The last run group records CONNECTING at 23:57:05 after a
  RECONNECTING state at 23:57:02. No subsequent CONNECTED event is present in
  this log. In the immediately preceding run group, repeated CONNECTING and
  RECONNECTING transitions include retry delays of 0, 3, and 6 seconds.
- **Missing evidence:** The application does not record a close code, server
  close reason, `go_away`, session-timeout, HTTP status, quota response, or
  exception signature in `jarvis_activity.log`. The old console stderr captures
  are both empty. Thus the initiating failure is not identifiable from this
  evidence.

### Command-prompt scripts glitch, repeat, or print garbage

- **Symptom reported:** Console scripts sometimes repeat or display malformed
  text.
- **When/reproduction:** No reproducer or matching console error is preserved.
- **Evidence:** `main.py` changes stdout and stderr to UTF-8 with replacement on
  Windows. This protects JARVIS's emoji/status output from legacy console
  encodings, but cannot establish whether other subprocesses inherit the
  encoding or whether the reported scripts are JARVIS subprocesses.
- **Captured output:** The available manual-start and verifier stderr files
  each contain 0 bytes; their stdout captures have no error/traceback lines.

### UI freezes / Windows reports “not responding”

- **Symptom reported:** The desktop window occasionally stops responding.
- **When/reproduction:** No freeze timestamp, thread dump, or reproduction
  details were recorded, so no historical stack evidence exists.
- **Diagnostic added:** Set `JARVIS_DEBUG_WATCHDOG=1` before startup. If the Qt
  UI heartbeat is absent for five seconds, the watchdog writes all thread
  stacks and asyncio task stacks to `logs/ui-freeze-<time>.txt`. External
  source paths are replaced with `<external>`. Run the app until the freeze
  occurs, then preserve that file locally for analysis; it is ignored by Git.

### Many errors in logs

| Signature | Count in available activity/console evidence | First / last | Raising file:line |
|---|---:|---|---|
| `RECONNECTING` state | 44 | first 02:11:58; last 23:57:02 | `main.py` writes the state at the reconnect loop |
| Python exception / traceback in activity log | 0 | none | none captured |
| HTTP 429 / quota marker in activity log | 0 | none | none captured |
| `go_away` / session-timeout / close-code marker | 0 | none | not logged by the current activity format |
| Error/traceback lines in saved startup stderr | 0 (two files, each 0 bytes) | none | none captured |

The 44 reconnect records are state transitions, not 44 proven exceptions.
`main.py` prints caught exception details to the console, while the activity
log stores only CONNECTING, CONNECTED, and RECONNECTING plus retry delay.

## Last three logged run windows

The log stores time-of-day only. Session-like windows are inferred by grouping
records separated by a gap longer than ten minutes; these are not guaranteed
process boundaries.

| Window | Records | First → last | Notable transitions |
|---|---:|---|---|
| 1 | 14 | 22:22:44 → 22:24:53 | CONNECTING → CONNECTED; two RECONNECTING cycles (3s); final CONNECTED |
| 2 | 72 | 22:44:32 → 23:16:36 | Repeated CONNECTING → CONNECTED cycles; multiple RECONNECTING cycles (3s, one 6s); final CONNECTED |
| 3 | 18 | 23:43:37 → 23:57:05 | CONNECTED at 23:44:46; three rapid RECONNECTING cycles (0s); later CONNECTED at 23:54:38; final RECONNECTING (3s) → CONNECTING, with no later CONNECTED in this log |

Close codes, close reasons, reconnect causes, quota state, and correlation with
voice/tool/browser actions were not captured. No safe reproduction steps are
known from this evidence.

## Environment observed

- Python: 3.14.6.
- OS: Windows 11, version 10.0.26200 (build 26200).
- Microphone endpoints: Windows default/primary capture and Senary Audio
  microphone array. Custom headset/device names are redacted.
- Speaker endpoints: Windows default/primary output and Senary Audio speakers.
  Custom headset/device names are redacted.
- Wake word: disabled in the local runtime settings when checked.
- Offline fallback: implemented; it activates when the network check reports
  offline. Its state at the historical stop events cannot be established.
- Gemini key source after the change: `GEMINI_API_KEY` environment variable,
  then the OS keychain (Python `keyring`). No key value is included here.
- Selected installed package versions are in
  [`diagnostics/package_versions.txt`](diagnostics/package_versions.txt).

## Ranked investigation leads (hypotheses, not established causes)

1. **Live session termination or resumption failure.** Repeated reconnects and
   the final CONNECTING without a later CONNECTED support investigating the
   Gemini Live session lifecycle. The activity log lacks the server close
   reason. See `main.py` connection loop and exception handler.
2. **Network or connection timeout.** Reconnect delays grow to six seconds in
   the activity log; `main.py` classifies timeout/DNS/socket errors for
   backoff. No network exception text was preserved.
3. **Unrecorded server close code / `go_away` / session timeout.** This cannot
   be confirmed or excluded because only three coarse connection states are
   logged; add structured close telemetry without request or transcript text.
4. **Audio device or driver instability.** Several input/output endpoints were
   enumerated, but no device-open or callback error is present in the saved
   evidence. Capture device identity only in local diagnostics and redact
   custom names before sharing.
5. **Qt UI thread blockage.** The reported symptom is consistent with a
   blocked event loop, but there is no historical stack dump. The opt-in
   watchdog now provides the required stack evidence if reproduced.
6. **Console encoding or subprocess interaction.** The app has Windows
   UTF-8/replacement handling, but no captured console errors establish a
   remaining encoding failure. Compare the exact affected command's
   stdout/stderr locally.
7. **Quota / HTTP 429 response.** No 429 or quota marker appears in the
   available log. The model helper has quota handling, but this remains
   unverified for the Live connection.
8. **Wake-word state confusion.** Wake word was disabled when checked, so it
   should not gate the observed run now; the setting at each earlier stop is
   unknown.
9. **Offline fallback transition.** The application checks connectivity and
   switches offline speech behavior, but the historical log has no online/offline
   transition around the final reconnect. Correlate a future local dump with
   network state.
10. **Insufficient historical observability.** The current activity log has no
    exception signature, action category, close code, or task/thread state;
    this is directly evidenced by the log format and zero traceback/error
    lines in the preserved startup stderr files.

## Local debug procedure

1. Set `$env:JARVIS_DEBUG_WATCHDOG = "1"` in PowerShell.
2. Start JARVIS using the normal `main.py` command and reproduce the UI stall.
3. When responsive again, locate the newest `logs/ui-freeze-*.txt`.
4. Review locally first. The watchdog redacts paths outside the project, but
   inspect the dump for accidental user text before sharing it.
5. Capture the terminal's stderr separately if the app stops; redact credentials,
   personal names, message text, transcripts, and non-project paths.
