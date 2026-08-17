"""OfficeCLI detect / install / watch helpers."""

from app.tools.officecli.resolve import resolve_officecli, probe_watch
from app.tools.officecli.watch_manager import WatchManager

__all__ = ["resolve_officecli", "probe_watch", "WatchManager"]
