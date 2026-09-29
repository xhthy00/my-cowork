from __future__ import annotations

import importlib.util
import asyncio
import io
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.industry_apps.loader import load_enabled_apps
from app.industry_apps.sdk import LoadedAppTool
from app.industry_apps.tooling import make_agent_tool
from app.industry_apps.package import (
    AppPackageError,
    inspect_zip,
    install_zip,
    list_installed,
    rollback_app,
)
from app.main import create_app


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "taskboard"
PACK_SCRIPT = ROOT / "scripts" / "pack-industry-app.py"


def _example_zip(tmp_path: Path) -> bytes:
    spec = importlib.util.spec_from_file_location("pack_industry_app", PACK_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "taskboard.zip"
    module.pack(EXAMPLE, output)
    return output.read_bytes()


def test_install_and_load_taskboard_in_existing_fastapi_process(tmp_path: Path) -> None:
    raw = _example_zip(tmp_path)
    inspection = inspect_zip(raw)
    root = tmp_path / "installed"
    installed = install_zip(raw, inspection.sha256, root)
    assert installed["requires_restart"] is True
    assert list_installed(root)[0]["status"] == "pending_restart"

    app = FastAPI()
    loaded_tools: list[LoadedAppTool] = []
    assert load_enabled_apps(app, root, tool_sink=loaded_tools) == [{"id": "cn.example.taskboard", "status": "ready"}]
    client = TestClient(app)
    created = client.post(
        "/api/apps/cn.example.taskboard/tasks",
        json={"title": "核对订单"},
    )
    assert created.status_code == 200
    assert created.json()["id"] == 1
    assert client.get("/api/apps/cn.example.taskboard/tasks").json()["tasks"] == [
        {"id": 1, "title": "核对订单", "done": False}
    ]
    assert len(loaded_tools) == 1
    agent_tool = make_agent_tool(loaded_tools[0], None)
    assert agent_tool.name == "industry__cn_example_taskboard__list_tasks"
    assert agent_tool.metadata["tool_source"] == "industry_app"
    assert asyncio.run(agent_tool.ainvoke({})) == {
        "total": 1, "tasks": [{"id": 1, "title": "核对订单", "done": False}]
    }
    assert list_installed(root)[0]["status"] == "ready"


def test_rejects_package_changed_after_inspection(tmp_path: Path) -> None:
    raw = _example_zip(tmp_path)
    with pytest.raises(AppPackageError, match="changed after inspection"):
        install_zip(raw, "0" * 64, tmp_path / "installed")
    assert not (tmp_path / "installed").exists()


def test_rejects_zip_path_traversal(tmp_path: Path) -> None:
    raw = _example_zip(tmp_path)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../outside.txt", "bad")
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            for item in source.infolist():
                archive.writestr(item, source.read(item.filename))
    with pytest.raises(AppPackageError, match="invalid ZIP path"):
        inspect_zip(payload.getvalue())
    assert not (tmp_path / "outside.txt").exists()


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    raw = _example_zip(tmp_path)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            for item in source.infolist():
                content = source.read(item.filename)
                if item.filename == "frontend/dist/index.html":
                    content += b"<script>changed</script>"
                archive.writestr(item, content)
    with pytest.raises(AppPackageError, match="checksum mismatch"):
        inspect_zip(payload.getvalue())


def test_rejects_native_extension_in_python_package(tmp_path: Path) -> None:
    raw = _example_zip(tmp_path)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            for item in source.infolist():
                archive.writestr(item, source.read(item.filename))
        archive.writestr("backend/mcapp_cn_example_taskboard/native.so", b"binary")
    with pytest.raises(AppPackageError, match="native or bytecode"):
        inspect_zip(payload.getvalue())


def test_update_can_roll_back_to_previous_version(tmp_path: Path) -> None:
    original = _example_zip(tmp_path)
    root = tmp_path / "installed"
    install_zip(original, inspect_zip(original).sha256, root)

    updated_source = tmp_path / "updated-source"
    shutil.copytree(EXAMPLE, updated_source)
    manifest = updated_source / "mycowork-app.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("version: 1.0.0", "version: 1.0.1"),
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("pack_industry_app_update", PACK_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "updated.zip"
    module.pack(updated_source, output)
    updated = output.read_bytes()
    install_zip(updated, inspect_zip(updated).sha256, root)
    assert list_installed(root)[0]["previous_version"] == "1.0.0"

    result = rollback_app("cn.example.taskboard", root)
    assert result["version"] == "1.0.0"
    assert list_installed(root)[0]["version"] == "1.0.0"


def test_main_app_exposes_installed_app_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = _example_zip(tmp_path)
    root = tmp_path / "installed"
    install_zip(raw, inspect_zip(raw).sha256, root)
    monkeypatch.setenv("MY_COWORK_INDUSTRY_APPS_ROOT", str(root))
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MY_COWORK_INDUSTRY_TOKEN", "test-only-token")

    client = TestClient(create_app(task_manager=object()))
    assert client.get("/api/industry-apps").status_code == 403
    headers = {"X-MyCowork-Industry-Token": "test-only-token"}
    assert client.get("/api/industry-apps", headers=headers).json()["apps"][0]["status"] == "ready"
    response = client.post(
        "/api/apps/cn.example.taskboard/tasks",
        json={"title": "检查库存"},
        headers=headers,
    )
    assert response.status_code == 200
