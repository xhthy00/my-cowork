"""Import enabled application routers into the existing FastAPI process."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.industry_apps.package import AppManifest, app_root, list_installed, set_app_status
from app.industry_apps.sdk import AppContext, AppContribution
from app.industry_apps.sdk import LoadedAppTool
from app.industry_apps.tooling import validate_app_tools


def load_enabled_apps(
    app: FastAPI, root: Path | None = None, *, tool_sink: list[LoadedAppTool] | None = None
) -> list[dict[str, Any]]:
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
        path_added = False
        try:
            if not backend.is_dir():
                raise FileNotFoundError(f"missing backend directory: {backend}")
            # Every package uses a unique mcapp_<reverse-domain-id> module root.
            sys.path.insert(0, str(backend))
            path_added = True
            try:
                module_name, function_name = manifest["backend"]["entry"].split(":")
                register = getattr(importlib.import_module(module_name), function_name)
                contribution = register(
                    AppContext(app_id=app_id, data_root=base / "data" / app_id)
                )
            except Exception:
                sys.path.remove(str(backend))
                path_added = False
                raise
            if not isinstance(contribution, AppContribution):
                raise TypeError("register() must return AppContribution")
            if contribution.jobs:
                raise ValueError("jobs are not supported in the first app SDK release")
            loaded_tools = validate_app_tools(AppManifest.model_validate(manifest), contribution)
            app.include_router(contribution.router, prefix=f"/api/apps/{app_id}")
            if tool_sink is not None:
                tool_sink.extend(loaded_tools)
            set_app_status(app_id, "ready", base)
            results.append({"id": app_id, "status": "ready"})
        except Exception as exc:  # noqa: BLE001
            if path_added and str(backend) in sys.path:
                sys.path.remove(str(backend))
            set_app_status(app_id, "load_failed", base, str(exc))
            results.append({"id": app_id, "status": "load_failed", "error": str(exc)})
    return results
