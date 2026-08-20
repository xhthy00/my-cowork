"""Semantic embeddings for long-term memory. Disable recall when unavailable."""

from __future__ import annotations

import os
from typing import Any, Callable

import httpx

EmbedFn = Callable[[str], list[float]]


class EmbedConfig:
    def __init__(self, fn: EmbedFn | None, dim: int, enabled: bool) -> None:
        self.fn = fn
        self.dim = dim
        self.enabled = enabled


def _settings() -> tuple[str, str, str]:
    model = (os.environ.get("MY_COWORK_EMBED_MODEL") or "").strip()
    base = (os.environ.get("MY_COWORK_EMBED_BASE_URL") or os.environ.get("MY_COWORK_BASE_URL") or "").strip()
    key = (os.environ.get("MY_COWORK_EMBED_API_KEY") or os.environ.get("MY_COWORK_API_KEY") or "").strip()
    return model, base, key


def _openai_embed(text: str, *, model: str, base_url: str, api_key: str) -> list[float]:
    url = base_url.rstrip("/")
    if not url.endswith("/embeddings"):
        url = url + "/embeddings" if url.endswith("/v1") else url.rstrip("/") + "/v1/embeddings"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=30.0) as client:
        res = client.post(url, headers=headers, json={"model": model, "input": text[:8000]})
        res.raise_for_status()
        data = res.json()
    vec = ((data.get("data") or [{}])[0]).get("embedding") or []
    return [float(x) for x in vec]


def _ollama_embed(text: str, *, model: str, host: str) -> list[float]:
    url = host.rstrip("/") + "/api/embeddings"
    with httpx.Client(timeout=30.0) as client:
        res = client.post(url, json={"model": model, "prompt": text[:8000]})
        res.raise_for_status()
        data = res.json()
    vec = data.get("embedding") or []
    return [float(x) for x in vec]


def make_embed_config() -> EmbedConfig:
    """Return a real embedding function or a disabled config (no hash fallback)."""
    model, base, key = _settings()
    if not model:
        return EmbedConfig(None, 0, False)

    def _fn(text: str) -> list[float]:
        if "11434" in base or base.rstrip("/").endswith("11434"):
            return _ollama_embed(text, model=model, host=base or "http://127.0.0.1:11434")
        if not base:
            # Ollama default when only a local model name like bge-m3 is set.
            if "/" not in model and ":" not in model.split("/")[-1][:3]:
                try:
                    return _ollama_embed(
                        text, model=model, host="http://127.0.0.1:11434"
                    )
                except Exception:
                    pass
            raise RuntimeError("no embed base_url")
        return _openai_embed(text, model=model, base_url=base, api_key=key)

    # Probe dimension lazily on first call — default 1024 for bge-m3 / many CN models.
    dim_raw = (os.environ.get("MY_COWORK_EMBED_DIM") or "").strip()
    dim = int(dim_raw) if dim_raw.isdigit() else 1024
    return EmbedConfig(_fn, dim, True)
