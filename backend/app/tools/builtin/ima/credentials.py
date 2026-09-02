"""Load IMA OpenAPI credentials: env → config.toml → ~/.config/ima/."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://ima.qq.com"
MISSING_CREDENTIALS_MSG = (
    "未配置 IMA 凭证。请打开 Hub「知识库」页签填写 Client ID 和 API Key，"
    "或前往 https://ima.qq.com/agent-interface 申请。"
)


@dataclass(frozen=True)
class ImaCredentials:
    client_id: str
    api_key: str
    base_url: str = DEFAULT_BASE_URL

    def is_valid(self) -> bool:
        return bool(self.client_id.strip() and self.api_key.strip())


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _toml_ima() -> dict[str, Any]:
    import tomllib

    candidates = [
        Path(os.environ.get("MY_COWORK_CONFIG") or ""),
        Path.home() / ".my-cowork" / "config.toml",
        Path(__file__).resolve().parents[5] / "config.toml",
    ]
    for path in candidates:
        if not path or not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ima = ((data.get("tools") or {}).get("ima") or {})
        if isinstance(ima, dict):
            return ima
    return {}


def _env(*names: str) -> str:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def load_credentials() -> ImaCredentials | None:
    """Resolve credentials. Env (keychain-injected) wins, then toml, then files."""
    toml = _toml_ima()
    client_id = (
        _env("IMA_OPENAPI_CLIENTID", "IMA_CLIENT_ID")
        or str(toml.get("client_id") or "").strip()
        or _read_file(Path.home() / ".config" / "ima" / "client_id")
    )
    api_key = (
        _env("IMA_OPENAPI_APIKEY", "IMA_API_KEY")
        or str(toml.get("api_key") or "").strip()
        or _read_file(Path.home() / ".config" / "ima" / "api_key")
    )
    base_url = (
        _env("IMA_BASE_URL")
        or str(toml.get("base_url") or "").strip()
        or DEFAULT_BASE_URL
    ).rstrip("/")
    if not client_id or not api_key:
        return None
    return ImaCredentials(client_id=client_id, api_key=api_key, base_url=base_url)


def configured() -> bool:
    creds = load_credentials()
    return creds is not None and creds.is_valid()
