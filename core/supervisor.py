import asyncio

async def supervise(name: str, coro_func, *args, max_restarts: int = 5, backoff_base: float = 2.0, **kwargs):
    """
    Runs an async task and restarts it on failure with exponential backoff.
    Ensures that a single background task failing does not bring down the entire TaskGroup.
    """
    restarts = 0
    while True:
        try:
            await coro_func(*args, **kwargs)
            break # Normal exit
        except asyncio.CancelledError:
            raise
        except Exception as e:
            restarts += 1
            if restarts > max_restarts:
                print(f"[Supervisor] 🚨 Task {name} failed {max_restarts} times. Giving up. Error: {e}")
                from selfheal.detect import _record_incident
                _record_incident(name, e, {"restarts": restarts}, 0.0)
                break

            delay = backoff_base * (2 ** (restarts - 1))
            print(f"[Supervisor] ⚠️ Task {name} crashed: {e}. Restarting in {delay}s...")
            await asyncio.sleep(delay)
