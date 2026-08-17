#!/usr/bin/env python3
"""Simple local KB search over markdown/json text files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


def iter_files(kb: Path):
    for root in ["00_registry", "02_clean", "03_chunks", "05_contract_assets", "06_internal", "07_evals"]:
        base = kb / root
        if base.exists():
            yield from base.rglob("*.md")
            yield from base.rglob("*.json")
            yield from base.rglob("*.yaml")
            yield from base.rglob("*.yml")


def read_text(path: Path) -> str:
    try:
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(obj, ensure_ascii=False)
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def score(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(len(re.findall(re.escape(term.lower()), lowered)) for term in terms)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    terms = [t for t in re.split(r"\s+", args.query.strip()) if t]
    hits = []
    for path in iter_files(Path(args.kb)):
        text = read_text(path)
        s = score(text, terms)
        if s:
            snippet = re.sub(r"\s+", " ", text)[:300]
            hits.append((s, path, snippet))
    hits.sort(key=lambda item: item[0], reverse=True)
    for s, path, snippet in hits[: args.limit]:
        print(f"[{s}] {path}\n  {snippet}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
