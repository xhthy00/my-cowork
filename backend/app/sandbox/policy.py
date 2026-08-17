"""L0/L1 sandbox execution policy and Skill confirm rules."""


class Policy:
    """Decide whether a tool call requires human confirmation.

    L0 short-circuits to silent for every tool (no guardrails active).
    L1 enforces: fs/exec always confirm; ``os.open_path`` is silent only when
    the running skill opts out via ``skill_req_confirm=False``; everything
    else is silent.
    """

    def __init__(self, level: str, skill_req_confirm: bool) -> None:
        self.level = level
        self.skill_req_confirm = skill_req_confirm

    def requires_confirm_for(self, tool: str) -> bool:
        if self.level == "L0":
            return False
        if self._is_fs_or_exec(tool):
            return True
        if tool == "os.open_path" or tool.endswith(".os.open_path"):
            return self.skill_req_confirm
        return False

    @staticmethod
    def _is_fs_or_exec(tool: str) -> bool:
        return any(part in ("fs", "exec") for part in tool.split("."))
