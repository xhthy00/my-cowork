#!/usr/bin/env python3
"""Check whether citation strings appear in the local legal-counsel KB."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


CITATION_RE = re.compile(
    r"(《[^》]{2,80}》(?:第[一二三四五六七八九十百千万0-9]+条(?:第[一二三四五六七八九十百千万0-9]+款)?)?|（?\(?\d{4}\)?[\u4e00-\u9fa5A-Za-z0-9第初终再执行民刑知行商\-号]+)"
)


def collect_text(kb: Path) -> str:
    parts: list[str] = []
    for base_name in ["02_clean", "03_chunks", "00_registry", "05_contract_assets", "06_internal"]:
        base = kb / base_name
        if base.exists():
            for path in base.rglob("*"):
                if path.suffix.lower() in {".md", ".json", ".yaml", ".yml", ".txt"}:
                    try:
                        parts.append(path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="file containing legal output to verify")
    parser.add_argument("--kb", default=DEFAULT_KB)
    args = parser.parse_args()
    text = Path(args.input).read_text(encoding="utf-8")
    citations = sorted(set(m.group(0) for m in CITATION_RE.finditer(text)))
    corpus = collect_text(Path(args.kb))
    if not citations:
        print("WARN no citation-like strings found")
        return 0
    failed = 0
    for citation in citations:
        title = re.match(r"《[^》]+》", citation)
        probe = title.group(0) if title else citation
        if probe in corpus:
            print(f"PASS {citation}")
        else:
            print(f"FAIL {citation}")
            failed += 1
    print(f"checked={len(citations)} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
