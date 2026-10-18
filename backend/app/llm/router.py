"""Model selection for task kinds."""

PRIMARY = {
    "supervisor": "claude-sonnet-5-5",
    "developer_agent": "claude-sonnet-5-5",
    "browser_agent": "claude-sonnet-5-5",
    "document_agent": "claude-sonnet-5-5",
    "multi_modal_agent": "claude-sonnet-5-5",
    # legacy aliases
    "file_worker": "claude-sonnet-5-5",
    "doc_worker": "claude-sonnet-5-5",
    "web_worker": "claude-sonnet-5-5",
    "msg_worker": "claude-sonnet-5-5",
}

COMPRESS = {
    "compress": "gpt-4o-mini",
}

_MODEL_MAP = {
    **PRIMARY,
    **COMPRESS,
}

_PROVIDER_MAP = {
    "claude-sonnet-5-5": "anthropic",
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
