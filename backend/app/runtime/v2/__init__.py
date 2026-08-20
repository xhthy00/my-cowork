"""v2 cognition runtime: session Act loop, critic, compact, synthesize."""

from app.runtime.v2.flag import is_v2, runtime_version
from app.runtime.v2.loop import run_act_loop
from app.runtime.v2.session import append_run, load_thread, save_thread

__all__ = [
    "is_v2",
    "runtime_version",
    "run_act_loop",
    "load_thread",
    "save_thread",
    "append_run",
]
