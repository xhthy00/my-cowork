#!/usr/bin/env python3
"""Normalize raw legal text/HTML files into Markdown and JSON sidecars."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


TAG_RE = re.compile(r"<[^>]+>")


def normalize_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", raw)
    text = html.unescape(TAG_RE.sub("", raw))
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_source_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        result = subprocess.run(
            ["pdftotext", "-raw", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", errors="ignore")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--kb", default=DEFAULT_KB)
    args = parser.parse_args()
    kb = Path(args.kb)
    md_dir = kb / "02_clean" / "markdown"
    json_dir = kb / "02_clean" / "json"
    md_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    for input_name in args.inputs:
        path = Path(input_name)
        raw = read_source_text(path)
        text = normalize_text(raw)
        stem = path.stem
        md_path = md_dir / f"{stem}.md"
        json_path = json_dir / f"{stem}.json"
        md_path.write_text(f"# {stem}\n\n{text}\n", encoding="utf-8")
        json_path.write_text(json.dumps({"source_path": str(path), "title": stem, "text": text}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"normalized {path} -> {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
