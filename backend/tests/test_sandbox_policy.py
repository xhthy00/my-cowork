from app.sandbox.policy import Policy


class TestSandboxPolicy:
    def test_os_open_path_silent_when_skill_quiet(self) -> None:
        policy = Policy(level="L1", skill_req_confirm=False)
        assert policy.requires_confirm_for("os.open_path") is False

    def test_fs_write_still_confirms_when_skill_quiet(self) -> None:
        policy = Policy(level="L1", skill_req_confirm=False)
        assert policy.requires_confirm_for("fs.write") is True

    def test_builtin_fs_write_still_confirms_when_skill_quiet(self) -> None:
        policy = Policy(level="L1", skill_req_confirm=False)
        assert policy.requires_confirm_for("builtin.fs.write") is True

    def test_exec_still_confirms_when_skill_quiet(self) -> None:
        policy = Policy(level="L1", skill_req_confirm=False)
        assert policy.requires_confirm_for("exec.bash") is True

    def test_os_open_path_confirms_when_skill_requires(self) -> None:
        policy = Policy(level="L1", skill_req_confirm=True)
        assert policy.requires_confirm_for("os.open_path") is True

    def test_l0_silences_every_tool(self) -> None:
        policy = Policy(level="L0", skill_req_confirm=False)
        for tool in ("fs.write", "exec.bash", "os.open_path"):
            assert policy.requires_confirm_for(tool) is False

    def test_l0_silences_even_when_skill_requires(self) -> None:
        policy = Policy(level="L0", skill_req_confirm=True)
        assert policy.requires_confirm_for("fs.write") is False
