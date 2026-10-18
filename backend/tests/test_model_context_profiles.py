"""Native MiniMax window fallback shared by UI metadata and official compaction."""
import pytest
from deepagents.middleware.summarization import compute_summarization_defaults

from model_integrations.anthropic import create_anthropic
from model_integrations.context import context_limit, with_context_metadata
from model_integrations.openai_compat import create_openai_compat


@pytest.mark.parametrize('factory,url', [
    (create_openai_compat, 'https://api.minimaxi.com/v1'),
    (create_openai_compat, 'https://api.minimax.io/v1'),
    (create_anthropic, 'https://api.minimax.io/anthropic'),
])
@pytest.mark.parametrize('name,expected', [
    ('MiniMax-M3', 1_000_000),
    ('MiniMax-M3.1-Flash-Preview', 1_000_000),
    ('MiniMax-M2.7', 204_800),
    ('MiniMax-M2.7-highspeed', 204_800),
    ('MiniMax-M2.5', 204_800),
    ('MiniMax-M2.5-highspeed', 204_800),
    ('MiniMax-M2.1', 204_800),
    ('MiniMax-M2.1-highspeed', 204_800),
    ('MiniMax-M2', 204_800),
])
def test_minimax_profile_drives_metadata_and_official_compaction(factory, url, name, expected):
    model = factory(name, 'metadata-only', base_url=url)
    assert context_limit(model) == expected
    assert model.metadata['cowork_context_limit'] == expected
    defaults = compute_summarization_defaults(model)
    assert defaults['trigger'] == ('fraction', 0.85)
    assert defaults['keep'] == ('fraction', 0.10)


def test_sdk_profile_takes_precedence_and_other_capabilities_survive():
    model = create_openai_compat('MiniMax-M3', 'metadata-only', base_url='https://api.minimaxi.com/v1')
    # An upstream SDK update can correct capacity without updating this fallback.
    updated = model.model_copy(update={'profile': {'max_input_tokens': 1_500_000, 'tool_calling': True}})
    resolved = with_context_metadata(updated, model_name='MiniMax-M3', base_url='https://api.minimaxi.com/v1')
    assert context_limit(resolved) == 1_500_000
    assert resolved.metadata['cowork_context_limit'] == 1_500_000
    assert resolved.profile['tool_calling'] is True


@pytest.mark.parametrize('url', ['http://localhost:11434/v1', 'https://api.minimax.io.example.test/v1'])
def test_minimax_model_name_does_not_infer_custom_endpoint_capacity(url):
    model = create_openai_compat('MiniMax-M3', 'metadata-only', base_url=url)
    assert context_limit(model) is None
    assert model.metadata['cowork_context_limit'] is None


def test_fallback_keeps_other_sdk_profile_fields():
    model = create_openai_compat('MiniMax-M3', 'metadata-only', base_url='http://localhost:11434/v1')
    model = model.model_copy(update={'profile': {'tool_calling': True}, 'metadata': {'existing': 'kept'}})
    resolved = with_context_metadata(model, model_name='MiniMax-M3', base_url='https://api.minimax.io/v1')
    assert resolved.profile == {'tool_calling': True, 'max_input_tokens': 1_000_000}
    assert resolved.metadata == {'existing': 'kept', 'cowork_context_limit': 1_000_000}
