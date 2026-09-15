"""Bounded F1000Research HTML evidence for a reviewed public source.

The verifier deliberately accepts an article identifier, never an arbitrary URL.
It retains neither publisher HTML nor a full-text copy: callers get a short
in-memory excerpt for human review and may persist only the receipt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ARTICLE_ID = re.compile(r"^\d{1,3}-\d{1,6}$")
_MAX_HTML_BYTES = 2_000_000
_MAX_EXCERPT_CHARACTERS = 2_000
_COMPATIBLE_LICENSE = "CC-BY-4.0"
_LICENSE_URL = re.compile(
    rb"https?://creativecommons\.org/licenses/by/4\.0/?", re.IGNORECASE
)


class PublisherEvidenceError(RuntimeError):
    """A publisher page cannot be used as bounded evidence."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise PublisherEvidenceError("publisher page redirect was rejected")


@dataclass(frozen=True)
class F1000ArticleRequest:
    source_key: str
    article_id: str
    version: int = 1

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise PublisherEvidenceError("source key is malformed")
        if not _ARTICLE_ID.fullmatch(self.article_id):
            raise PublisherEvidenceError("article identifier is malformed")
        if not 1 <= self.version <= 99:
            raise PublisherEvidenceError("article version is outside the bounded range")

    @property
    def url(self) -> str:
        return f"https://f1000research.com/articles/{self.article_id}/v{self.version}"


@dataclass(frozen=True)
class HtmlResponse:
    content_type: str
    payload: bytes


@dataclass(frozen=True)
class PublisherHtmlReceipt:
    source_key: str
    provider: str
    document_url: str
    license_id: str
    html_sha256: str
    visible_text_sha256: str
    visible_character_count: int
    checked_on: str
    verification_status: str = "publisher_html_verified"


@dataclass(frozen=True)
class PublisherEvidence:
    receipt: PublisherHtmlReceipt
    excerpt: str


class _VisibleText(HTMLParser):
    _IGNORED = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        if tag.casefold() in self._IGNORED:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


def default_f1000_transport(url: str) -> HtmlResponse:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "f1000research.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not re.fullmatch(r"/articles/\d{1,3}-\d{1,6}/v\d{1,2}", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise PublisherEvidenceError("publisher target is outside the allowlist")
    request = Request(url, headers={"User-Agent": "neurolab-publisher-evidence/0.1"}, method="GET")
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=20) as response:
            if response.geturl() != url:
                raise PublisherEvidenceError("publisher page location changed")
            payload = response.read(_MAX_HTML_BYTES + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as error:
        raise PublisherEvidenceError("publisher page request failed") from error
    return HtmlResponse(content_type=content_type, payload=payload)


def verify_f1000_article(
    request: F1000ArticleRequest,
    *,
    transport: Callable[[str], HtmlResponse] = default_f1000_transport,
    checked_on: str,
) -> PublisherEvidence:
    """Verify one fixed CC-BY publisher HTML page without retaining its body."""
    response = transport(request.url)
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        raise PublisherEvidenceError("publisher response is not HTML")
    if len(response.payload) > _MAX_HTML_BYTES:
        raise PublisherEvidenceError("publisher response exceeds the size limit")
    if not _LICENSE_URL.search(response.payload):
        raise PublisherEvidenceError("no explicit compatible open licence was found")
    try:
        parser = _VisibleText()
        parser.feed(response.payload.decode("utf-8", errors="strict"))
        parser.close()
    except UnicodeDecodeError as error:
        raise PublisherEvidenceError("publisher response is not UTF-8 HTML") from error
    visible_text = parser.text()
    if not visible_text:
        raise PublisherEvidenceError("publisher page has no visible text")
    receipt = PublisherHtmlReceipt(
        source_key=request.source_key,
        provider="f1000research",
        document_url=request.url,
        license_id=_COMPATIBLE_LICENSE,
        html_sha256=sha256(response.payload).hexdigest(),
        visible_text_sha256=sha256(visible_text.encode("utf-8")).hexdigest(),
        visible_character_count=len(visible_text),
        checked_on=checked_on,
    )
    return PublisherEvidence(receipt=receipt, excerpt=visible_text[:_MAX_EXCERPT_CHARACTERS])
