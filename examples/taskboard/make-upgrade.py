"""Build the v2 migration example without changing the original v1 sample.

Run with the host backend Python: make-upgrade.py OUTPUT.zip
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml


def main(output: Path):
    source = Path(__file__).resolve().parent
    repo = source.parents[1]
    with tempfile.TemporaryDirectory(prefix="taskboard-v2-") as temporary:
        target = Path(temporary) / "app"
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "make-upgrade.py"))
        manifest_path = target / "mycowork-app.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest.update(schema_version=2, version="1.1.0", min_host_version=json.loads((repo / "package.json").read_text())["version"])
        manifest["data"].update(version=1, upgrade_from=["legacy"], migration_entry="mcapp_cn_example_taskboard.migrations:migrate")
        manifest["backend"]["health_entry"] = "mcapp_cn_example_taskboard.migrations:check"
        manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
        plugin = target / "backend/mcapp_cn_example_taskboard/plugin.py"
        plugin.write_text(plugin.read_text(encoding="utf-8").replace(
            "done INTEGER NOT NULL DEFAULT 0)", "done INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '')"
        ), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("pack_industry_app", repo / "scripts/pack-industry-app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.pack(target, output)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
