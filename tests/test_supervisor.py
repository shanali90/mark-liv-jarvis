import pytest
import asyncio
from core.supervisor import supervise

@pytest.mark.anyio
async def test_supervisor_restarts_on_error_with_exponential_backoff(monkeypatch):
    run_count = 0
    delays = []
    real_sleep = asyncio.sleep

    async def failing_task():
        nonlocal run_count
        run_count += 1
        if run_count < 3:
            raise ValueError("Crash")
        return "Success"

    async def record_sleep(delay):
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    await supervise("test_task", failing_task, max_restarts=3, backoff_base=0.1)
    assert run_count == 3
    assert delays == [0.1, 0.2]

@pytest.mark.anyio
async def test_supervisor_gives_up_after_max_restarts():
    run_count = 0

    async def always_fails():
        nonlocal run_count
        run_count += 1
        raise ValueError("Crash forever")

    await supervise("fail_task", always_fails, max_restarts=2, backoff_base=0.1)

    # It should have run 3 times (1 initial + 2 restarts)
    assert run_count == 3

@pytest.mark.anyio
async def test_supervisor_cancellation():
    run_count = 0

    async def hanging_task():
        nonlocal run_count
        run_count += 1
        await asyncio.sleep(10)

    task = asyncio.create_task(supervise("hang", hanging_task, max_restarts=2, backoff_base=0.1))
    await asyncio.sleep(0.1)
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass

    assert run_count == 1

@pytest.mark.anyio
async def test_supervisor_cancellation_during_backoff_stops_restarts():
    failed = asyncio.Event()
    run_count = 0

    async def failing_task():
        nonlocal run_count
        run_count += 1
        failed.set()
        raise RuntimeError("restart must be cancelled")

    task = asyncio.create_task(
        supervise("backoff", failing_task, max_restarts=5, backoff_base=5)
    )
    await asyncio.wait_for(failed.wait(), timeout=1)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert run_count == 1

@pytest.mark.anyio
async def test_supervisor_other_tasks_keep_running():
    task1_runs = 0
    task2_ticks = 0

    async def crashing_task():
        nonlocal task1_runs
        task1_runs += 1
        raise RuntimeError("Crash immediately")

    async def healthy_task():
        nonlocal task2_ticks
        for _ in range(5):
            task2_ticks += 1
            await asyncio.sleep(0.05)

    t1 = asyncio.create_task(supervise("crasher", crashing_task, max_restarts=2, backoff_base=0.01))
    t2 = asyncio.create_task(supervise("healthy", healthy_task, max_restarts=2, backoff_base=0.01))

    await asyncio.gather(t1, t2)
    assert task1_runs == 3
    assert task2_ticks == 5
