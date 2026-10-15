import asyncio
import threading
import time

from core.diagnostics.watchdog import UIFreezeWatchdog


def test_watchdog_dumps_thread_and_asyncio_stacks_without_external_paths(tmp_path):
    loop = asyncio.new_event_loop()
    loop_ready = threading.Event()

    def run_loop():
        asyncio.set_event_loop(loop)
        loop.create_task(asyncio.Event().wait())
        loop_ready.set()
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()
    watchdog = None
    try:
        assert loop_ready.wait(timeout=2)
        watchdog = UIFreezeWatchdog(
            tmp_path,
            timeout_seconds=0.05,
            poll_seconds=0.01,
        )
        watchdog.bind_asyncio_loop(loop)
        watchdog.start()
        deadline = time.monotonic() + 2
        dumps = []
        while time.monotonic() < deadline:
            dumps = list(tmp_path.glob("ui-freeze-*.txt"))
            if dumps:
                contents = dumps[0].read_text(encoding="utf-8")
                if "Task count:" in contents:
                    break
            time.sleep(0.01)
        assert dumps
        assert "Thread stacks" in contents
        assert "Asyncio task stacks" in contents
        assert "Task count:" in contents
        assert str(tmp_path) not in contents
    finally:
        if watchdog is not None:
            watchdog.stop()
        if loop.is_running():
            async def cancel_pending_tasks():
                pending = [
                    task for task in asyncio.all_tasks(loop)
                    if task is not asyncio.current_task()
                ]
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

            asyncio.run_coroutine_threadsafe(cancel_pending_tasks(), loop).result(timeout=2)
            loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        if loop_thread.is_alive():
            raise RuntimeError("watchdog test event loop did not stop")
        if not loop.is_closed():
            loop.close()
