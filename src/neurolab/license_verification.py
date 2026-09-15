"""Verify an explicit compatible licence on one fixed arXiv abstract page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_MAX_HTML_BYTES = 1_000_000
_LICENSE_PATTERNS: tuple[tuple[re.Pattern[bytes], str], ...] = (
    (re.compile(rb"https?://creativecommons\.org/licenses/by/4\.0/?", re.IGNORECASE), "CC-BY-4.0"),
    (re.compile(rb"https?://creativecommons\.org/publicdomain/zero/1\.0/?", re.IGNORECASE), "CC0-1.0"),
)


class LicenseVerificationError(RuntimeError):
    """The fixed-page licence proof is missing, incompatible or malformed."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise LicenseVerificationError("licence page redirect was rejected")


@dataclass(frozen=True)
class ArxivLicenseRequest:
    source_key: str
    arxiv_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise LicenseVerificationError("source key is malformed")
        if not _ARXIV_ID.fullmatch(self.arxiv_id):
            raise LicenseVerificationError("only modern arXiv identifiers are allowed")

    @property
    def url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"


@dataclass(frozen=True)
class HtmlResponse:
    content_type: str
    payload: bytes


@dataclass(frozen=True)
class LicenseReceipt:
    source_key: str
    provider: str
    metadata_url: str
    license_id: str
    evidence_sha256: str
    checked_on: str


def default_html_transport(url: str) -> HtmlResponse:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "arxiv.org" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise LicenseVerificationError("licence target is outside the allowlist")
    request = Request(url, headers={"User-Agent": "neurolab-license-verification/0.1"}, method="GET")
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=20) as response:
            if response.geturl() != url:
                raise LicenseVerificationError("licence page location changed")
            payload = response.read(_MAX_HTML_BYTES + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as error:
        raise LicenseVerificationError("licence page request failed") from error
    return HtmlResponse(content_type=content_type, payload=payload)


def verify_arxiv_license(
    request: ArxivLicenseRequest,
    *,
    transport: Callable[[str], HtmlResponse] = default_html_transport,
    checked_on: str,
) -> LicenseReceipt:
    """Return an explicit CC BY/CC0 proof without retaining the abstract-page HTML."""
    response = transport(request.url)
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        raise LicenseVerificationError("licence response is not HTML")
    if len(response.payload) > _MAX_HTML_BYTES:
        raise LicenseVerificationError("licence response exceeds the size limit")
    for pattern, license_id in _LICENSE_PATTERNS:
        match = pattern.search(response.payload)
        if match:
            return LicenseReceipt(
                source_key=request.source_key,
                provider="arxiv",
                metadata_url=request.url,
                license_id=license_id,
                evidence_sha256=sha256(match.group(0).lower()).hexdigest(),
                checked_on=checked_on,
            )
    raise LicenseVerificationError("no compatible explicit open licence was found")
