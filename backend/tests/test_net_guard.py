import pytest

from app.sandbox.net_guard import NetForbidden, NetGuard


class TestNetGuard:
    def test_allowed_domain_passes(self) -> None:
        guard = NetGuard(["api.openai.com"])
        guard.check_domain("https://api.openai.com/v1/chat/completions")

    def test_disallowed_domain_raises(self) -> None:
        guard = NetGuard(["api.openai.com"])
        with pytest.raises(NetForbidden):
            guard.check_domain("https://evil.example.com/steal")

    def test_empty_whitelist_rejects_all(self) -> None:
        guard = NetGuard([])
        with pytest.raises(NetForbidden):
            guard.check_domain("https://api.openai.com/")

    def test_domain_match_is_case_insensitive(self) -> None:
        guard = NetGuard(["api.openai.com"])
        guard.check_domain("https://API.OpenAI.com/v1")

    def test_subdomain_is_not_implicitly_allowed(self) -> None:
        guard = NetGuard(["api.openai.com"])
        with pytest.raises(NetForbidden):
            guard.check_domain("https://evil.api.openai.com/")
