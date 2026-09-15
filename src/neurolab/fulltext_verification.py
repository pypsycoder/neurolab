"""Bounded, open-license PDF retrieval for claim verification.

PDF bytes and extracted text are untrusted evidence.  This module never sends
them to a model, executes them, follows links inside them, or assigns maturity
scores from their content.  It returns a receipt so a separate reviewer may
create structured claims with explicit evidence locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")
_ALLOWED_HOSTS = frozenset({"arxiv.org", "export.arxiv.org"})
_ALLOWED_LICENSES = frozenset({"CC-BY-4.0", "CC0-1.0", "PUBLIC-DOMAIN"})
_MAX_PDF_BYTES = 25 * 1024 * 1024
_MAX_PDF_PAGES = 100
_MAX_EXTRACTED_CHARS = 1_000_000


class FullTextVerificationError(RuntimeError):
    """The document cannot enter the bounded verification path."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise FullTextVerificationError("PDF redirect was rejected")


@dataclass(frozen=True)
class OpenAccessPdfRequest:
    """A pre-verified document identity; arbitrary URLs are intentionally absent."""

    source_key: str
    arxiv_id: str
    license_id: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise FullTextVerificationError("source key is malformed")
        if not _ARXIV_ID.fullmatch(self.arxiv_id):
            raise FullTextVerificationError("only modern arXiv identifiers are allowed")
        if self.license_id.upper() not in _ALLOWED_LICENSES:
            raise FullTextVerificationError("an explicit compatible open licence is required")

    @property
    def url(self) -> str:
        return f"https://export.arxiv.org/pdf/{self.arxiv_id}"


@dataclass(frozen=True)
class PdfResponse:
    content_type: str
    payload: bytes


@dataclass(frozen=True)
class FullTextReceipt:
    source_key: str
    provider: str
    document_url: str
    license_id: str
    sha256: str
    byte_count: int
    page_count: int
    extracted_text_sha256: str
    extracted_character_count: int
    extraction_status: str = "extracted_untrusted"


def _validate_pdf_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS or parsed.username or parsed.password:
        raise FullTextVerificationError("PDF target is outside the allowlist")
    if parsed.port not in (None, 443):
        raise FullTextVerificationError("PDF target port is malformed")


def default_pdf_transport(url: str) -> PdfResponse:
    """Fetch one PDF with TLS checks, a byte cap and no redirects."""
    _validate_pdf_url(url)
    request = Request(url, headers={"User-Agent": "neurolab-fulltext-verification/0.1"}, method="GET")
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=30) as response:
            _validate_pdf_url(response.geturl())
            payload = response.read(_MAX_PDF_BYTES + 1)
            content_type = response.headers.get_content_type()
    except (HTTPError, URLError, TimeoutError) as error:
        raise FullTextVerificationError("open-access PDF request failed") from error
    return PdfResponse(content_type=content_type, payload=payload)


def verify_open_access_pdf(
    request: OpenAccessPdfRequest,
    *,
    transport: Callable[[str], PdfResponse] = default_pdf_transport,
) -> FullTextReceipt:
    """Extract bounded text in memory and return a receipt without retaining content."""
    response = transport(request.url)
    if response.content_type != "application/pdf":
        raise FullTextVerificationError("response is not a PDF")
    if not response.payload.startswith(b"%PDF-"):
        raise FullTextVerificationError("response does not have a PDF signature")
    if len(response.payload) > _MAX_PDF_BYTES:
        raise FullTextVerificationError("PDF exceeds the size limit")
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
        reader = PdfReader(BytesIO(response.payload), strict=True)
        if len(reader.pages) > _MAX_PDF_PAGES:
            raise FullTextVerificationError("PDF exceeds the page limit")
        text = "".join((page.extract_text() or "") for page in reader.pages)
    except FullTextVerificationError:
        raise
    except Exception as error:
        raise FullTextVerificationError("PDF text extraction failed") from error
    if len(text) > _MAX_EXTRACTED_CHARS:
        raise FullTextVerificationError("extracted PDF text exceeds the limit")
    return FullTextReceipt(
        source_key=request.source_key,
        provider="arxiv",
        document_url=request.url,
        license_id=request.license_id.upper(),
        sha256=sha256(response.payload).hexdigest(),
        byte_count=len(response.payload),
        page_count=len(reader.pages),
        extracted_text_sha256=sha256(text.encode("utf-8")).hexdigest(),
        extracted_character_count=len(text),
    )
