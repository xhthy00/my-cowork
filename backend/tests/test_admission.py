import asyncio
import threading

import pytest

from app.runtime.admission import Admission, MaintenanceBusy


async def test_cancelled_await_does_not_release_writing_thread():
    gate = Admission()
    started, release = threading.Event(), threading.Event()
    def work():
        started.set()
        release.wait(5)
    task = asyncio.create_task(gate.thread(work))
    while not started.is_set():
        await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gate.pause()["active"] == 1
    with pytest.raises(MaintenanceBusy):
        gate.acquire()
    release.set()
    for _ in range(100):
        if gate.status()["active"] == 0:
            break
        await asyncio.sleep(.01)
    assert gate.status()["active"] == 0


def test_accepted_task_can_finish_nested_work_after_pause():
    gate = Admission()
    with gate.work("chat"):
        gate.pause()
        with gate.work("tool"):
            assert gate.status()["active"] == 2
    assert gate.status()["active"] == 0
    with pytest.raises(MaintenanceBusy):
        gate.acquire()


async def test_scheduler_pauses_before_claim(tmp_path):
    from app.automation.scheduler import AutomationScheduler
    from app.automation.store import AutomationStore
    gate = Admission()
    store = AutomationStore(tmp_path / "automations.db")
    async def runner(task, run):
        return run
    scheduler = AutomationScheduler(store, runner, admission=gate)
    gate.pause()
    with pytest.raises(MaintenanceBusy):
        scheduler.run_now("not-claimed")
    await scheduler.tick()
    assert gate.status()["active"] == 0
    store.close()
