"""Context capacity from the same SDK model profile used by Deep Agents."""
from langchain_core.language_models import BaseChatModel
import hashlib
import json
from urllib.parse import urlsplit


# SDK profiles take precedence; fill only the MiniMax names they do not know.
# https://platform.minimax.io/docs/api-reference/text-openai-api
_MINIMAX_CONTEXT_WINDOWS = {
    'minimax-m3.1-flash-preview': 1_000_000,
    'minimax-m3': 1_000_000,
    'minimax-m2.7': 204_800,
    'minimax-m2.7-highspeed': 204_800,
    'minimax-m2.5': 204_800,
    'minimax-m2.5-highspeed': 204_800,
    'minimax-m2.1': 204_800,
    'minimax-m2.1-highspeed': 204_800,
    'minimax-m2': 204_800,
}


def selection_key(spec) -> str:
    value = {'provider': spec.get('provider', 'openai_compat'), 'model': spec.get('model', ''),
        'base_url': (spec.get('base_url') or '').rstrip('/')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def context_limit(model) -> int | None:
    profile = getattr(model, 'profile', None)
    value = profile.get('max_input_tokens') if isinstance(profile, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def with_context_metadata(model, *, model_name: str = '', base_url: str | None = None):
    if not isinstance(model, BaseChatModel):
        return model
    if context_limit(model) is None and urlsplit(base_url or '').hostname in {'api.minimax.io', 'api.minimaxi.com'}:
        limit = _MINIMAX_CONTEXT_WINDOWS.get(model_name.lower())
        if limit is not None:
            # Public profile is also read by Deep Agents' summarization middleware.
            model = model.model_copy(update={'profile': {**(model.profile or {}), 'max_input_tokens': limit}})
    return model.model_copy(update={'metadata': {
        **(model.metadata or {}), 'cowork_context_limit': context_limit(model),
    }})
