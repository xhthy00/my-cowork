#!/usr/bin/env python3
"""Build a deterministic MyCowork industry application ZIP."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


def pack(source: Path, output: Path) -> None:
    source = source.resolve()
    if output.resolve().is_relative_to(source):
        raise ValueError("output ZIP must be outside the source directory")
    if not (source / "mycowork-app.yaml").is_file():
        raise ValueError("mycowork-app.yaml is missing")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("application source may not contain symbolic links")
    files = sorted(
        p for p in source.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and p.name != "checksums.sha256"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    checksums: list[str] = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            relative = file.relative_to(source).as_posix()
            content = file.read_bytes()
            checksums.append(hashlib.sha256(content).hexdigest() + "  " + relative)
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
        info = zipfile.ZipInfo("checksums.sha256", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, "\n".join(checksums) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    pack(args.source, args.output)
    print(args.output)
