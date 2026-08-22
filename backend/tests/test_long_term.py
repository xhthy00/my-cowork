"""Tests for long-term vector memory."""

from pathlib import Path

from app.llm.gateway import local_embed
from app.memory.long_term import LongTermStore, extract_remember_content
from app.runtime.context import inject_memories


def test_write_query_returns_related(tmp_path: Path):
    store = LongTermStore(tmp_path / "m.db", embed_fn=lambda t: local_embed(t, dim=64))
    store.write("喜欢喝美式咖啡", kind="pref")
    store.write("项目代号是北极星", kind="fact")
    store.write("周末去爬山", kind="plan")
    hits = store.query("咖啡偏好", k=3)
    contents = [h["content"] for h in hits]
    assert any("咖啡" in c for c in contents)
    store.close()


def test_query_disabled_without_semantic_embed(tmp_path: Path):
    store = LongTermStore(tmp_path / "m-off.db")
    assert store.semantic_enabled is False
    store.write("喜欢喝美式咖啡", kind="pref")
    assert store.query("咖啡偏好", k=3) == []
    store.close()


def test_store_starts_without_sqlite_load_extension(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.memory.long_term._load_sqlite_vec", lambda _conn: False)
    store = LongTermStore(tmp_path / "m-novec.db", embed_fn=lambda t: local_embed(t, dim=64))
    assert store.vec_ready is False
    assert store.semantic_enabled is False
    store.write("喜欢喝美式咖啡", kind="pref")
    assert store.list_recent()[0]["content"] == "喜欢喝美式咖啡"
    assert store.query("咖啡偏好", k=3) == []
    store.close()


def test_remember_keyword_extract():
    assert extract_remember_content("请记住 我喜欢用简洁模板") == "我喜欢用简洁模板"
    assert extract_remember_content("写个 PPT") is None


def test_inject_memories_writes_and_prepends(tmp_path: Path):
    store = LongTermStore(tmp_path / "m2.db", embed_fn=lambda t: local_embed(t, dim=64))
    msgs = inject_memories("记住 桌面路径是 ~/Desktop", store)
    assert any(getattr(m, "type", None) == "system" or m.__class__.__name__ == "SystemMessage" for m in msgs)
    hits = store.query("桌面路径", k=2)
    assert any("Desktop" in h["content"] or "桌面" in h["content"] for h in hits)
    store.close()


def test_inject_memories_includes_history():
    msgs = inject_memories(
        "生成图文并茂的 ppt",
        None,
        history=[
            {"role": "user", "content": "写一份湖北宜昌旅游攻略"},
            {
                "role": "assistant",
                "content": "宜昌三日游推荐…\n\n[已生成文件: ~/Desktop/宜昌.docx]",
            },
            {"role": "user", "content": "生成图文并茂的 ppt"},  # duplicate of current — skipped
        ],
    )
    texts = [str(getattr(m, "content", "")) for m in msgs]
    assert any("宜昌" in t for t in texts)
    assert any("已生成文件" in t for t in texts)
    # Current user turn appears once at the end.
    assert texts[-1] == "生成图文并茂的 ppt"
    assert sum(1 for t in texts if t == "生成图文并茂的 ppt") == 1
    assert any("follow-up" in t.lower() for t in texts)


def test_history_strips_think_blocks():
    msgs = inject_memories(
        "大数据集团介入需要注意哪些",
        None,
        history=[
            {"role": "user", "content": "写一份合资方案评审"},
            {
                "role": "assistant",
                "content": "<think>I will generate a docx. Plan the task first.</think>\n评审结论：建议谨慎参股。",
            },
        ],
    )
    texts = [str(getattr(m, "content", "")) for m in msgs]
    assert any("评审结论" in t for t in texts)
    assert not any("<think>" in t for t in texts)
    assert not any("Plan the task" in t for t in texts)


def test_looks_like_plan_only():
    from app.runtime.context import looks_like_plan_only

    assert looks_like_plan_only(
        "大数据集团介入需要注意哪些",
        "<think>plan</think>\nI will generate a formal consultation analysis report (docx). Plan the task first.",
    )
    assert not looks_like_plan_only(
        "大数据集团介入需要注意哪些",
        "需要注意三方面：\n1. 股权比例与一票否决\n2. 数据合规与出境\n3. 合资公司治理与人员派出\n"
        "另外还应关注估值、对赌、退出和关联交易审查。" * 2,
    )
    assert not looks_like_plan_only(
        "Python 里 list 和 tuple 的区别是什么？",
        "list 可变，tuple 不可变。list 用方括号，tuple 用圆括号。",
    )
