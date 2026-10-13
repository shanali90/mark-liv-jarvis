# Phase A: JARVIS Architecture & Enhancement Analysis

## 1. Architecture Review

### Strengths
- **Live WebSocket Foundation**: Real-time streaming via `google-genai` enables genuine conversational flow with barge-in capabilities.
- **Safety & Audit Architecture**: The existing SHA-256 hash-chaining and three-tier (RED/YELLOW/GREEN) permission structure provides a solid, verifiable trust foundation.
- **SQLite + Vector DB**: FTS5 mixed with Cosine Similarity enables rich memory management.

### Single Points of Failure (SPOFs) & Monolithic Flaws
- **`main.py` is a 2500-line monolith**: `JarvisLive` currently handles UI threading, audio device I/O, prompt assembly, API networking, and tool execution. If one piece fails (e.g., an audio buffer underrun), the entire session crashes.
- **Internet Dependency**: 100% reliance on Gemini. Without network, the assistant cannot even process basic local OS commands.
- **Synchronous Setup**: The UI waits for the ~20KB prompt upload to Gemini before displaying "Ready", leading to perceived latency.

### Refactoring Strategy (Module Boundaries)
We will splinter `main.py` into the following structure:
- `core/session/` - Connection, state management, contextual compression.
- `core/audio/` - VAD, echo cancellation, `sounddevice` streams, visemes.
- `core/safety/` - Voice authentication, kill-switch, `ToolRegistry` enforcement.
- `core/tools/` - Dynamic module loading and dispatch.
- `ops/` - Personal operations (Gmail, Calendar, Social, Accounts).
- `selfheal/` - System supervisors, exception capture, research-and-patch.
- `learning/` - Playbook generators, preference updaters.

---

## 2. Solutions for the 17 Limitations

| Limit | Solution & Specific Implementation | Effort |
|---|---|---|
| **1. Offline Fallback** | Deploy `faster-whisper` (small model) locally. Route audio here if WS fails. Add a regex-based `LocalCommandParser` for basic OS tools (volume, app launch, lock screen). | M |
| **2. Wake Word** | Due to Py3.14 wheel limitations, spawn an isolated `python3.11` subprocess for `openwakeword` communicating via local UDP socket. Fall back to PTT if missing. | M |
| **3. Slow Connection** | Lazily inject memory (keep prompt strictly to rules). Compress payload. Spawn PyQt6 UI **before** awaiting `live.connect()`. | S |
| **4. Screen Clicking** | Call `ctypes.windll.shcore.SetProcessDpiAwareness(2)`. Use `mss.mss().monitors` for exact offsets. Post-click screenshot verification with retries. | M |
| **5. Browser Loops** | `browser_control` gets an execution budget (max 3 actions/domain). Add DOM hash checks (`hash(page.content())`); abort if unchanged 3 times. | S |
| **6. Weather** | Remove Google scrape; implement `requests.get("https://api.open-meteo.com/v1/forecast")` for structured, keyless JSON data. | S |
| **7. Music** | OAuth via `spotipy` for Spotify Web API. Fallback to `pycaw`/`winrt.windows.media.control` for local Windows media keys (Play/Pause). | M |
| **8. Smart Home** | Gateway via `homeassistant_api` (Home Assistant REST/WS API). Restrict to simple toggles initially. | S |
| **9. Image Generation** | Implement `gemini_image` tool hitting the `imagen-3.0-generate-001` endpoint via `genai.Client`. | S |
| **10. Clipboard Hist.** | Background thread polling `pyperclip`, tracking last 50 items in SQLite `memory.db` (`clipboard` category). | S |
| **11. Notification Ctr.** | In-app PyQt6 slide-in toasts (replacing OS notifications) + SQLite notification history panel in the UI. | M |
| **12. Multi-Monitor** | Update `screen_processor` to capture virtual desktop bounding box from `mss` instead of `monitor[1]`. | S |
| **13. Gmail/Calendar** | `ops/gmail/` using `google-api-python-client` with local OAuth desktop flow (`InstalledAppFlow`) & `keyring` storage. | L |
| **14. Social Sandbox** | `ops/social/` adapters for Tweepy (X) and LinkedIn. RED tier (requires voice confirm to POST). | L |
| **15. Dashboard/Relay** | Extract dashboard into `ops/dashboard.py` running in a daemon thread with `fastapi`/`uvicorn`. | S |
| **16. Plugin System** | Define `manifest.json`. Plugins loaded into `plugins/` execute dynamically via `ToolRegistry` with sandboxed permissions. | M |
| **17. Py3.14 Compat** | Move strict dependencies (Whisper, ONNX) into a managed `py3.11` venv sidecar. | M |

---

## 3. Prioritized Roadmap

**Phase 1: Foundation (Critical Fixes & Safety) - *High Value, Med Effort***
1. Refactor `main.py` into `core/` modules.
2. Fix screen clicking accuracy (DPI + multi-monitor).
3. Implement `Open-Meteo` weather & `Spotipy` integration.
4. UI Async Start (load UI before Gemini handshake).
5. Fix Wake Word (isolated Py3.11 subprocess) & Offline fallback (faster-whisper).
6. Implement Prompt Injection wrappers.

**Phase 2: Personal Operations - *High Value, High Effort***
1. `ops/accounts.py`: OAuth + Windows Credential Manager.
2. `ops/gmail/`: Sync, Triage, Draft, Reply.
3. Calendar integrations & Daily Briefing.
4. Social Media official APIs (X, LinkedIn).
5. Clipboard history & internal Notification Center.

**Phase 3: Self-Repair & Learning - *Extreme Value, High Effort***
1. `selfheal/detect.py`: Task supervisors & Incident DB.
2. `selfheal/patcher.py`: Git sandbox, AST verification, and Gemini patch generation.
3. `learning/`: Playbook generation (distilling successful multi-step actions).
4. Home Assistant integration & Plugin ecosystem.

---

## 4. Risk Register (Autonomy Features)

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Accidental Email/Post** | High | Actions locked to RED tier. Requires explicit voice confirmation matching the owner's voice print (`is_guest_mode() == False`). 30-sec undo delay window. |
| **Prompt Injection via Mail** | Critical | Untrusted text wrapped in `<untrusted>` tags. Model instructed to drop action privileges when analyzing unverified text. |
| **Bad Self-Patch Brick** | High | Patches applied in `git worktree`. Strict replay tests + unit tests before merge. Instant rollback if identical crash occurs within 5 minutes. |
| **OAuth Token Theft** | High | Tokens stored entirely in Windows `keyring` (Credential Manager). Explicit blocking of credential extraction tools. |
| **Browser Infinite Loop** | Med | State machine aborts if DOM hash matches 3 consecutive times or budget > 5 actions. |
