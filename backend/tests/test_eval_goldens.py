"""Golden fixtures scored by the v2 critic."""

from pathlib import Path

from eval.runner import load_goldens, run


def test_twenty_goldens_present():
    cases = load_goldens(Path(__file__).resolve().parents[1] / "eval" / "goldens")
    assert len(cases) >= 20
    cats = {c.get("category") for c in cases}
    assert {"qa", "search", "followup", "ppt", "gongwen", "research", "refuse"} <= cats


def test_golden_fixtures_pass_heuristic_gate():
    report = run(Path(__file__).resolve().parents[1] / "eval" / "goldens")
    assert report["failed"] == 0, report["rows"]
    assert report["passed"] >= 20
