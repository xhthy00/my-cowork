#!/usr/bin/env python3
"""Chunk normalized legal documents by article, issue, or contract clause."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


ARTICLE_RE = re.compile(r"(?m)^\s*(第[一二三四五六七八九十百千万0-9]+条)\s*")
CLAUSE_RE = re.compile(r"(?m)^\s*([一二三四五六七八九十]+、|第[一二三四五六七八九十百千万0-9]+条|\d+(?:\.\d+)*[、.])\s*")


def split_by_pattern(text: str, pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    matches = list(pattern.finditer(text))
    if not matches:
        return [("chunk-001", text.strip())] if text.strip() else []
    chunks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        label = match.group(1)
        chunks.append((label, text[start:end].strip()))
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--kind", choices=["law", "case", "contract"], default="law")
    args = parser.parse_args()
    kb = Path(args.kb)
    out_subdir = {
        "law": "laws_by_article",
        "case": "cases_by_issue",
        "contract": "templates_by_clause",
    }[args.kind]
    out_dir = kb / "03_chunks" / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = ARTICLE_RE if args.kind == "law" else CLAUSE_RE
    for input_name in args.inputs:
        path = Path(input_name)
        text = path.read_text(encoding="utf-8")
        if text.startswith("# "):
            text = "\n".join(text.splitlines()[1:]).strip()
        chunks = split_by_pattern(text, pattern)
        rows = []
        for idx, (label, chunk_text) in enumerate(chunks, 1):
            chunk_id = f"{path.stem}-{idx:04d}"
            rows.append({"chunk_id": chunk_id, "label": label, "source_path": str(path), "text": chunk_text})
            (out_dir / f"{chunk_id}.md").write_text(f"# {label}\n\n{chunk_text}\n", encoding="utf-8")
        (out_dir / f"{path.stem}.chunks.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"chunked {path}: {len(rows)} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
