"""Import enabled application routers into the existing FastAPI process."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.industry_apps.package import app_root, list_installed, set_app_status
from app.industry_apps.sdk import AppContext, AppContribution


def load_enabled_apps(app: FastAPI, root: Path | None = None) -> list[dict[str, Any]]:
    base = app_root(root)
    results: list[dict[str, Any]] = []
    for entry in list_installed(base):
        if not entry.get("enabled"):
            continue
        app_id = entry["id"]
        manifest = entry["manifest"]
        version = entry["version"]
        package = base / "packages" / app_id / version
        backend = package / "backend"
        try:
            if not backend.is_dir():
                raise FileNotFoundError(f"missing backend directory: {backend}")
            # Every package uses a unique mcapp_<reverse-domain-id> module root.
            sys.path.insert(0, str(backend))
            try:
                module_name, function_name = manifest["backend"]["entry"].split(":")
                register = getattr(importlib.import_module(module_name), function_name)
                contribution = register(
                    AppContext(app_id=app_id, data_root=base / "data" / app_id)
                )
            except Exception:
                sys.path.remove(str(backend))
                raise
            if not isinstance(contribution, AppContribution):
                raise TypeError("register() must return AppContribution")
            if contribution.tools or contribution.jobs:
                raise ValueError("tools and jobs are not supported in the first app SDK release")
            app.include_router(contribution.router, prefix=f"/api/apps/{app_id}")
            set_app_status(app_id, "ready", base)
            results.append({"id": app_id, "status": "ready"})
        except Exception as exc:  # noqa: BLE001
            set_app_status(app_id, "load_failed", base, str(exc))
            results.append({"id": app_id, "status": "load_failed", "error": str(exc)})
    return results
