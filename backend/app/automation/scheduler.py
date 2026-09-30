"""OpenWorker-style independent tick loop with catch-up and overlap control."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from .models import Automation, AutomationRun
from .store import AutomationStore
from app.task_support.admission import Admission, MaintenanceBusy

logger = logging.getLogger(__name__)
Runner = Callable[[Automation, AutomationRun], Awaitable[AutomationRun]]


class AutomationScheduler:
    def __init__(self, store: AutomationStore, runner: Runner, *, tick_seconds: float = 30.0, admission: Admission | None = None) -> None:
        self.store = store
        self.runner = runner
        self.tick_seconds = tick_seconds
        self.admission = admission or Admission()
        self._loop_task: asyncio.Task | None = None
        self._spawned: set[asyncio.Task] = set()
        self._spawned_by_run: dict[str, asyncio.Task] = {}
        self._runs_by_id: dict[str, AutomationRun] = {}

    def start(self) -> None:
        if self._loop_task is None:
            for run in self.store.recover_interrupted():
                self._spawn(run.task_id, run)
            self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        for task in list(self._spawned):
            task.cancel()
        if self._spawned:
            await asyncio.gather(*self._spawned, return_exceptions=True)
        self._spawned.clear()
        self._spawned_by_run.clear()
        self._runs_by_id.clear()

    async def _loop(self) -> None:
        await self.tick(trigger="catchup")
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                await self.tick(trigger="schedule")
            except Exception:
                logger.exception("Automation scheduler tick failed")

    async def tick(self, *, trigger: str = "schedule") -> None:
        if self.admission.paused:
            return
        for task_id in self.store.due_ids():
            try:
                run = self.store.claim(task_id, trigger=trigger)
                if run is not None:
                    self._spawn(task_id, run)
            except Exception:
                logger.exception("Could not claim scheduled task %s", task_id)

    def run_now(self, task_id: str) -> AutomationRun | None:
        if self.admission.paused:
            raise MaintenanceBusy()
        run = self.store.claim(task_id, trigger="manual")
        if run is not None:
            self._spawn(task_id, run)
        return run

    def resume_reviewed(self, run_id: str) -> AutomationRun | None:
        if self.admission.paused:
            raise MaintenanceBusy()
        run = self.store.get_run(run_id)
        if run is None or run.status != "recovery_review" or run_id in self._spawned_by_run:
            return None
        if self.store.get(run.task_id) is None:
            return None
        run.status = "running"
        run.recovery_tools = []
        run.resume_count += 1
        self.store.update_run(run)
        self._spawn(run.task_id, run)
        return run

    def _spawn(self, task_id: str, run: AutomationRun) -> None:
        lease = self.admission.acquire("定时任务")
        async def execute():
            with self.admission.work(run.run_id, lease):
                await self._run_claimed(task_id, run)
        child = asyncio.create_task(execute())
        child.add_done_callback(lambda _: self.admission.release(lease))
        self._spawned.add(child)
        self._spawned_by_run[run.run_id] = child
        self._runs_by_id[run.run_id] = run
        child.add_done_callback(self._spawned.discard)
        child.add_done_callback(lambda _done: self._spawned_by_run.pop(run.run_id, None))
        child.add_done_callback(lambda _done: self._runs_by_id.pop(run.run_id, None))

    async def cancel_run(self, run_id: str) -> bool:
        child = self._spawned_by_run.get(run_id)
        if child is None or child.done():
            run = self.store.get_run(run_id)
            if run is None or run.status != "recovery_review":
                return False
            run.status = "cancelled"
            run.recovery_tools = []
            self.store.finish(run)
            return True
        run = self._runs_by_id[run_id]
        run.status = "cancelled"
        child.cancel()
        await asyncio.gather(child, return_exceptions=True)
        stored = self.store.get_run(run_id)
        if stored is not None and stored.finished_at is None:
            self.store.finish(run)
        return True

    async def _run_claimed(self, task_id: str, run: AutomationRun) -> None:
        task = self.store.get(task_id)
        if task is None:
            run.status = "error"
            run.error = "Automation was deleted before execution"
            self.store.finish(run)
            return
        try:
            await self.runner(task, run)
        except asyncio.CancelledError:
            if run.status == "cancelled" and self.store.get_run(run.run_id).finished_at is None:
                self.store.finish(run)
            elif run.status != "cancelled":
                self.store.update_run(run)
            raise
        except Exception as exc:
            logger.exception("Automation %s failed", task_id)
            run.status = "error"
            run.error = str(exc)
            self.store.finish(run)
