#!/usr/bin/env python3
"""Compatible entry point for the shared host packer/checker."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.industry_apps.packing import build_zip, publish
from app.industry_apps.package import inspect_zip


def pack(source: Path, output: Path) -> None:
    publish(source, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', '--output', type=Path)
    parser.add_argument('--validate', action='store_true', help='Compatibility flag; output is always validated')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--replace', action='store_true', help='Replace the owned developer candidate file')
    args = parser.parse_args()
    try:
        if args.check:
            inspection = build_zip(args.source)[1] if args.source.is_dir() else inspect_zip(args.source.read_bytes())
        elif args.output:
            inspection = publish(args.source, args.output, replace=args.replace)
        else:
            parser.error('-o is required unless --check is used')
        result = {**inspection.public(), 'files': list(inspection.files), 'output': str(args.output) if args.output else None}
        print(json.dumps(result, ensure_ascii=False) if args.json else str(args.output or args.source))
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
