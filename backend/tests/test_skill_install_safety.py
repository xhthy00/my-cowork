"""Skill installation must never replace files outside its owned directory."""

import base64
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.server.routes.skills import router
from app.skills.config import import_skill_zip


def skill_zip(skill_id: str, filename: str = "skill.yaml") -> bytes:
    content = (f"id: {json.dumps(skill_id)}\nprompt: demo\n" if filename == "skill.yaml"
               else f"---\nname: {json.dumps(skill_id)}\n---\ndemo\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(f"package/{filename}", content)
    return buf.getvalue()


@pytest.mark.parametrize("filename", ["skill.yaml", "SKILL.md"])
def test_rejects_metadata_escape_before_touching_existing_files(tmp_path, filename):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    with pytest.raises(ValueError):
        import_skill_zip(skill_zip("../outside", filename), root=tmp_path / "skills")
    assert sentinel.read_text() == "keep"


@pytest.mark.parametrize("entry", ["import", "hub"])
async def test_both_install_routes_reject_escape(tmp_path, monkeypatch, entry):
    app = FastAPI()
    app.include_router(router)
    app.state.skills_root = tmp_path / "skills"
    payload = skill_zip("../outside")

    async def download(*_):
        return payload

    monkeypatch.setattr("app.server.routes.skills.download_hub_skill", download)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        if entry == "import":
            response = await client.post("/api/skills/import", json={"zip_base64": base64.b64encode(payload).decode()})
        else:
            response = await client.post("/api/skillhub/install", json={"handle": "user", "slug": "demo"})
    assert response.status_code == 400
    assert not (tmp_path / "outside").exists()


def test_valid_skill_installs_and_updates(tmp_path):
    root = tmp_path / "skills"
    meta = import_skill_zip(skill_zip("demo"), root=root)
    assert meta.id == "demo"
    assert meta.base_dir == root / "demo"
    import_skill_zip(skill_zip("demo", "SKILL.md"), root=root)
    assert (root / "demo" / "SKILL.md").is_file()
    assert not (root / "demo" / "skill.yaml").exists()


@pytest.mark.parametrize("skill_id", ["/absolute", "C:\\outside", "C:outside", "..\\outside", "demo:stream", "NUL", "CON.txt", "demo.", "demo "])
def test_rejects_cross_platform_special_paths(tmp_path, skill_id):
    with pytest.raises(ValueError):
        import_skill_zip(skill_zip(skill_id), root=tmp_path / "skills")


def test_linked_install_destination_is_rejected(tmp_path):
    import os
    import subprocess
    root, outside = tmp_path / "skills", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    link = root / "demo"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        import_skill_zip(skill_zip("demo"), root=root)
    assert (outside / "keep.txt").read_text() == "keep"


def test_copy_failure_keeps_previous_install(tmp_path, monkeypatch):
    import shutil
    root = tmp_path / "skills"
    import_skill_zip(skill_zip("demo"), root=root)
    previous = (root / "demo" / "skill.yaml").read_bytes()
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(shutil, "copytree", fail)
    with pytest.raises(OSError):
        import_skill_zip(skill_zip("demo", "SKILL.md"), root=root)
    assert (root / "demo" / "skill.yaml").read_bytes() == previous


def test_failed_replace_and_rollback_preserve_backup(tmp_path, monkeypatch):
    from pathlib import Path
    root = tmp_path / "skills"
    import_skill_zip(skill_zip("demo"), root=root)
    previous = (root / "demo" / "skill.yaml").read_bytes()
    rename = Path.rename
    def fail_install_and_restore(source, target):
        if source.name in {"new", "old"}:
            raise PermissionError("file locked")
        return rename(source, target)
    monkeypatch.setattr(Path, "rename", fail_install_and_restore)
    with pytest.raises(OSError):
        import_skill_zip(skill_zip("demo", "SKILL.md"), root=root)
    backups = list(root.glob(".install-*/old/skill.yaml"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == previous
