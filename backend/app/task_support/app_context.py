"""Effective host-owned scope for one plugin-originated execution."""
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from typing import Callable
from app.skills import SkillMeta


@dataclass(frozen=True)
class AppTaskScope:
    app_id: str
    tools: frozenset[str]
    business: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    output_dir: str = ''
    record_file: Callable | None = field(default=None, compare=False)
    record_operation: Callable | None = field(default=None, compare=False)
    artifacts: list[str] = field(default_factory=list, compare=False)
    skills: dict[str, SkillMeta] = field(default_factory=dict)
    record_skills: Callable | None = field(default=None, compare=False)


app_task_scope: ContextVar[AppTaskScope | None] = ContextVar('app_task_scope', default=None)


def scoped_tools(tools):
    scope = app_task_scope.get()
    return [tool for tool in tools if tool.name in scope.tools] if scope else [tool for tool in tools if tool.name not in {'app_read_file', 'app_write_report'}]
