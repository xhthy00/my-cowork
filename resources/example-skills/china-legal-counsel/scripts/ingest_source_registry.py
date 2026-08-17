#!/usr/bin/env python3
"""Validate and summarize the legal-counsel KB source registry."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


def parse_simple_yaml_list(path: Path) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("- "):
            if current:
                items.append(current)
            current = {}
            rest = line[2:].strip()
            if rest:
                key, value = split_kv(rest)
                current[key] = clean(value)
        elif current is not None and re.match(r"\s+[A-Za-z0-9_]+:", line):
            key, value = split_kv(line.strip())
            current[key] = clean(value)
    if current:
        items.append(current)
    return items


def split_kv(text: str) -> tuple[str, str]:
    if ":" not in text:
        return text.strip(), ""
    key, value = text.split(":", 1)
    return key.strip(), value.strip()


def clean(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", default=DEFAULT_KB)
    args = parser.parse_args()
    registry = Path(args.kb) / "00_registry" / "sources.yaml"
    if not registry.exists():
        raise SystemExit(f"missing registry: {registry}")
    rows = parse_simple_yaml_list(registry)
    required = {"id", "name", "url", "authority_level", "source_type"}
    errors = []
    for idx, row in enumerate(rows, 1):
        missing = required - row.keys()
        if missing:
            errors.append(f"row {idx} missing: {', '.join(sorted(missing))}")
    by_level: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_level[row.get("authority_level", "UNKNOWN")] = by_level.get(row.get("authority_level", "UNKNOWN"), 0) + 1
        by_type[row.get("source_type", "UNKNOWN")] = by_type.get(row.get("source_type", "UNKNOWN"), 0) + 1
    print(f"sources: {len(rows)}")
    print("by_level:", dict(sorted(by_level.items())))
    print("by_type:", dict(sorted(by_type.items())))
    if errors:
        print("errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
