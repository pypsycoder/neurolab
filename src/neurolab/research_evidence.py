"""Public-source evidence contract with untrusted-content isolation."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from ipaddress import ip_address
import re
from typing import Literal
from urllib.parse import urlparse


EvidenceLevel = Literal["primary", "secondary", "reference"]


class ResearchEvidencePolicyError(ValueError):
    """Public-source evidence does not meet the synthetic research contract."""


@dataclass(frozen=True)
class PublicSourceEvidence:
    """One public-source record; raw_excerpt is untrusted data, never instructions."""

    source_id: str
    url: str
    title: str
    published_on: str
    checked_on: str
    evidence_level: EvidenceLevel
    limitations: tuple[str, ...]
    raw_excerpt: str


@dataclass(frozen=True)
class CitationMetadata:
    """Review-safe citation fields, deliberately excluding raw source content."""

    source_id: str
    url: str
    title: str
    published_on: str
    checked_on: str
    evidence_level: EvidenceLevel
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class ResearchReviewReport:
    """Review-only metadata report, deliberately excluding raw source content."""

    decision: Literal["review_required"]
    citations: tuple[CitationMetadata, ...]
    excerpt_digests: tuple[str, ...]
    audit: tuple[str, ...]


_SOURCE_ID = re.compile(r"^src-[a-z0-9-]{3,64}$")
_LEVELS: frozenset[str] = frozenset({"primary", "secondary", "reference"})
# Bibliographic providers legitimately expose compound titles that exceed the
# earlier 200-character UI-oriented limit.  Keep a bounded metadata ceiling so
# a malformed provider response cannot become an unbounded prompt artifact.
_MAX_TITLE_LENGTH = 500


def _public_hostname(url: str) -> str:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        raise ResearchEvidencePolicyError("source URL port is malformed") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise ResearchEvidencePolicyError("source URL must be public HTTPS without credentials")
    hostname = parsed.hostname.lower()
    try:
        address = ip_address(hostname)
    except ValueError:
        return hostname
    if not address.is_global:
        raise ResearchEvidencePolicyError("source URL must not use a non-public IP address")
    return hostname


def _parse_iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ResearchEvidencePolicyError(f"{field} must be an ISO date") from None


def require_public_evidence(evidence: PublicSourceEvidence) -> None:
    """Validate traceable public metadata while treating the excerpt as opaque data."""
    if not _SOURCE_ID.fullmatch(evidence.source_id):
        raise ResearchEvidencePolicyError("source id is malformed")
    _public_hostname(evidence.url)
    if not evidence.title.strip() or len(evidence.title) > _MAX_TITLE_LENGTH:
        raise ResearchEvidencePolicyError("source title is missing or too long")
    published_on = _parse_iso_date(evidence.published_on, "published_on")
    checked_on = _parse_iso_date(evidence.checked_on, "checked_on")
    if published_on > checked_on:
        raise ResearchEvidencePolicyError("source cannot be checked before publication")
    if evidence.evidence_level not in _LEVELS:
        raise ResearchEvidencePolicyError("evidence level is not declared")
    if not evidence.limitations or any(not item.strip() for item in evidence.limitations):
        raise ResearchEvidencePolicyError("source limitations are required")
    if not isinstance(evidence.raw_excerpt, str) or len(evidence.raw_excerpt) > 20_000:
        raise ResearchEvidencePolicyError("raw excerpt is invalid")


def build_research_review_report(
    evidence_items: Iterable[PublicSourceEvidence],
) -> ResearchReviewReport:
    """Create review-only evidence metadata from at least two public domains."""
    citations = tuple(evidence_items)
    if len(citations) < 2:
        raise ResearchEvidencePolicyError("at least two sources are required")

    source_ids: set[str] = set()
    hostnames: set[str] = set()
    for item in citations:
        require_public_evidence(item)
        if item.source_id in source_ids:
            raise ResearchEvidencePolicyError("source ids must be unique")
        source_ids.add(item.source_id)
        hostnames.add(_public_hostname(item.url))
    if len(hostnames) < 2:
        raise ResearchEvidencePolicyError("independent public domains are required")

    return ResearchReviewReport(
        decision="review_required",
        citations=tuple(
            CitationMetadata(
                source_id=item.source_id,
                url=item.url,
                title=item.title,
                published_on=item.published_on,
                checked_on=item.checked_on,
                evidence_level=item.evidence_level,
                limitations=item.limitations,
            )
            for item in citations
        ),
        excerpt_digests=tuple(
            sha256(item.raw_excerpt.encode("utf-8")).hexdigest() for item in citations
        ),
        audit=(
            "sources:public-https",
            "sources:independent-domains",
            "content:untrusted-opaque",
            "decision:review_required",
        ),
    )
