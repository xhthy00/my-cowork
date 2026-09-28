import httpx
import pytest
from fastapi import FastAPI

from app.sandbox.path_guard import PathGuard, PathGuardError
from app.server.routes import workspace
from app.workspace.resolver import WorkspaceResolver


def test_absolute_desktop_named_folder_is_not_remapped(tmp_path):
    from app.sandbox.path_guard import normalize_user_path
    folder = tmp_path / "Desktop"
    folder.mkdir()
    assert normalize_user_path(str(folder / "report.txt")) == folder / "report.txt"


def test_concurrent_saves_keep_disk_and_permissions_consistent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    folders = [tmp_path / str(i) for i in range(8)]
    for folder in folders:
        folder.mkdir()
    config = tmp_path / "permissions.json"
    guard = PathGuard([], config_path=config)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda folder: guard.save_whitelist([str(folder)]), folders))
    assert guard.get_whitelist() == PathGuard(config_path=config).get_whitelist()


def test_internal_skill_resources_are_read_only(tmp_path, monkeypatch):
    from app.tools.builtin import fs
    resources = tmp_path / "skills"
    resources.mkdir()
    reference = resources / "reference.md"
    reference.write_text("skill reference", encoding="utf-8")
    private = tmp_path / "private.txt"
    private.write_text("private", encoding="utf-8")
    guard = PathGuard([], read_only_paths=[str(resources)])
    monkeypatch.setattr(fs, "_guard", guard)
    assert fs.fs_read.invoke({"path": str(reference)}) == "skill reference"
    assert "[ERROR]" in fs.fs_write.invoke({"path": str(reference), "content": "overwrite"})
    assert "[ERROR]" in fs.fs_read.invoke({"path": str(private)})
    assert reference.read_text(encoding="utf-8") == "skill reference"


def test_explicit_and_binding_permissions_are_independent(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    bound = [str(folder)]
    guard = PathGuard([], config_path=tmp_path / "permissions.json", workspace_paths=lambda: bound)
    guard.check_path(str(folder / "a.txt"))
    bound.clear()
    with pytest.raises(PathGuardError):
        guard.check_path(str(folder / "a.txt"))
    guard.save_whitelist([str(folder)])
    bound.append(str(folder))
    bound.clear()
    guard.check_path(str(folder / "a.txt"))
    restored = PathGuard(config_path=tmp_path / "permissions.json")
    restored.check_path(str(folder / "a.txt"))
    restored.save_whitelist([])
    with pytest.raises(PathGuardError):
        restored.check_path(str(folder / "a.txt"))


def test_failed_save_does_not_change_permissions(tmp_path, monkeypatch):
    guard = PathGuard([], config_path=tmp_path / "permissions.json")
    from pathlib import Path

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError):
        guard.save_whitelist([str(tmp_path)])
    with pytest.raises(PathGuardError):
        guard.check_path(str(tmp_path))


async def test_settings_and_workspace_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(tmp_path / "data"))
    resolver = WorkspaceResolver()
    monkeypatch.setattr(workspace, "get_workspace_resolver", lambda: resolver)
    app = FastAPI()
    app.include_router(workspace.router)
    from app.server.routes.permissions import router
    app.include_router(router)
    guard = PathGuard(config_path=tmp_path / "permissions.json", workspace_paths=lambda: [b.workspace_root for b in resolver.store.list_bindings()])
    app.state.path_guard = guard
    folder = tmp_path / "project"
    folder.mkdir()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/admin/whitelist")).json()["paths"] == []
        assert (await client.post("/api/workspace/bind", json={"space_id": "demo", "root_path": str(folder)})).status_code == 200
        guard.check_path(str(folder))
        await client.delete("/api/workspace/demo")
        with pytest.raises(PathGuardError):
            guard.check_path(str(folder))
        response = await client.post("/api/admin/whitelist", json={"paths": [str(folder)]})
        assert response.status_code == 200
        assert (await client.get("/api/admin/whitelist")).json()["paths"] == [str(folder.resolve())]
        guard.check_path(str(folder))
        assert (await client.post("/api/admin/whitelist", json={"paths": ["relative"]})).status_code == 400
