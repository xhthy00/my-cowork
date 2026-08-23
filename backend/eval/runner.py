"""Golden-set runner for cognition quality gates.

Usage (from backend/):

    PYTHONPATH=. uv run python eval/runner.py

Live LLM comparison requires MY_COWORK_EVAL_LIVE=1 and a configured model.
Default mode scores the fixture transcripts with the v2 evidence_gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

ROOT = Path(__file__).resolve().parent
GOLDENS = ROOT / "goldens"


def _msg(row: dict[str, Any]) -> Any:
    role = str(row.get("type") or row.get("role") or "ai")
    content = str(row.get("content") or "")
    name = row.get("name")
    if role in {"human", "user"}:
        return HumanMessage(content=content)
    if role in {"system"}:
        return SystemMessage(content=content)
    if role in {"tool"}:
        return ToolMessage(
            content=content,
            tool_call_id=str(row.get("tool_call_id") or name or "t"),
            name=str(name or ""),
        )
    calls = row.get("tool_calls") or []
    return AIMessage(content=content, tool_calls=list(calls), name=name)


def load_goldens(root: Path = GOLDENS) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            continue
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get("cases"), list):
            items = data["cases"]
        elif isinstance(data, dict):
            items = [data]
        else:
            continue
        for item in items:
            if isinstance(item, dict):
                item = dict(item)
                item.setdefault("file", path.name)
                cases.append(item)
    return cases


def score_case(case: dict[str, Any]) -> dict[str, Any]:
    from app.runtime.v2.critic import evidence_gate

    user = str(case.get("user") or "")
    fixture = case.get("fixture") or {}
    raw_msgs = fixture.get("messages") if isinstance(fixture, dict) else []
    messages = [_msg(m) for m in (raw_msgs or []) if isinstance(m, dict)]
    verdict = evidence_gate(user, messages)
    expect = case.get("expect") or {}
    want_next = str(expect.get("next") or "").strip()
    ok = True
    reasons: list[str] = []
    if want_next and verdict.next != want_next:
        ok = False
        reasons.append(f"next={verdict.next} want={want_next}")
    if expect.get("not_plan_only") and not verdict.user_facing_complete:
        ok = False
        reasons.append("plan-only or empty answer")
    if expect.get("sources_ok") is True and not verdict.sources_ok:
        ok = False
        reasons.append("sources missing")
    if expect.get("deliverable_ok") is True and not verdict.deliverable_ok:
        ok = False
        reasons.append("deliverable missing")
    return {
        "id": case.get("id") or case.get("user"),
        "category": case.get("category"),
        "ok": ok,
        "next": verdict.next,
        "missing": verdict.missing,
        "reasons": reasons,
        "runtime": "v2",
    }


def run(root: Path = GOLDENS) -> dict[str, Any]:
    cases = load_goldens(root)
    rows = [score_case(c) for c in cases]
    passed = sum(1 for r in rows if r["ok"])
    return {
        "total": len(rows),
        "passed": passed,
        "failed": len(rows) - passed,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MyCowork goldens")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"goldens {report['passed']}/{report['total']} passed")
        for row in report["rows"]:
            mark = "ok" if row["ok"] else "FAIL"
            extra = f" {row['reasons']}" if row["reasons"] else ""
            print(f"  [{mark}] {row['id']} next={row['next']}{extra}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT.parent))
    raise SystemExit(main())
