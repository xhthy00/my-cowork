from pathlib import Path

import pytest

import app.skills as skills


@pytest.fixture
def layout(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.delenv("MY_COWORK_SKILLS_ROOT", raising=False)
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(tmp_path / "user-data"))
    monkeypatch.setattr(skills, "repo_root", lambda: tmp_path / "installation")
    old = tmp_path / "installation" / "skills"
    old.mkdir(parents=True)
    demo = old / "demo"
    demo.mkdir()
    (demo / "SKILL.md").write_text("---\nname: demo\n---\noriginal", encoding="utf-8")
    return old, tmp_path / "user-data" / "skills"


def test_default_root_is_user_writable_and_migration_keeps_original(layout):
    from app.skills.config import migrate_user_skills
    old, new = layout
    assert skills.default_user_skills_root() == new
    assert migrate_user_skills() == []
    assert (new / "demo" / "SKILL.md").read_bytes() == (old / "demo" / "SKILL.md").read_bytes()
    # Deleting an already migrated skill must not resurrect it on next launch.
    import shutil
    shutil.rmtree(new / "demo")
    assert migrate_user_skills() == []
    assert all(meta.id != "demo" for meta in skills.discover_skills())


def test_migration_never_overwrites_conflicts(layout):
    from app.skills.config import migrate_user_skills
    old, new = layout
    (new / "demo").mkdir(parents=True)
    (new / "demo" / "SKILL.md").write_text("---\nname: demo\n---\nnew version", encoding="utf-8")
    assert migrate_user_skills()
    assert "new version" in (new / "demo" / "SKILL.md").read_text()
    assert "original" in (old / "demo" / "SKILL.md").read_text()


def test_failed_copy_keeps_old_skill_available_and_can_retry(layout, monkeypatch):
    from app.skills.config import migrate_user_skills
    import shutil
    old, new = layout
    with monkeypatch.context() as patch:
        patch.setattr(shutil, "copytree", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        assert migrate_user_skills()
    assert skills.find_skill("demo").base_dir == old / "demo"
    assert migrate_user_skills() == []
    assert skills.find_skill("demo").base_dir == new / "demo"


def test_custom_user_root_keeps_bundled_examples(layout, monkeypatch, tmp_path):
    custom = tmp_path / "custom"
    example = tmp_path / "examples" / "builtin"
    example.mkdir(parents=True)
    (example / "SKILL.md").write_text("---\nname: builtin\n---\nexample", encoding="utf-8")
    monkeypatch.setenv("MY_COWORK_SKILLS_ROOT", str(custom))
    monkeypatch.setenv("MY_COWORK_EXAMPLE_SKILLS", str(example.parent))
    found = skills.discover_skills(custom)
    assert any(s.id == "builtin" and s.is_example for s in found)


@pytest.mark.parametrize("metadata", ["id: [broken", "- not-a-mapping", "id: broken\nparams: 42", "id: broken\nallowed_tools: 42"])
def test_invalid_legacy_skill_does_not_block_startup_or_other_skills(layout, monkeypatch, metadata):
    from fastapi.testclient import TestClient
    from app import main
    old, new = layout
    bad = old / "broken"
    bad.mkdir()
    (bad / "skill.yaml").write_text(metadata, encoding="utf-8")
    monkeypatch.setenv("MY_COWORK_ENABLE_SCHEDULER", "0")
    monkeypatch.setenv("MY_COWORK_CHANNEL_AUTOSTART", "0")
    monkeypatch.setenv("MY_COWORK_INDUSTRY_TOKEN", "isolated-migration-test")
    monkeypatch.setattr(main, "build_stack", lambda **kwargs: {"task_manager": object(), "bus": None, "confirm_hub": None})
    with TestClient(main.create_app()) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/api/skills", headers={"X-MyCowork-Industry-Token": "isolated-migration-test"})
        assert response.status_code == 200
        assert response.json()["warnings"]
        assert any(s["id"] == "demo" for s in response.json()["skills"])
    assert (bad / "skill.yaml").read_text(encoding="utf-8") == metadata
    assert (new / "demo/SKILL.md").is_file()
