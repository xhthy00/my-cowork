from app.memory.embed import make_embed_config
from app.runtime.v2.flag import is_v2, runtime_version


def test_embed_disabled_without_model(monkeypatch):
    monkeypatch.delenv("MY_COWORK_EMBED_MODEL", raising=False)
    cfg = make_embed_config()
    assert cfg.enabled is False
    assert cfg.fn is None


def test_runtime_flag_reads_env(monkeypatch):
    monkeypatch.setenv("MY_COWORK_RUNTIME", "v2")
    assert runtime_version() == "v2"
    assert is_v2() is True
    monkeypatch.setenv("MY_COWORK_RUNTIME", "v1")
    assert is_v2() is False
