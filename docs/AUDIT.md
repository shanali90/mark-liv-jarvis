# Phase 0: System Audit

## What Jarvis Does Today
Jarvis is a voice-first AI assistant built with a local fallback engine and a PyQt6/numpy-based 3D holographic avatar. It uses Gemini Live for primary speech, with background processes that handle proactive notifications, screen monitoring, web searching, system controls, and offline fallback commands.

## Architecture
- **Entry Points**: `main.py` and `run_jarvis.bat`.
- **UI/Audio**: `ui.py` (avatar), `core/audio_devices.py`, `core/tts.py`, `core/stt.py`, `core/gemini.py` (handles Live streaming API).
- **Tooling**: `core/action_loader.py` discovers and loads capabilities from the `actions/` directory.
- **LLM Engine**: `core/llm_client.py` connects to local Ollama/OpenAI servers for offline queries.
- **Offline Fallback**: `core/offline_engine.py` handles basic commands (volume, brightness) when network fails.

## Dependencies
- **Core**: `PyQt6`, `sounddevice`, `numpy`, `google-genai`
- **Automation**: `pyautogui`, `pyperclip`, `pygetwindow`, `pywinauto` (Windows)
- **Web/Vision**: `playwright`, `beautifulsoup4`, `requests`, `opencv-python`, `pillow`, `mss`
- **Remote**: `fastapi`, `uvicorn`, `cryptography`
- **Missing**: `adb` is missing from the system PATH.

## Real Measured Latency Per Step
Based on `core/gemini.py` docstrings (one throwaway session):
- **Connect**: 0.24s
- **Short structured JSON**: 1.7 - 2.8s
- **2300 characters of code**: 3.39s
- **Concurrent load (3 sessions)**: 4.77s wall clock
- **Viseme Extraction**: Runs on ~43ms analysis windows.

## Brittle Spots
- **Missing Permission Boundaries**: All actions are executed directly without an approval gate.
- **No Central Event Bus**: Modules call each other directly or rely on the `genai.Client` indiscriminately.
- **Unbounded API Calls**: Previous iterations had no timeout on LLM calls (partially fixed in new ladder system, but remains a risk in plugins).
- **No Persistent DB**: Memory relies on JSON files (`long_term.json`) without FTS or vector indexing.

## Dead or Duplicated Code
- The `actions/` folder previously housed 16 different files initializing `genai.Client` inline 26 times. This is mostly duplicated API setup that should be routed through a central model adapter.

## Hardcoded Secrets
- `config/api_keys.json`

## Social Media Repo Audit
- Cannot locate the social media repository in standard directories. Awaiting path from the user.

## Environment Report
- **OS**: Microsoft Windows 11 Pro Education 10.0.26200
- **Python**: 3.14.6
- **Node**: v24.16.0
- **Chrome**: 154.0.8037.95
- **ADB**: Missing / Not recognized
- **Available Audio**: AMD High Definition Audio Device, FxSound Audio Enhancer, Senary Audio

## Skill Inventory
- `~/.gemini/antigravity/skills/`: Contains `linkedin-*` skills.
- `.agents/skills/`: Directory not found.
- `~/.gemini/config/skills/`: Contains `agency-*` skills.
- **Missing**: None of the requested engineering/security skills (Software Architect, Reality Checker, Security Architect, etc.) were found in these directories.

## Ranked Fix List
1. Build the central Event Bus & Permission Engine (Kill switch, Approval Queue, Secret Vault).
2. Establish the 3-Tier Router and Model Adapter for latency & cost control.
3. Replace JSON memory with local SQLite (FTS5 + vector index).
4. Centralize browser control behind DOM/accessibility profiles with safety halts.
5. Setup robust ADB connectivity for mobile device interaction.

## Proposed Target Architecture
```
[ Microphone / UI ] -> [ Wake Word / STT ] -> [ 3-Tier Router ]
                                                     |
                                            +--------+--------+
                                            |                 |
[ Rules Engine ] <-> [ Small Model Intent ] <-> [ Large Model Planner ]
                                            |
[ Execution Engine (Idempotent & Typed) ] <-+-> [ Event Bus / Audit Log ]
                                            |
[ Permission Gate (Green/Yellow/Red) ] <----+-> [ Secret Vault / SQLite ]
                                            |
[ Tools Registry (MCP-Compatible) ] <-------+
```

## Module Decisions
- `main.py` / `ui.py`: Keep (refactor UI to connect to event bus).
- `core/gemini.py`: Keep/Refactor (integrate into Model Adapter).
- `actions/*`: Rewrite (migrate to MCP-compatible tool registry with strict inputs/outputs).
- `memory/long_term.json`: Delete (replace with SQLite).
- `core/llm_client.py`: Rewrite (integrate into standard Model Adapter).

## Effort Per Phase
- Phase 1 (Foundations): High (critical plumbing).
- Phase 2 (Fast Brain): High (evals and router).
- Phase 3 (Memory): Medium.
- Phase 4 (Computer/Chrome): High (playwright with safety stops).
- Phase 5 (Mobile): Medium (ADB integration).
- Phase 6 (Voice): Low (mostly exists, needs integration).
- Phase 7 (Social): Medium (needs platforms and API pacing).
- Phase 8-10: Medium to High (specialized routines and deep hardening).
