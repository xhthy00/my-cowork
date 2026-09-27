"""Import prior APScheduler jobs and skill-declared schedules exactly once."""

from __future__ import annotations

import logging
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.skills import discover_skills
from app.skills.config import list_skills_api

from .models import Automation, Schedule
from .store import AutomationStore

logger = logging.getLogger(__name__)
_INTERVAL = re.compile(r"^every\s+(\d+)\s*(seconds?|minutes?|hours?|s|m|h)$", re.I)
_AP_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _legacy_weekday(value: str) -> str:
    """Keep APScheduler's Monday=0 semantics when importing its trigger."""
    if value == "*":
        return value
    mapped: list[str] = []
    for part in value.split(","):
        base, _, step_text = part.partition("/")
        if base != "*" and not base.replace("-", "").isdigit():
            mapped.append(part)
            continue
        step = int(step_text) if step_text else 1
        if base == "*":
            days = range(0, 7, step)
        elif "-" in base:
            start, end = (int(item) for item in base.split("-", 1))
            days = range(start, end + 1, step)
        elif step_text:
            days = range(int(base), 7, step)
        else:
            days = (int(base),)
        mapped.extend(_AP_WEEKDAYS[day] for day in days)
    return ",".join(dict.fromkeys(mapped))


def parse_legacy_schedule(raw: str) -> Schedule:
    from datetime import datetime

    match = _INTERVAL.fullmatch(raw.strip())
    if match:
        count, unit = int(match[1]), match[2].lower()
        return Schedule(kind="interval", interval_seconds=count * (3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1))
    try:
        datetime.fromisoformat(raw.strip())
    except ValueError:
        return Schedule(kind="cron", cron=raw.strip())
    return Schedule(kind="once", fire_at=raw.strip())


def _from_trigger(trigger) -> Schedule:
    if isinstance(trigger, CronTrigger):
        fields = {f.name: str(f) for f in trigger.fields}
        fields["day_of_week"] = _legacy_weekday(fields["day_of_week"])
        cron = " ".join(fields[name] for name in ("minute", "hour", "day", "month", "day_of_week"))
        return Schedule(kind="cron", cron=cron, timezone=str(trigger.timezone))
    if isinstance(trigger, DateTrigger):
        return Schedule(kind="once", fire_at=trigger.run_date.isoformat())
    if isinstance(trigger, IntervalTrigger):
        return Schedule(kind="interval", interval_seconds=int(trigger.interval.total_seconds()))
    raise ValueError(f"Unsupported legacy trigger: {trigger}")


def import_legacy_jobs(store: AutomationStore, old_db: Path) -> int:
    if store.meta("legacy_apscheduler_imported") == "1":
        return 0
    count = 0
    if old_db.is_file():
        from app.orchestrator.scheduler import SkillScheduler
        # APScheduler can remove malformed job rows while reading them. Inspect a
        # SQLite backup so the user's original database stays untouched.
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch) / "scheduler.db"
            try:
                with closing(sqlite3.connect(str(old_db))) as source, closing(sqlite3.connect(str(copy))) as target:
                    source.backup(target)
                legacy = SkillScheduler(db_path=copy)
                legacy.scheduler.start(paused=True)
                try:
                    for job in legacy.scheduler.get_jobs():
                        if store.get(job.id):
                            continue
                        kwargs = dict(job.kwargs or {})
                        skill_id = str(kwargs.get("skill_id") or job.id.removeprefix("skill:"))
                        prompt = str(kwargs.get("prompt") or skill_id)
                        try:
                            prompt = prompt.format(**(kwargs.get("params") or {}))
                        except (KeyError, ValueError):
                            pass
                        task = Automation(
                            id=job.id, title=skill_id, instructions=prompt,
                            schedule=_from_trigger(job.trigger), source="legacy", skill_id=skill_id,
                            enabled=job.next_run_time is not None,
                            enabled_skill_ids=[skill_id],
                            next_run=job.next_run_time.timestamp() if job.next_run_time else None,
                        )
                        try:
                            store.save(task, preserve_next_run=True)
                            count += 1
                        except ValueError:
                            logger.exception("Could not import legacy job %s", job.id)
                finally:
                    legacy.scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("Could not inspect old APScheduler database %s", old_db)
                return count
    store.set_meta("legacy_apscheduler_imported", "1")
    return count


def import_skill_schedules(store: AutomationStore, *, root: Path | None = None,
                           config_path: Path | None = None) -> int:
    enabled = {row["id"] for row in list_skills_api(root=root, config_path=config_path)
               if row.get("enabled", True)}
    count = 0
    for skill in discover_skills(root):
        task_id = f"skill:{skill.id}"
        if not skill.schedule or skill.id not in enabled or store.get(task_id) or store.meta(f"deleted:{task_id}"):
            continue
        prompt = skill.prompt or skill.name or skill.id
        try:
            prompt = prompt.format(**skill.params)
        except (KeyError, ValueError):
            pass
        task = Automation(id=task_id, title=skill.name or skill.id, instructions=prompt,
                          schedule=parse_legacy_schedule(str(skill.schedule)), source="skill",
                          skill_id=skill.id, enabled_skill_ids=[skill.id])
        try:
            store.save(task)
            count += 1
        except ValueError:
            logger.exception("Could not import schedule from skill %s", skill.id)
    return count
