"""Bounded F1000Research PDF retrieval after an explicit CC-BY HTML receipt.

The publisher's fixed PDF route may redirect once to its static file host.  The
redirect is not followed blindly: its host and path are constrained, its query
is discarded, and the final request permits no redirect.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import re
import signal
import socket
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ARTICLE_ID = re.compile(r"^\d{1,3}-\d{1,6}$")
_STATIC_PATH = re.compile(
    r"^/manuscripts/\d{1,12}/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}_f1000res\d{1,12}\.pdf$",
    re.IGNORECASE,
)
_MAX_PDF_BYTES = 25 * 1024 * 1024
_MAX_PDF_PAGES = 100
_MAX_EXTRACTED_CHARS = 1_000_000
_NETWORK_TIMEOUT_SECONDS = 90
_NETWORK_WALL_CLOCK_SECONDS = 180
_RANGE_CHUNK_BYTES = 256 * 1024
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class PublisherFullTextError(RuntimeError):
    """The F1000 PDF cannot enter the bounded full-text path."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@contextmanager
def _ipv4_only_resolution():
    """Use IPv4 for the static CDN in this disposable single-process route."""
    original = socket.getaddrinfo

    def ipv4_only(*args, **kwargs):  # type: ignore[no-untyped-def]
        addresses = original(*args, **kwargs)
        selected = [address for address in addresses if address[0] == socket.AF_INET]
        if not selected:
            raise socket.gaierror("no IPv4 address for static PDF host")
        return selected

    socket.getaddrinfo = ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = original


@contextmanager
def _network_wall_clock_limit():
    """Abort a slow-dripping response rather than allowing an unbounded read."""
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        yield
        return
    previous_handler = signal.getsignal(signal.SIGALRM)

    def expired(signum, frame):  # type: ignore[no-untyped-def]
        raise PublisherFullTextError("publisher PDF request exceeded the wall-clock limit")

    signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, _NETWORK_WALL_CLOCK_SECONDS)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


@dataclass(frozen=True)
class F1000OpenAccessPdfRequest:
    source_key: str
    article_id: str
    version: int = 1
    license_id: str = "CC-BY-4.0"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise PublisherFullTextError("source key is malformed")
        if not _ARTICLE_ID.fullmatch(self.article_id):
            raise PublisherFullTextError("article identifier is malformed")
        if not 1 <= self.version <= 99:
            raise PublisherFullTextError("article version is outside the bounded range")
        if self.license_id.upper() != "CC-BY-4.0":
            raise PublisherFullTextError("an explicit CC-BY-4.0 licence is required")

    @property
    def publisher_url(self) -> str:
        return f"https://f1000research.com/articles/{self.article_id}/v{self.version}/pdf"


@dataclass(frozen=True)
class PdfResponse:
    content_type: str
    payload: bytes
    document_url: str


@dataclass(frozen=True)
class PublisherFullTextReceipt:
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


def _validate_publisher_url(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "f1000research.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not re.fullmatch(r"/articles/\d{1,3}-\d{1,6}/v\d{1,2}/pdf", parsed.path)
        or parsed.query
        or parsed.fragment
    ):
        raise PublisherFullTextError("publisher PDF target is outside the allowlist")


def _stable_file_url(location: str) -> str:
    parsed = urlparse(location)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "f1000research-files.f1000.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not _STATIC_PATH.fullmatch(parsed.path)
        or parsed.fragment
    ):
        raise PublisherFullTextError("publisher PDF redirect is outside the static-file allowlist")
    return urlunparse(("https", parsed.hostname, parsed.path, "", "", ""))


def default_f1000_pdf_transport(url: str) -> PdfResponse:
    """Resolve one fixed publisher PDF route, then fetch one stable file URL."""
    _validate_publisher_url(url)
    request = Request(url, headers={"User-Agent": "neurolab-publisher-fulltext/0.1"}, method="GET")
    try:
        build_opener(_NoRedirect()).open(request, timeout=_NETWORK_TIMEOUT_SECONDS)
    except HTTPError as error:
        if error.code not in {301, 302, 303, 307, 308}:
            raise PublisherFullTextError("publisher PDF route failed") from error
        location = error.headers.get("Location")
    except (URLError, TimeoutError) as error:
        raise PublisherFullTextError("publisher PDF route failed") from error
    else:
        raise PublisherFullTextError("publisher PDF route did not provide the expected static redirect")
    if not isinstance(location, str):
        raise PublisherFullTextError("publisher PDF redirect has no location")
    static_url = _stable_file_url(location)
    try:
        with _network_wall_clock_limit(), _ipv4_only_resolution():
            payload, content_type = _read_static_pdf_ranges(static_url)
    except (HTTPError, URLError, TimeoutError) as error:
        raise PublisherFullTextError("publisher static PDF request failed") from error
    return PdfResponse(content_type=content_type, payload=payload, document_url=static_url)


def _read_static_pdf_ranges(static_url: str) -> tuple[bytes, str]:
    """Fetch contiguous bounded ranges; reject a CDN that ignores Range."""
    payload = bytearray()
    expected_start = 0
    total_size: int | None = None
    content_type = ""
    while total_size is None or expected_start < total_size:
        expected_end = min(expected_start + _RANGE_CHUNK_BYTES - 1, _MAX_PDF_BYTES - 1)
        request = Request(
            static_url,
            headers={
                "User-Agent": "neurolab-publisher-fulltext/0.1",
                "Range": f"bytes={expected_start}-{expected_end}",
            },
            method="GET",
        )
        with build_opener(_NoRedirect()).open(request, timeout=_NETWORK_TIMEOUT_SECONDS) as response:
            if response.geturl() != static_url or response.status != 206:
                raise PublisherFullTextError("publisher static PDF did not honour the fixed range request")
            match = _CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
            if match is None:
                raise PublisherFullTextError("publisher static PDF has no valid content range")
            range_start, range_end, declared_total = (int(value) for value in match.groups())
            if range_start != expected_start or range_end < range_start:
                raise PublisherFullTextError("publisher static PDF content range is discontinuous")
            if declared_total <= 0 or declared_total > _MAX_PDF_BYTES or range_end >= declared_total:
                raise PublisherFullTextError("publisher static PDF size is outside the limit")
            if total_size is not None and declared_total != total_size:
                raise PublisherFullTextError("publisher static PDF size changed during retrieval")
            total_size = declared_total
            expected_length = range_end - range_start + 1
            part = response.read(expected_length + 1)
            if len(part) != expected_length:
                raise PublisherFullTextError("publisher static PDF range is incomplete")
            content_type = response.headers.get_content_type()
        payload.extend(part)
        expected_start = range_end + 1
    return bytes(payload), content_type


def verify_f1000_open_access_pdf(
    request: F1000OpenAccessPdfRequest,
    *,
    transport: Callable[[str], PdfResponse] = default_f1000_pdf_transport,
) -> PublisherFullTextReceipt:
    """Extract a verified F1000 CC-BY PDF in memory and retain only its receipt."""
    response = transport(request.publisher_url)
    if response.content_type not in {"application/pdf", "application/octet-stream"}:
        raise PublisherFullTextError("publisher response is not an allowed PDF MIME type")
    if not response.payload.startswith(b"%PDF-"):
        raise PublisherFullTextError("publisher response does not have a PDF signature")
    if len(response.payload) > _MAX_PDF_BYTES:
        raise PublisherFullTextError("publisher PDF exceeds the size limit")
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
        reader = PdfReader(BytesIO(response.payload), strict=True)
        if len(reader.pages) > _MAX_PDF_PAGES:
            raise PublisherFullTextError("publisher PDF exceeds the page limit")
        text = "".join(page.extract_text() or "" for page in reader.pages)
    except PublisherFullTextError:
        raise
    except Exception as error:
        raise PublisherFullTextError("publisher PDF text extraction failed") from error
    if len(text) > _MAX_EXTRACTED_CHARS:
        raise PublisherFullTextError("publisher extracted text exceeds the limit")
    return PublisherFullTextReceipt(
        source_key=request.source_key,
        provider="f1000research",
        document_url=response.document_url,
        license_id="CC-BY-4.0",
        sha256=sha256(response.payload).hexdigest(),
        byte_count=len(response.payload),
        page_count=len(reader.pages),
        extracted_text_sha256=sha256(text.encode("utf-8")).hexdigest(),
        extracted_character_count=len(text),
    )
