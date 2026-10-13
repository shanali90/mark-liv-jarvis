"""
Local wake-word detection for JARVIS ("Hey Jarvis").

Design goals:
  • ZERO cost when the feature is off — openwakeword is imported ONLY inside
    start()/install helpers, never at module load. If the user never enables
    wake word, none of this touches the app.
  • ZERO latency on the audio path — the microphone callback only ever does a
    cheap, non-blocking queue push (feed()); the actual model inference runs in
    this module's own background thread, so the real-time audio thread and the
    Gemini stream are never slowed.
  • Fully local & offline — audio fed here never leaves the machine; there is no
    network call except the one-time model download the user triggers from the UI.

openwakeword ships small ONNX models (a few MB each) and runs comfortably on a
CPU. The pretrained wake phrase used here is "Hey Jarvis".
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

# Pretrained openwakeword model that listens for "Hey Jarvis".
WAKE_MODEL = "hey_jarvis"
# Score in [0,1]; above this counts as a detection. Tuned to 0.14 for alert, instant wake detection across accents and phrases.
DEFAULT_THRESHOLD = 0.14
# Mic frames arrive at 16 kHz int16; this is just the detector's input rate.
SAMPLE_RATE = 16000


def is_installed() -> bool:
    """True if the openwakeword package is importable (no model check)."""
    try:
        import importlib.util
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """True if openwakeword is installed AND its model files are present on disk.

    This is a cheap, DETERMINISTIC file-existence check. It deliberately does NOT
    construct a Model to probe readiness — doing that is slow and, worse, can clash
    with the detector's own Model when it's already running, which intermittently
    returned False and made the UI flicker to 'not downloaded'. Never raises.
    """
    if not is_installed():
        return False
    try:
        import openwakeword
        models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        if not models_dir.is_dir():
            return False
        has_wake = (any(models_dir.glob(f"{WAKE_MODEL}*.onnx"))
                    or any(models_dir.glob(f"{WAKE_MODEL}*.tflite")))
        has_mel = (any(models_dir.glob("melspectrogram*.onnx"))
                   or any(models_dir.glob("melspectrogram*.tflite")))
        has_emb = (any(models_dir.glob("embedding_model*.onnx"))
                   or any(models_dir.glob("embedding_model*.tflite")))
        return bool(has_wake and has_mel and has_emb)
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    One-click setup for the UI button: pip-install openwakeword if missing, then
    download the wake model. Returns (ok, message). Never raises — every failure
    is reported through the returned message and the logger.
    """
    _tell = notify or (lambda _msg: None)
    try:
        if not is_installed():
            logger("Wake word: installing openwakeword (one-time)…")
            _tell("Wake word: installing openwakeword (one-time)…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openwakeword"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"
        # Download the pretrained melspectrogram/embedding + wake models.
        logger("Wake word: downloading models…")
        _tell("Wake word: downloading models…")
        try:
            import openwakeword.utils as _u
            try:
                _u.download_models([WAKE_MODEL])
            except TypeError:
                _u.download_models()   # older signature downloads the default set
        except Exception as e:
            return False, f"model download failed: {e}"

        if not is_ready():
            return False, "installed, but the wake model could not be loaded."
        logger("Wake word: ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs the wake model in a dedicated thread. The mic thread calls feed() with
    raw int16 frames; detections invoke on_detect() (called from this thread —
    the callback must marshal to whatever loop/UI it needs).
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger    = logger
        # See PluginRegistry: `logger` is the console and gets everything,
        # `notify` is the activity log and gets only what the user must act on.
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._paused  = False
        self._model   = None
        self._ready   = False

    def start(self) -> bool:
        """Load the model and spawn the inference thread. Returns True on success.
        Safe to call again — a no-op if already running. Never raises."""
        if self._running:
            return True
        try:
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")
        except Exception as e:
            self._logger(f"Wake word: could not load model — {e}")
            self._notify("Wake word unavailable — use the WAKE NOW button.")
            self._model = None
            return False
        self._running = True
        self._paused  = False
        self._ready   = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="WakeWordThread")
        self._thread.start()
        self._logger("Wake word: listening for 'Hey Jarvis'.")
        return True

    def stop(self) -> None:
        self._running = False
        self._paused  = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._model = None
        self._ready = False

    def pause(self) -> None:
        """Pause inference when JARVIS is AWAKE or PROCESSING (saves CPU & prevents re-trigger)."""
        self._paused = True
        self._drain()

    def resume(self) -> None:
        """Resume inference when JARVIS transitions back to SLEEPING."""
        self._drain()
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Must stay cheap and
        never block — the frame is copied and dropped if the queue is backed up."""
        if not self._running or self._paused:
            return
        try:
            # Check 3: Diagnose if audio reaches wake word model
            # This logs at least one chunk to prove audio is flowing to the detector
            if not getattr(self, "_logged_first_chunk", False):
                self._logger("[Wake] 🎤 Received first audio chunk from microphone.")
                self._logged_first_chunk = True
                
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except (queue.Full, Exception):
            pass

    def _loop(self) -> None:
        import numpy as np
        import time
        import os
        from datetime import datetime
        pass_count = 0
        acc_buffer = np.zeros(0, dtype=np.int16)
        while self._running:
            try:
                frame = self._queue.get()
                if frame is None or not self._running:
                    break
                if self._paused:
                    acc_buffer = np.zeros(0, dtype=np.int16)
                    continue

                acc_buffer = np.append(acc_buffer, np.asarray(frame, dtype=np.int16).flatten())
                while len(acc_buffer) >= 1280:
                    chunk = acc_buffer[:1280]
                    acc_buffer = acc_buffer[1280:]

                    t0 = time.monotonic()
                    scores = self._model.predict(chunk)
                    score = 0.0
                    detected_name = ""
                    if isinstance(scores, dict):
                        for k, v in scores.items():
                            if "jarvis" in k.lower():
                                if float(v) > score:
                                    score = float(v)
                                    detected_name = k
                        if score == 0.0 and scores:
                            for k, v in scores.items():
                                if float(v) > score:
                                    score = float(v)
                                    detected_name = k

                    pass_count += 1
                    
                    is_detected = (score >= self._threshold)
                    
                    now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    if score >= 0.05:
                        os.makedirs("logs", exist_ok=True)
                        with open("logs/jarvis_activity.log", "a", encoding="utf-8") as f:
                            status = "ACCEPTED" if is_detected else "REJECTED"
                            f.write(f"[{now_str}] WAKE ATTEMPT | Score: {score:.3f} | Threshold: {self._threshold:.2f} | {status}\n")

                    if is_detected:
                        latency_ms = (time.monotonic() - t0) * 1000.0
                        self._logger(f"[Wake] ✅ Detected '{detected_name or 'hey_jarvis'}' (score={score:.3f} >= {self._threshold:.2f}) at {now_str} (latency: {latency_ms:.1f}ms)")
                        self._drain()
                        acc_buffer = np.zeros(0, dtype=np.int16)
                        self._paused = True  # pause immediately on detection
                        try:
                            self._on_detect()
                        except Exception as e:
                            self._logger(f"Wake word: on_detect error — {e}")
                        break
                    elif score >= 0.05:
                        self._logger(f"[Wake] 🔍 Sub-threshold pass: '{detected_name or 'hey_jarvis'}' score={score:.3f} (threshold={self._threshold:.2f})")
            except Exception as e:
                self._logger(f"Wake word: inference error — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
