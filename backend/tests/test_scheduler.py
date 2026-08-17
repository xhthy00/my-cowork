"""Tests for SkillScheduler."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from freezegun import freeze_time

from app.orchestrator.scheduler import SkillScheduler
from app.orchestrator.task_manager import TaskRequest
from app.skills import SkillMeta


@pytest.mark.asyncio
async def test_run_skill_submits_cron_task(tmp_path: Path):
    submitted: list[TaskRequest] = []

    async def _submit(req: TaskRequest) -> str:
        submitted.append(req)
        return "tid-1"

    sched = SkillScheduler(db_path=tmp_path / "jobs.db", submit=_submit)
    task_id = await sched.run_skill("cron_heartbeat", prompt="tick")
    assert task_id == "tid-1"
    assert submitted[0].source == "cron"
    assert submitted[0].text == "tick"
    sched.shutdown()


@pytest.mark.asyncio
async def test_register_cron_due_after_61s_and_run():
    """freezegun advances past a cron minute; run_skill submits once."""
    submitted: list[TaskRequest] = []

    async def _submit(req: TaskRequest) -> str:
        submitted.append(req)
        return "tid-cron"

    from apscheduler.triggers.cron import CronTrigger

    with freeze_time("2024-01-01 00:00:00", tz_offset=0) as frozen:
        trigger = CronTrigger.from_crontab("* * * * *", timezone="UTC")
        now = datetime(2024, 1, 1, 0, 0, tzinfo=trigger.timezone)
        first = trigger.get_next_fire_time(None, now)
        assert first is not None
        frozen.move_to("2024-01-01 00:01:01")
        later = datetime(2024, 1, 1, 0, 1, 1, tzinfo=trigger.timezone)
        # After +61s, the previous fire time is in the past relative to `later`.
        assert first < later

    sched = SkillScheduler(db_path=None, submit=_submit)
    job_id = sched.register_skill(
        SkillMeta(
            id="cron_heartbeat",
            schedule="* * * * *",
            prompt="heartbeat",
            allowed_tools=["builtin.http.request"],
        )
    )
    assert job_id == "skill:cron_heartbeat"
    await sched.run_skill("cron_heartbeat", prompt="heartbeat")
    assert len(submitted) == 1
    assert submitted[0].source == "cron"
    sched.shutdown()


@pytest.mark.asyncio
async def test_register_discovered_cron_skill(tmp_path: Path):
    sched = SkillScheduler(db_path=tmp_path / "jobs.db", submit=None)
    skill_dir = tmp_path / "cron_heartbeat"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(
        "id: cron_heartbeat\nname: Cron Heartbeat\n"
        "schedule: '* * * * *'\nprompt: heartbeat\n"
        "allowed_tools:\n  - builtin.http.request\n",
        encoding="utf-8",
    )
    ids = sched.register_discovered(tmp_path)
    assert any(i.endswith("cron_heartbeat") for i in ids)
    job = sched.scheduler.get_job("skill:cron_heartbeat")
    assert job is not None
    sched.shutdown()
