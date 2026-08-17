import pytest

from app.guardrails.command_filter import CommandForbidden, CommandFilter


class TestCommandFilter:
    def test_allows_safe_command(self) -> None:
        cf = CommandFilter()
        cf.check("ls -la /home/user")

    def test_allows_rm_under_tmp(self) -> None:
        cf = CommandFilter()
        cf.check("rm -rf /tmp/old-build")

    def test_allows_rm_under_workspace_absolute_path(self) -> None:
        cf = CommandFilter()
        cf.check("rm -rf /Users/me/project/_scratch/unpacked")
        cf.check("rm -rf /var/folders/xx/T/officecli-tmp")
        cf.check("rm -rf ./out")

    def test_blocks_rm_rf_root(self) -> None:
        cf = CommandFilter()
        with pytest.raises(CommandForbidden):
            cf.check("rm -rf /")
        with pytest.raises(CommandForbidden):
            cf.check("rm -rf /*")

    def test_blocks_chmod_777_root(self) -> None:
        cf = CommandFilter()
        with pytest.raises(CommandForbidden):
            cf.check("chmod -R 777 /")

    def test_blocks_dd_zero(self) -> None:
        cf = CommandFilter()
        with pytest.raises(CommandForbidden):
            cf.check("dd if=/dev/zero of=/dev/sda bs=1M")

    def test_blocks_mkfs(self) -> None:
        cf = CommandFilter()
        with pytest.raises(CommandForbidden):
            cf.check("mkfs.ext4 /dev/sda1")

    def test_blocks_mid_command_match(self) -> None:
        cf = CommandFilter()
        with pytest.raises(CommandForbidden):
            cf.check("bash -c 'rm -rf /'")

    def test_allows_list_with_similar_tokens(self) -> None:
        cf = CommandFilter()
        cf.check("chmod -R 755 /tmp/allowed")
        cf.check("rm -rf /tmp/allowed")
