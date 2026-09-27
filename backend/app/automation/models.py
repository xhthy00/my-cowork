"""An automation and each of its executions are separate durable records."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from tzlocal import get_localzone

_CRON_DAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


class _OrCronTrigger:
    """Traditional cron fires when either restricted day field matches."""

    def __init__(self, day_of_month: CronTrigger, day_of_week: CronTrigger) -> None:
        self.day_of_month = day_of_month
        self.day_of_week = day_of_week

    def get_next_fire_time(self, previous_fire_time, now):
        first = self.day_of_month.get_next_fire_time(previous_fire_time, now)
        second = self.day_of_week.get_next_fire_time(previous_fire_time, now)
        return min(value for value in (first, second) if value is not None) if first or second else None


def _standard_cron_trigger(expression: str, timezone):
    """APScheduler numbers Monday as 0; crontab numbers Sunday as 0/7."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron needs five fields")
    day = fields[4]
    if day != "*" and all(
        part.split("/", 1)[0] == "*"
        or part.split("/", 1)[0].replace("-", "").isdigit()
        for part in day.split(",")
    ):
        values: list[int] = []
        for part in day.split(","):
            base, _, step_text = part.partition("/")
            step = int(step_text) if step_text else 1
            if step < 1:
                raise ValueError("Cron weekday step must be positive")
            if base == "*":
                values.extend(range(0, 7, step))
            elif "-" in base:
                start, end = (int(value) for value in base.split("-", 1))
                if start > end:
                    raise ValueError("Cron weekday range must ascend")
                values.extend(range(start, end + 1, step))
            elif step_text:
                values.extend(range(int(base), 8, step))
            else:
                values.append(int(base))
        if any(value < 0 or value > 7 for value in values):
            raise ValueError("Cron weekday must be 0 through 7")
        fields[4] = ",".join(dict.fromkeys(_CRON_DAYS[value % 7] for value in values))
    if fields[2] != "*" and fields[4] != "*":
        month_day = fields.copy()
        month_day[4] = "*"
        week_day = fields.copy()
        week_day[2] = "*"
        return _OrCronTrigger(
            CronTrigger.from_crontab(" ".join(month_day), timezone=timezone),
            CronTrigger.from_crontab(" ".join(week_day), timezone=timezone),
        )
    return CronTrigger.from_crontab(" ".join(fields), timezone=timezone)


def _timezone(name: str):
    if name == "local":
        return get_localzone()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


@dataclass
class Schedule:
    kind: str  # cron | once | interval (interval preserves existing jobs)
    cron: str | None = None
    fire_at: str | None = None
    interval_seconds: int | None = None
    timezone: str = "local"

    def validate(self) -> None:
        tz = _timezone(self.timezone)
        if self.kind == "cron":
            if not self.cron:
                raise ValueError("cron is required")
            try:
                _standard_cron_trigger(self.cron, tz)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid cron expression: {self.cron}") from exc
        elif self.kind == "once":
            if not self.fire_at:
                raise ValueError("fire_at is required")
            try:
                datetime.fromisoformat(self.fire_at)
            except ValueError as exc:
                raise ValueError("fire_at must be an ISO datetime") from exc
        elif self.kind == "interval":
            if not self.interval_seconds or self.interval_seconds < 1:
                raise ValueError("interval_seconds must be positive")
        else:
            raise ValueError(f"Unknown schedule kind: {self.kind}")

    def label(self) -> str:
        if self.kind == "once":
            return f"单次 · {self.fire_at}"
        if self.kind == "interval":
            return f"每 {self.interval_seconds} 秒"
        return self.cron or ""


def next_fire_time(schedule: Schedule, *, after: float | None = None, run_count: int = 0) -> float | None:
    schedule.validate()
    now = time.time() if after is None else after
    tz = _timezone(schedule.timezone)
    if schedule.kind == "once":
        if run_count:
            return None
        dt = datetime.fromisoformat(schedule.fire_at or "")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        fire = dt.timestamp()
        return fire if fire > now else None
    if schedule.kind == "interval":
        return now + int(schedule.interval_seconds or 0)
    trigger = _standard_cron_trigger(schedule.cron or "", tz)
    nxt = trigger.get_next_fire_time(None, datetime.fromtimestamp(now, tz))
    return nxt.timestamp() if nxt else None


@dataclass
class Automation:
    title: str
    instructions: str
    schedule: Schedule
    id: str = field(default_factory=lambda: "auto-" + uuid.uuid4().hex[:12])
    source: str = "user"  # user | agent | skill | legacy
    skill_id: str | None = None
    workspace: str | None = None
    space_id: str | None = None
    project_id: str | None = None
    assistant_id: str | None = None
    session_mode: str = "single-agent"
    enabled_skill_ids: list[str] = field(default_factory=list)
    notify_on_completion: bool = True
    notify_target: str | None = None  # lark:<chat_id>, optional external completion notice
    always_allowed_tools: list[dict[str, str]] = field(default_factory=list)
    always_allowed_commands: list[str] = field(default_factory=list)
    auto_approve_commands: bool = False
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    next_run: float | None = None
    last_run: float | None = None
    last_status: str | None = None
    run_count: int = 0
    max_runs: int | None = None
    seen_runs_at: float = 0.0

    def to_dict(self) -> dict:
        return {**asdict(self), "schedule_label": self.schedule.label()}

    @classmethod
    def from_dict(cls, raw: dict) -> "Automation":
        data = dict(raw)
        data.pop("schedule_label", None)
        data["schedule"] = Schedule(**data["schedule"])
        return cls(**data)


@dataclass
class AutomationRun:
    task_id: str
    trigger: str
    run_id: str = field(default_factory=lambda: "run-" + uuid.uuid4().hex[:12])
    task_execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    scheduled_for: float | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"  # running | waiting_user | ok | error | skipped | interrupted | cancelled
    result_text: str = ""
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    notification_error: str | None = None
    resume_count: int = 0
    recovery_tools: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = f"__run__{self.run_id}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "AutomationRun":
        return cls(**raw)
