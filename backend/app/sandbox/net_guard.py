"""Outbound domain whitelist for network tools."""

from urllib.parse import urlparse


class NetForbidden(Exception):
    """Raised when a URL's domain is not in the allowed list."""


class NetGuard:
    """Domain whitelist guard. Each instance holds its own allowed_domains set."""

    def __init__(self, domains: list[str] | None = None) -> None:
        self._allowed_domains: set[str] = {d.lower() for d in (domains or [])}

    def check_domain(self, url: str) -> None:
        """Raise NetForbidden if urlparse(url).netloc is not in the whitelist.

        Matching is exact and case-insensitive on the netloc. Subdomains are
        not implied: ``api.openai.com`` does not allow ``evil.api.openai.com``.
        """
        netloc = urlparse(url).netloc.lower()
        if netloc not in self._allowed_domains:
            raise NetForbidden(f"Domain {netloc!r} is not in the allowed list")
