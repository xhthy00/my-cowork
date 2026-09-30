"""Import enabled application routers into the existing FastAPI process."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.industry_apps.package import AppManifest, app_root
from app.industry_apps.sdk import AppContext, AppContribution
from app.industry_apps.sdk import LoadedAppTool
from app.industry_apps.tooling import validate_app_tools
from app.industry_apps.lifecycle import runtime_entries
from app.industry_apps.snapshots import managed
from app.skills.bundled import load_package_skills
from app.industry_apps.development import package_path


def load_enabled_apps(
    app: FastAPI, root: Path | None = None, *, tool_sink: list[LoadedAppTool] | None = None
) -> list[dict[str, Any]]:
    base = app_root(root)
    results: list[dict[str, Any]] = []
    app.state.app_manifests = {}
    app.state.app_skills = {}
    app.state.app_development = {}
    for entry in runtime_entries(base, os.environ.get("MY_COWORK_OPERATION_TOKEN", "")):
        if not entry.get("version") or entry.get('removed'):
            continue
        app_id = entry["id"]
        manifest = entry["manifest"]
        version = entry["version"]
        path_added = False
        package_skills = {}
        try:
            package = package_path(base, app_id, entry)
            backend = package / 'backend'
            parsed = AppManifest.model_validate(manifest)
            if parsed.id != app_id or parsed.version != version:
                raise ValueError("package identity mismatch")
            package_skills = load_package_skills(manifest, package, available=False)
            app.state.app_skills.update(package_skills)
            if not entry.get('enabled'):
                continue
            if not managed(package, "frontend", "dist", "index.html").is_file():
                raise ValueError(f"application entry page is missing: {package / 'frontend/dist/index.html'}")
            if not backend.is_dir():
                raise FileNotFoundError(f"missing backend directory: {backend}")
            # Every package uses a unique mcapp_<reverse-domain-id> module root.
            sys.path.insert(0, str(backend))
            sys.dont_write_bytecode = True
            path_added = True
            try:
                module_name, function_name = manifest["backend"]["entry"].split(":")
                register = getattr(importlib.import_module(module_name), function_name)
                contribution = register(
                    AppContext(app_id=app_id, data_root=managed(base, "data", app_id))
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
            if parsed.backend.health_entry:
                module, name = parsed.backend.health_entry.split(":")
                check = getattr(importlib.import_module(module), name)
                checked = check(AppContext(app_id=app_id, data_root=managed(base, "data", app_id)))
                import inspect
                if inspect.isawaitable(checked):
                    raise ValueError("health_entry must be synchronous")
            app.include_router(contribution.router, prefix=f"/api/apps/{app_id}")
            if tool_sink is not None:
                tool_sink.extend(loaded_tools)
            results.append({"id": app_id, "version": version, "enabled": True, "status": "ready", **({'dev_revision': entry['dev_revision']} if entry.get('dev_revision') else {})})
            if entry.get('dev_revision'):
                app.state.app_development[app_id] = entry['dev_revision']
            app.state.app_manifests[app_id] = parsed.model_dump(mode='json')
            for skill in package_skills.values():
                skill.available = True
        except Exception as exc:  # noqa: BLE001
            if path_added and str(backend) in sys.path:
                sys.path.remove(str(backend))
            results.append({"id": app_id, "status": "load_failed", "error": str(exc)})
    return results
