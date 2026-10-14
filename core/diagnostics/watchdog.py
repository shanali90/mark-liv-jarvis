from __future__ import annotations

import asyncio
import faulthandler
import logging
import re
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FRAME_PATH = re.compile(rb'(?m)(File ")([^"]+)(", line )')


class UIFreezeWatchdog:
    def __init__(
        self,
        dump_dir: Path,
        timeout_seconds: float = 5.0,
        poll_seconds: float = 0.25,
    ) -> None:
        if timeout_seconds <= 0 or poll_seconds <= 0:
            raise ValueError("watchdog timeouts must be positive")
        self._dump_dir = Path(dump_dir)
        self._timeout = timeout_seconds
        self._poll = poll_seconds
        self._last_heartbeat = time.monotonic()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._reported = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("UI freeze watchdog is already started")
        self._last_heartbeat = time.monotonic()
        self._thread = threading.Thread(
            target=self._watch,
            name="jarvis-ui-freeze-watchdog",
            daemon=True,
        )
        self._thread.start()

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = time.monotonic()
            self._reported = False

    def bind_asyncio_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if loop.is_closed():
            raise RuntimeError("cannot bind watchdog to a closed asyncio loop")
        with self._lock:
            self._loop = loop

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, self._poll * 4))

    def _watch(self) -> None:
        while not self._stop.wait(self._poll):
            with self._lock:
                stalled = time.monotonic() - self._last_heartbeat >= self._timeout
                if not stalled or self._reported:
                    continue
                self._reported = True
                loop = self._loop
            self._capture(loop)

    def _capture(self, loop: asyncio.AbstractEventLoop | None) -> None:
        try:
            self._dump_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            dump_path = self._dump_dir / f"ui-freeze-{stamp}.txt"
            with tempfile.TemporaryFile(mode="w+b") as buffer:
                faulthandler.dump_traceback(file=buffer, all_threads=True)
                buffer.flush()
                buffer.seek(0)
                tracebacks = _redact_frame_paths(buffer.read())
            with dump_path.open("wb") as output:
                output.write(
                    f"UI heartbeat stalled for at least {self._timeout:.1f}s\n"
                    "Thread stacks (paths outside the project are redacted):\n"
                    .encode("utf-8")
                )
                output.write(tracebacks)
                output.write(b"\nAsyncio task stacks:\n")
            if loop is None:
                _append_text(dump_path, "No asyncio loop was bound.")
                return
            try:
                loop.call_soon_threadsafe(self._append_asyncio_tasks, dump_path)
            except RuntimeError as exc:
                _append_text(
                    dump_path,
                    f"Could not schedule asyncio task dump ({type(exc).__name__}).",
                )
        except OSError:
            logger.exception("Could not write the UI freeze diagnostic dump.")

    @staticmethod
    def _append_asyncio_tasks(dump_path: Path) -> None:
        try:
            loop = asyncio.get_running_loop()
            tasks = asyncio.all_tasks(loop)
            with dump_path.open("a", encoding="utf-8") as output:
                output.write(f"Task count: {len(tasks)}\n")
                for task in sorted(tasks, key=lambda item: item.get_name()):
                    coroutine = task.get_coro()
                    label = getattr(coroutine, "__qualname__", type(coroutine).__name__)
                    output.write(f"Task: {label}\n")
                    for frame in task.get_stack(limit=20):
                        output.write(
                            f"  {_display_source(frame.f_code.co_filename)}:"
                            f"{frame.f_lineno} in {frame.f_code.co_name}\n"
                        )
        except OSError:
            logger.exception("Could not append asyncio task stacks to the dump.")


def _display_source(filename: str) -> str:
    path = Path(filename)
    try:
        return path.resolve().relative_to(_PROJECT_ROOT).as_posix()
    except (OSError, ValueError):
        return "<external>"


def _redact_frame_paths(tracebacks: bytes) -> bytes:
    def replace(match: re.Match[bytes]) -> bytes:
        filename = match.group(2).decode("utf-8", "replace")
        display = _display_source(filename)
        return match.group(1) + display.encode("utf-8") + match.group(3)

    return _FRAME_PATH.sub(replace, tracebacks)


def _append_text(path: Path, message: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as output:
            output.write(message + "\n")
    except OSError:
        logger.exception("Could not update the UI freeze diagnostic dump.")
