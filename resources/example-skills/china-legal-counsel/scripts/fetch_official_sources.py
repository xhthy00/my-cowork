#!/usr/bin/env python3
"""Fetch public official legal sources listed in the local registry.

This is a conservative bootstrap fetcher. It stores raw HTML/PDF bytes and a
sidecar metadata file. Dynamic or login-gated sites should be registered but
left for a specialized fetcher.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

from ingest_source_registry import parse_simple_yaml_list

DEFAULT_KB = str(Path(__file__).resolve().parents[1] / "knowledge-base")


def safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)[:120]


def target_dir(kb: Path, source_type: str) -> Path:
    mapping = {
        "official_law": "official_laws",
        "official_case": "cases",
        "judicial_interpretation": "judicial_interpretations",
        "regulator": "regulators",
        "template": "templates",
        "standard": "regulators",
    }
    return kb / "01_raw" / mapping.get(source_type, "regulators")


def fetch_url(url: str) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Codex legal-counsel-kb bootstrap"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read(), resp.headers.get("content-type", ""), "urllib"
    except Exception:
        cmd = [
            "curl",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "60",
            "-A",
            "Codex legal-counsel-kb bootstrap",
        ]
        if "wb.flk.npc.gov.cn" in url:
            # The national laws database currently serves some files with a
            # certificate chain that local Python rejects; retain URL metadata
            # and use curl's explicit insecure fallback only for this host.
            cmd.append("-k")
        cmd.append(url)
        result = subprocess.run(cmd, check=True, capture_output=True)
        return result.stdout, "", "curl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--level", default="P0")
    parser.add_argument("--ids", default="", help="comma-separated source ids to fetch")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    kb = Path(args.kb)
    rows = parse_simple_yaml_list(kb / "00_registry" / "sources.yaml")
    wanted_ids = {item.strip() for item in args.ids.split(",") if item.strip()}
    if wanted_ids:
        selected = [r for r in rows if r.get("id") in wanted_ids and r.get("full_text_allowed", "false").lower() == "true"]
    else:
        selected = [r for r in rows if r.get("authority_level") == args.level and r.get("full_text_allowed", "false").lower() == "true"]
    if args.limit:
        selected = selected[: args.limit]
    fetched = 0
    for row in selected:
        url = row.get("url", "")
        if not url.startswith(("http://", "https://")):
            continue
        out_dir = target_dir(kb, row.get("source_type", "regulator"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        base = f"{safe_name(row.get('id', 'source'))}-{stamp}"
        try:
            data, content_type, fetched_by = fetch_url(url)
            suffix = ".pdf" if "pdf" in content_type or url.lower().endswith(".pdf") else ".html"
            raw_path = out_dir / f"{base}{suffix}"
            raw_path.write_bytes(data)
            meta = dict(row)
            meta.update({"fetched_at": stamp, "content_type": content_type, "raw_path": str(raw_path), "fetched_by": fetched_by})
            (out_dir / f"{base}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"fetched {row.get('id')}: {raw_path}")
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            print(f"failed {row.get('id')} {url}: {exc}")
    print(f"fetched_count: {fetched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
