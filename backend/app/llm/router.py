"""Model selection for task kinds."""

PRIMARY = {
    "supervisor": "claude-sonnet-4-20250514",
    "developer_agent": "claude-sonnet-4-20250514",
    "browser_agent": "claude-sonnet-4-20250514",
    "document_agent": "claude-sonnet-4-20250514",
    "multi_modal_agent": "claude-sonnet-4-20250514",
    # legacy aliases
    "file_worker": "claude-sonnet-4-20250514",
    "doc_worker": "claude-sonnet-4-20250514",
    "web_worker": "claude-sonnet-4-20250514",
    "msg_worker": "claude-sonnet-4-20250514",
}

COMPRESS = {
    "compress": "gpt-4o-mini",
}

_MODEL_MAP = {
    **PRIMARY,
    **COMPRESS,
}

_PROVIDER_MAP = {
    "claude-sonnet-4-20250514": "anthropic",
    "gpt-4o-mini": "openai_compat",
}


def model_picker(task_kind: str) -> tuple[str, str]:
    """Return (provider, model_name) for the given task kind."""
    model = _MODEL_MAP.get(task_kind)
    if model is None:
        raise ValueError(f"Unknown task_kind: {task_kind!r}. Available: {list(_MODEL_MAP)}")
    provider = _PROVIDER_MAP.get(model)
    if provider is None:
        raise ValueError(f"Unknown model: {model!r}")
    return provider, model
