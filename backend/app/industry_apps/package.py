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
    health_entry: str | None = None


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
    version: int | None = Field(default=None, ge=1, strict=True)
    upgrade_from: list[int | Literal["legacy"]] = Field(default_factory=list)


class Capabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host_api: list[str] = Field(default_factory=list)
    network_domains: list[str] = Field(default_factory=list)


class AgentToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$", max_length=64)
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    access: Literal["read", "write"] = "read"


class AppManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1, 2]
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
    agent_tools: list[AgentToolSpec] = Field(default_factory=list, max_length=32)
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
        names = [tool.name for tool in self.agent_tools]
        if len(names) != len(set(names)):
            raise ValueError("agent_tools names must be unique")
        prefix = f"mcapp_{self.id.replace('.', '_')}"
        entry = self.backend.entry.split(":")
        if len(entry) != 2 or not entry[1].isidentifier():
            raise ValueError("backend.entry must be module:function")
        if entry[0] != prefix and not entry[0].startswith(prefix + "."):
            raise ValueError(f"backend.entry must use {prefix}")
        if self.ui.entry != "frontend/dist/index.html":
            raise ValueError("ui.entry must be frontend/dist/index.html in v1")
        if self.backend.health_entry:
            health = self.backend.health_entry.split(":")
            if len(health) != 2 or not health[1].isidentifier() or not all(p.isidentifier() for p in health[0].split(".")):
                raise ValueError("backend.health_entry must be module:function")
            if health[0] != prefix and not health[0].startswith(prefix + "."):
                raise ValueError(f"backend.health_entry must use {prefix}")
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
        host_version = os.environ.get("MY_COWORK_APP_VERSION", "0.1.1")
        if _VERSION.fullmatch(host_version):
            if tuple(map(int, host_version.split("."))) < tuple(map(int, self.min_host_version.split("."))):
                raise ValueError(f"application requires MyCowork {self.min_host_version}")
        system = {"Darwin": "darwin", "Windows": "win"}.get(platform.system())
        machine = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "AMD64": "x64"}.get(platform.machine())
        if system and machine and self.platforms and f"{system}-{machine}" not in self.platforms:
            raise ValueError("application does not support this platform")
        if self.capabilities.network_domains:
            raise ValueError("v1 does not support network_domains")
        if set(self.capabilities.host_api) - {'ai', 'files', 'navigation', 'ui'}:
            raise ValueError("unsupported host_api capability")
        if self.schema_version == 1 and (self.data.migration_entry or self.data.version is not None or self.data.upgrade_from or self.backend.health_entry):
            raise ValueError("data migrations and health checks require schema_version 2")
        if self.schema_version == 2 and (self.data.version is None or not self.backend.health_entry):
            raise ValueError("v2 requires data.version and backend.health_entry")
        if any(isinstance(v, int) and (isinstance(v, bool) or v < 1) for v in self.data.upgrade_from):
            raise ValueError("upgrade_from requires positive versions or legacy")
        from app.skills.bundled import validate_skill_paths
        validate_skill_paths(self.skills)
        return self


@dataclass(frozen=True)
class Inspection:
    manifest: AppManifest
    sha256: str
    files: tuple[str, ...]
    expanded_bytes: int
    skill_names: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.model_dump(),
            "sha256": self.sha256,
            "file_count": len(self.files),
            "expanded_bytes": self.expanded_bytes,
            "skill_names": list(self.skill_names),
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
    if path.is_absolute() or ".." in path.parts or any(":" in part or part.endswith((".", " ")) for part in path.parts):
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
        from app.skills.bundled import parse_package_skill, MAX_SKILL_BYTES
        skill_names = []
        for directory in manifest.skills:
            entries = [f'{directory}/{name}' for name in ('SKILL.md', 'skill.yaml') if f'{directory}/{name}' in files]
            if len(entries) != 1:
                raise AppPackageError(f'skill {directory} requires exactly one entry')
            try:
                if zf.getinfo(entries[0]).file_size > MAX_SKILL_BYTES:
                    raise ValueError('skill entry exceeds 64 KiB')
                skill_names.append(parse_package_skill(zf.read(entries[0]), entries[0], manifest.model_dump()).name)
            except (ValueError, yaml.YAMLError) as exc:
                raise AppPackageError(f'invalid skill {directory}: {exc}') from exc
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
            skill_names=tuple(skill_names),
        )


def _load_registry(root: Path) -> dict[str, Any]:
    from .registry import read
    return read(root)


def _save_registry(root: Path, registry: dict[str, Any]) -> None:
    from .registry import write
    write(root, "registry", registry)


def list_installed(root: Path | None = None) -> list[dict[str, Any]]:
    registry = _load_registry(app_root(root))
    return [{"id": app_id, **{key: value for key, value in entry.items() if key != "recovery_operation"},
             "needs_recovery": bool(entry.get("recovery_operation"))}
            for app_id, entry in sorted(registry["apps"].items())]


def check_upgrade(manifest: AppManifest, old: dict) -> None:
    previous = old.get("version")
    if previous and tuple(map(int, manifest.version.split("."))) < tuple(map(int, previous.split("."))):
        raise AppPackageError("较低版本不能作为普通更新，请使用恢复上次更新")
    source = old.get("data_version", "legacy")
    target = manifest.data.version if manifest.schema_version == 2 else "legacy"
    if source != target:
        if source not in manifest.data.upgrade_from or not manifest.data.migration_entry:
            raise AppPackageError("新版未声明如何迁移当前数据，请联系插件作者")


def inspect_update(raw: bytes, root: Path | None = None) -> dict:
    result = inspect_zip(raw)
    old = _load_registry(app_root(root))["apps"].get(result.manifest.id, {})
    if old.get("version") or (app_root(root) / "data" / result.manifest.id).exists():
        check_upgrade(result.manifest, old)
    return {**result.public(), "current_version": old.get("version"),
            "previous_tools": old.get("manifest", {}).get("agent_tools", [])}


def install_zip(raw: bytes, expected_sha256: str, root: Path | None = None) -> dict[str, Any]:
    from .locks import FileLock
    # Validate before creating even the registry or lock directory.
    inspection = inspect_zip(raw)
    if inspection.sha256 != expected_sha256:
        raise AppPackageError("ZIP changed after inspection")
    base = app_root(root)
    with FileLock(base, "operation"):
        return stage_zip(raw, expected_sha256, base)


def stage_zip(raw: bytes, expected_sha256: str, base: Path) -> dict[str, Any]:
    from .snapshots import managed
    inspection = inspect_zip(raw)
    if inspection.sha256 != expected_sha256:
        raise AppPackageError("ZIP changed after inspection")
    manifest = inspection.manifest
    registry = _load_registry(base)
    old = registry["apps"].get(manifest.id, {})
    if old.get('dev_revision'):
        raise AppPackageError('同版本开发源码不能切换为正式包，请使用 package-test 独立环境')
    if old.get("recovery_operation"):
        raise AppPackageError("请先恢复未完成的数据操作，再更新此应用")
    if old.get("version") or managed(base, "data", manifest.id).exists():
        check_upgrade(manifest, old)
    destination = managed(base, "packages", manifest.id, manifest.version)
    if destination.exists():
        checksum = destination / ".package-sha256"
        if not checksum.exists() or checksum.read_text() != inspection.sha256:
            raise AppPackageError("同版本的包内容不同，不能覆盖；请使用新的版本号")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=destination.parent))
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for name in inspection.files:
                    target = stage.joinpath(*PurePosixPath(name).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
                        sink.flush()
                        os.fsync(sink.fileno())
            (stage / ".package-sha256").write_text(inspection.sha256)
            os.replace(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    if old.get("version") == manifest.version and old.get("sha256") == inspection.sha256:
        return {"id": manifest.id, "version": manifest.version, "requires_restart": False}
    candidate = {"manifest": manifest.model_dump(), "version": manifest.version, "sha256": inspection.sha256}
    entry = dict(old) if old else {"manifest": manifest.model_dump(), "version": None, "enabled": False, "status": "pending_activation", "data_version": "legacy"}
    entry["candidate"] = candidate
    registry["apps"][manifest.id] = entry
    _save_registry(base, registry)
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
    raise AppPackageError("请使用桌面应用管理菜单，安全停止后端后应用变更")


enable_app = disable_app
rollback_app = disable_app
