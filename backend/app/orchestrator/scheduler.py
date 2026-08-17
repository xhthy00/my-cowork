"""L9 scheduler: APScheduler + SQLite jobstore, skill schedule registration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.orchestrator.task_manager import TaskManager, TaskRequest
from app.skills import SkillMeta, discover_skills

SubmitFn = Callable[[TaskRequest], Awaitable[str]]

_INTERVAL_RE = re.compile(
    r"^every\s+(\d+)\s*(seconds?|minutes?|hours?|s|m|h)$",
    re.IGNORECASE,
)


class SkillScheduler:
    """Register skills that declare ``schedule`` and submit cron tasks."""

    def __init__(
        self,
        task_manager: TaskManager | None = None,
        *,
        db_path: str | Path | None = None,
        submit: SubmitFn | None = None,
    ) -> None:
        self._tm = task_manager
        self._submit = submit
        if db_path is None:
            from apscheduler.jobstores.memory import MemoryJobStore

            jobstores = {"default": MemoryJobStore()}
        else:
            url = f"sqlite:///{Path(db_path)}"
            jobstores = {"default": SQLAlchemyJobStore(url=url)}
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self.scheduler.start()
            self._started = True

    def shutdown(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def register_skill(self, skill_meta: SkillMeta | dict[str, Any]) -> str | None:
        """Add a job when skill has ``schedule``; return job id or None."""
        if isinstance(skill_meta, dict):
            skill_id = str(skill_meta.get("id") or "")
            schedule = skill_meta.get("schedule")
            params = dict(skill_meta.get("params") or {})
            prompt = str(skill_meta.get("prompt") or skill_id)
        else:
            skill_id = skill_meta.id
            schedule = skill_meta.schedule
            params = dict(skill_meta.params)
            prompt = skill_meta.prompt or skill_meta.name or skill_id

        if not schedule or not skill_id:
            return None

        trigger = _parse_trigger(str(schedule))
        job_id = f"skill:{skill_id}"
        self.scheduler.add_job(
            self.run_skill,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs={"skill_id": skill_id, "params": params, "prompt": prompt},
        )
        return job_id

    def register_discovered(self, root: Path | None = None) -> list[str]:
        ids: list[str] = []
        try:
            from app.skills.config import list_skills_api

            enabled = {s["id"] for s in list_skills_api(root=root) if s.get("enabled", True)}
        except Exception:
            enabled = None
        for skill in discover_skills(root):
            if enabled is not None and skill.id not in enabled:
                continue
            job_id = self.register_skill(skill)
            if job_id:
                ids.append(job_id)
        return ids

    async def run_skill(
        self,
        skill_id: str,
        params: dict[str, Any] | None = None,
        prompt: str | None = None,
    ) -> str:
        text = prompt or skill_id
        if params:
            try:
                text = text.format(**params)
            except (KeyError, ValueError):
                pass
        req = TaskRequest(text=text, source="cron")
        if self._submit is not None:
            return await self._submit(req)
        if self._tm is None:
            raise RuntimeError("SkillScheduler has no task_manager/submit")
        return await self._tm.submit(req)


def _parse_trigger(schedule: str):
    from datetime import datetime

    raw = schedule.strip()
    m = _INTERVAL_RE.match(raw)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("s"):
            return IntervalTrigger(seconds=n)
        if unit.startswith("m"):
            return IntervalTrigger(minutes=n)
        return IntervalTrigger(hours=n)
    # ISO datetime → DateTrigger. Try first so we don't fall through to
    # cron parsing, which would reject dates like "2026-07-29" with a count
    # of dashes >= 2 (scheduling a calendar date must not require a time).
    try:
        return DateTrigger(run_date=datetime.fromisoformat(raw))
    except ValueError:
        pass
    # crontab
    return CronTrigger.from_crontab(raw)
