"""Validate and install MyCowork industry application ZIPs.

This installer does not execute package code. Installed Python is trusted code
and is imported only when the backend starts.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.workspace.paths import data_root

MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_FILES = 1000
MAX_RATIO = 1000
_ID = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_HASH_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
_lock = threading.RLock()


class AppPackageError(ValueError):
    """An application package is invalid or cannot be installed."""


class BackendSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry: str
    requires_python: str = ">=3.11,<3.13"


class UiSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry: str
    route_mode: Literal["hash"] = "hash"
    bridge_version: Literal[1] = 1
    min_width: int = Field(default=640, ge=320, le=1920)


class DataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["workspace", "global"] = "workspace"
    migration_entry: str | None = None


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host_api: list[str] = Field(default_factory=list)
    network_domains: list[str] = Field(default_factory=list)


class AppManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    id: str
    name: str = Field(min_length=1, max_length=80)
    version: str
    description: str = Field(default="", max_length=500)
    min_host_version: str = "0.0.0"
    sdk_version: Literal[1] = 1
    kind: Literal["python-web"]
    platforms: list[str] = Field(default_factory=list)
    backend: BackendSpec
    ui: UiSpec
    data: DataSpec = Field(default_factory=DataSpec)
    capabilities: Capabilities = Field(default_factory=Capabilities)
    skills: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("id must be a lowercase reverse-domain name")
        return value

    @field_validator("version", "min_host_version")
    @classmethod
    def valid_version(cls, value: str) -> str:
        if not _VERSION.fullmatch(value):
            raise ValueError("version must use MAJOR.MINOR.PATCH")
        return value

    @model_validator(mode="after")
    def valid_entries(self) -> "AppManifest":
        prefix = f"mcapp_{self.id.replace('.', '_')}"
        entry = self.backend.entry.split(":")
        if len(entry) != 2 or not entry[1].isidentifier():
            raise ValueError("backend.entry must be module:function")
        if entry[0] != prefix and not entry[0].startswith(prefix + "."):
            raise ValueError(f"backend.entry must use {prefix}")
        if self.ui.entry != "frontend/dist/index.html":
            raise ValueError("ui.entry must be frontend/dist/index.html in v1")
        if self.data.migration_entry:
            migration = self.data.migration_entry.split(":")
            if len(migration) != 2 or not migration[1].isidentifier():
                raise ValueError("data.migration_entry must be module:function")
            if migration[0] != prefix and not migration[0].startswith(prefix + "."):
                raise ValueError(f"data.migration_entry must use {prefix}")
        if self.backend.requires_python != ">=3.11,<3.13":
            raise ValueError("v1 supports Python >=3.11,<3.13")
        if not ((3, 11) <= sys.version_info[:2] < (3, 13)):
            raise ValueError("host Python is outside the v1 supported range")
        host_version = os.environ.get("MY_COWORK_APP_VERSION", "0.0.9")
        if _VERSION.fullmatch(host_version):
            if tuple(map(int, host_version.split("."))) < tuple(map(int, self.min_host_version.split("."))):
                raise ValueError(f"application requires MyCowork {self.min_host_version}")
        system = {"Darwin": "darwin", "Windows": "win"}.get(platform.system())
        machine = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "AMD64": "x64"}.get(platform.machine())
        if system and machine and self.platforms and f"{system}-{machine}" not in self.platforms:
            raise ValueError("application does not support this platform")
        if self.capabilities.network_domains:
            raise ValueError("v1 does not support network_domains")
        if self.capabilities.host_api:
            raise ValueError("host_api capabilities are not yet available")
        if self.data.migration_entry:
            raise ValueError("data migrations are not yet available")
        if self.skills:
            raise ValueError("bundled skills are not yet available")
        return self


@dataclass(frozen=True)
class Inspection:
    manifest: AppManifest
    sha256: str
    files: tuple[str, ...]
    expanded_bytes: int

    def public(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.model_dump(),
            "sha256": self.sha256,
            "file_count": len(self.files),
            "expanded_bytes": self.expanded_bytes,
            "trusted_code": True,
            "requires_restart": True,
        }


def app_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    configured = os.environ.get("MY_COWORK_INDUSTRY_APPS_ROOT")
    return Path(configured).expanduser().resolve() if configured else data_root() / "industry-apps"


def _safe_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    if "\\" in name or name.startswith("/") or "\x00" in name:
        raise AppPackageError(f"invalid ZIP path: {name!r}")
    path = PurePosixPath(name)
    if not name or any(part in {"", ".", ".."} for part in name.split("/")):
        # A final slash is permitted for directory entries.
        if not (info.is_dir() and all(part not in {"", ".", ".."} for part in name[:-1].split("/"))):
            raise AppPackageError(f"invalid ZIP path: {name!r}")
    if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
        raise AppPackageError(f"invalid ZIP path: {name!r}")
    mode = info.external_attr >> 16
    if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise AppPackageError(f"unsupported ZIP entry: {name!r}")
    return name.rstrip("/")


def _read_manifest(zf: zipfile.ZipFile) -> AppManifest:
    try:
        raw = zf.read("mycowork-app.yaml")
    except KeyError as exc:
        raise AppPackageError("mycowork-app.yaml must be at ZIP root") from exc
    if len(raw) > 64 * 1024:
        raise AppPackageError("manifest is too large")
    try:
        obj = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(obj, dict):
            raise ValueError("manifest must be an object")
        return AppManifest.model_validate(obj)
    except Exception as exc:
        raise AppPackageError(f"invalid manifest: {exc}") from exc


def inspect_zip(raw: bytes) -> Inspection:
    if not raw or len(raw) > MAX_ZIP_BYTES:
        raise AppPackageError("ZIP is empty or exceeds 50 MiB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise AppPackageError("invalid ZIP") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_FILES:
            raise AppPackageError("ZIP contains too many entries")
        seen: set[str] = set()
        files: list[str] = []
        expanded = 0
        for info in infos:
            name = _safe_name(info)
            key = name.casefold()
            if key in seen:
                raise AppPackageError(f"duplicate ZIP path: {name}")
            seen.add(key)
            if info.is_dir():
                continue
            if PurePosixPath(name).suffix.lower() in {".so", ".pyd", ".dll", ".dylib", ".pyc"}:
                raise AppPackageError(f"native or bytecode dependency is unsupported: {name}")
            if info.flag_bits & 1:
                raise AppPackageError("encrypted ZIP entries are unsupported")
            if info.file_size > MAX_FILE_BYTES:
                raise AppPackageError(f"file too large: {name}")
            if info.file_size and info.file_size / max(info.compress_size, 1) > MAX_RATIO:
                raise AppPackageError(f"suspicious compression ratio: {name}")
            expanded += info.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise AppPackageError("ZIP expands beyond 200 MiB")
            files.append(name)
        if "checksums.sha256" not in files:
            raise AppPackageError("checksums.sha256 is required")
        manifest = _read_manifest(zf)
        expected_package = f"backend/mcapp_{manifest.id.replace('.', '_')}/__init__.py"
        if expected_package not in files:
            raise AppPackageError(f"missing {expected_package}")
        expected_backend_root = expected_package.removesuffix("__init__.py")
        if any(name.startswith("backend/") and not name.startswith(expected_backend_root) for name in files):
            raise AppPackageError("backend files must stay within the app's unique Python package")
        if manifest.ui.entry not in files:
            raise AppPackageError(f"missing {manifest.ui.entry}")
        checksums: dict[str, str] = {}
        try:
            checksum_text = zf.read("checksums.sha256").decode("utf-8")
        except UnicodeError as exc:
            raise AppPackageError("checksums.sha256 must be UTF-8") from exc
        for line in checksum_text.splitlines():
            match = _HASH_LINE.fullmatch(line)
            if not match or match.group(2) in checksums:
                raise AppPackageError("invalid checksums.sha256")
            checksums[match.group(2)] = match.group(1)
        content_files = set(files) - {"checksums.sha256"}
        if set(checksums) != content_files:
            raise AppPackageError("checksums do not match ZIP files")
        for name in content_files:
            digest = hashlib.sha256(zf.read(name)).hexdigest()
            if digest != checksums[name]:
                raise AppPackageError(f"checksum mismatch: {name}")
        return Inspection(
            manifest=manifest,
            sha256=hashlib.sha256(raw).hexdigest(),
            files=tuple(sorted(files)),
            expanded_bytes=expanded,
        )


def _registry_path(root: Path) -> Path:
    return root / "registry.json"


def _load_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.is_file():
        return {"schema_version": 1, "apps": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("apps"), dict):
        raise AppPackageError("application registry is invalid")
    return data


def _save_registry(root: Path, registry: dict[str, Any]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = _registry_path(root)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as tmp:
        json.dump(registry, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def list_installed(root: Path | None = None) -> list[dict[str, Any]]:
    base = app_root(root)
    with _lock:
        registry = _load_registry(base)
        return [
            {"id": app_id, **entry}
            for app_id, entry in sorted(registry["apps"].items())
        ]


def install_zip(raw: bytes, expected_sha256: str, root: Path | None = None) -> dict[str, Any]:
    inspection = inspect_zip(raw)
    if inspection.sha256 != expected_sha256:
        raise AppPackageError("ZIP changed after inspection")
    manifest = inspection.manifest
    base = app_root(root)
    destination = base / "packages" / manifest.id / manifest.version
    with _lock:
        registry = _load_registry(base)
        if destination.exists():
            raise AppPackageError("this application version is already installed")
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=destination.parent))
        installed = False
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in inspection.files:
                    target = stage.joinpath(*PurePosixPath(name).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
            os.replace(stage, destination)
            installed = True
            old = registry["apps"].get(manifest.id, {})
            registry["apps"][manifest.id] = {
                "manifest": manifest.model_dump(),
                "version": manifest.version,
                "previous_version": old.get("version"),
                "enabled": True,
                "status": "pending_restart",
                "sha256": inspection.sha256,
            }
            _save_registry(base, registry)
        except Exception:
            if stage.exists():
                shutil.rmtree(stage)
            if installed and destination.exists():
                shutil.rmtree(destination)
            raise
    return {"id": manifest.id, "version": manifest.version, "requires_restart": True}


def set_app_status(app_id: str, status: str, root: Path | None = None, error: str | None = None) -> None:
    base = app_root(root)
    with _lock:
        registry = _load_registry(base)
        entry = registry["apps"].get(app_id)
        if entry is None:
            return
        entry["status"] = status
        if error:
            entry["error"] = error[:2000]
        else:
            entry.pop("error", None)
        _save_registry(base, registry)


def disable_app(app_id: str, root: Path | None = None) -> dict[str, Any]:
    base = app_root(root)
    with _lock:
        registry = _load_registry(base)
        entry = registry["apps"].get(app_id)
        if entry is None:
            raise AppPackageError("application not found")
        entry["enabled"] = False
        entry["status"] = "pending_restart"
        _save_registry(base, registry)
    return {"id": app_id, "requires_restart": True}


def enable_app(app_id: str, root: Path | None = None) -> dict[str, Any]:
    base = app_root(root)
    with _lock:
        registry = _load_registry(base)
        entry = registry["apps"].get(app_id)
        if entry is None:
            raise AppPackageError("application not found")
        entry["enabled"] = True
        entry["status"] = "pending_restart"
        _save_registry(base, registry)
    return {"id": app_id, "requires_restart": True}


def rollback_app(app_id: str, root: Path | None = None) -> dict[str, Any]:
    base = app_root(root)
    with _lock:
        registry = _load_registry(base)
        entry = registry["apps"].get(app_id)
        if entry is None:
            raise AppPackageError("application not found")
        previous = entry.get("previous_version")
        if not previous:
            raise AppPackageError("no previous version is available")
        manifest_path = base / "packages" / app_id / previous / "mycowork-app.yaml"
        try:
            manifest = AppManifest.model_validate(yaml.safe_load(manifest_path.read_text(encoding="utf-8")))
        except Exception as exc:
            raise AppPackageError(f"previous version is invalid: {exc}") from exc
        if manifest.id != app_id or manifest.version != previous:
            raise AppPackageError("previous version does not match registry")
        entry.update(
            manifest=manifest.model_dump(),
            version=previous,
            previous_version=None,
            enabled=True,
            status="pending_restart",
        )
        entry.pop("error", None)
        _save_registry(base, registry)
    return {"id": app_id, "version": previous, "requires_restart": True}
