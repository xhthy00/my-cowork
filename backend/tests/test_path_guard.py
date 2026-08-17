from pathlib import Path

import pytest

from app.sandbox.path_guard import (
    PathGuard,
    PathGuardError,
    desktop_dir,
    normalize_user_path,
    resolve_write_path,
)
from app.runtime.workspace_context import (
    WorkspaceRuntime,
    reset_workspace_runtime,
    set_workspace_runtime,
)


class TestPathGuard:
    def test_path_inside_whitelist_allowed(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        guard = PathGuard([str(allowed)])

        guard.check_path(str(allowed / "nested" / "file.txt"))

    def test_path_outside_whitelist_rejected(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        guard = PathGuard([str(allowed)])

        with pytest.raises(PathGuardError):
            guard.check_path(str(outside / "file.txt"))

    def test_path_traversal_rejected(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        guard = PathGuard([str(allowed)])

        with pytest.raises(PathGuardError):
            guard.check_path(str(allowed / "subdir" / ".." / ".." / "outside.txt"))

    def test_symlink_outside_whitelist_rejected(self, tmp_path):
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        symlink = allowed / "link"
        symlink.symlink_to(outside)
        guard = PathGuard([str(allowed)])

        with pytest.raises(PathGuardError):
            guard.check_path(str(symlink / "file.txt"))

    def test_instances_have_independent_whitelists(self):
        guard_a = PathGuard(["/tmp/a"])
        guard_b = PathGuard(["/tmp/b"])

        guard_a.check_path("/tmp/a/file.txt")
        with pytest.raises(PathGuardError):
            guard_b.check_path("/tmp/a/file.txt")

    def test_desktop_alias_allowed_when_home_whitelisted(self):
        guard = PathGuard([str(Path.home())])
        guard.check_path("../Desktop/hello.txt")
        guard.check_path("桌面/hello.txt")


class TestNormalizeUserPath:
    def test_desktop_aliases_map_to_real_desktop(self):
        desk = desktop_dir()
        assert normalize_user_path("Desktop") == desk
        assert normalize_user_path("桌面") == desk
        assert normalize_user_path("~/Desktop") == desk
        assert normalize_user_path("../Desktop") == desk
        assert normalize_user_path("./Desktop/hello.txt") == desk / "hello.txt"
        assert normalize_user_path("桌面/hello.txt") == desk / "hello.txt"

    def test_relative_file_resolves_under_home(self):
        assert normalize_user_path("hello.txt") == (Path.home() / "hello.txt").resolve()


class TestResolveWritePath:
    def test_desktop_remapped_to_workdir(self, tmp_path):
        work = tmp_path / "workdir"
        work.mkdir()
        tok = set_workspace_runtime(
            WorkspaceRuntime(
                space_id="s",
                project_id="p",
                task_id="t",
                working_directory=work,
                task_output_root=work,
                workdir_mode="artifact-only",
            )
        )
        try:
            desk = desktop_dir()
            got = resolve_write_path(str(desk / "report.html"))
            assert got == (work / "report.html").resolve()
            keep = resolve_write_path(str(work / "keep.pdf"))
            assert keep == (work / "keep.pdf").resolve()
        finally:
            reset_workspace_runtime(tok)
