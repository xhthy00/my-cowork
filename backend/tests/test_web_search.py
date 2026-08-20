"""Built-in web search / fetch."""

import pytest

from app.tools.builtin.web_fetch import html_to_text
from app.tools.builtin.web_search import (
    configured_providers,
    json_dumps,
    parse_bocha_payload,
    web_search,
)


def test_ddgs_always_in_provider_chain():
    names = configured_providers()
    assert names[-1] == "ddgs"
    assert "ddgs" in names


def test_preferred_provider_prepended(monkeypatch):
    monkeypatch.setenv("MY_COWORK_SEARCH_PROVIDER", "searxng")
    monkeypatch.setenv("SEARXNG_URL", "http://127.0.0.1:8888")
    names = configured_providers()
    assert names[0] == "searxng"
    assert names[-1] == "ddgs"


def test_preferred_bocha_stays_first_when_keyed(monkeypatch):
    monkeypatch.setenv("MY_COWORK_SEARCH_PROVIDER", "bocha")
    monkeypatch.setenv("BOCHA_API_KEY", "test-key")
    names = configured_providers()
    assert names[0] == "bocha"
    assert names[-1] == "ddgs"


def test_html_to_text_strips_script():
    html = "<html><script>alert(1)</script><p>Hello <b>world</b></p></html>"
    text = html_to_text(html)
    assert "Hello" in text
    assert "alert" not in text


@pytest.mark.asyncio
async def test_web_search_empty_query():
    assert "empty" in await web_search("")


def test_json_dumps_shape():
    blob = json_dumps(
        [{"title": "t", "url": "https://example.com", "snippet": "s", "published": ""}]
    )
    assert "https://example.com" in blob


def test_parse_bocha_nested_data():
    rows = parse_bocha_payload(
        {
            "code": 200,
            "data": {
                "webPages": {
                    "value": [
                        {
                            "name": "扬州购房政策",
                            "url": "https://yangzhou.gov.cn/policy",
                            "snippet": "限购调整",
                        }
                    ]
                }
            },
        }
    )
    assert rows[0]["url"] == "https://yangzhou.gov.cn/policy"
    assert rows[0]["title"] == "扬州购房政策"


def test_parse_bocha_top_level_webpages():
    rows = parse_bocha_payload(
        {
            "_type": "SearchResponse",
            "webPages": {
                "value": [
                    {"name": "t", "url": "https://example.com", "summary": "s"}
                ]
            },
        }
    )
    assert rows[0]["url"] == "https://example.com"
    assert rows[0]["snippet"] == "s"


def test_parse_bocha_error_code():
    try:
        parse_bocha_payload({"code": 401, "msg": "invalid api key"})
    except RuntimeError as exc:
        assert "401" in str(exc)
        assert "invalid api key" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
