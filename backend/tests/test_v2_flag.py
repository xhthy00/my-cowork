from app.memory.embed import make_embed_config


def test_embed_disabled_without_model(monkeypatch):
    monkeypatch.delenv("MY_COWORK_EMBED_MODEL", raising=False)
    cfg = make_embed_config()
    assert cfg.enabled is False
    assert cfg.fn is None
