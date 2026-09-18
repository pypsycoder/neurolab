"""Deterministic preflight queue for legally verifiable public arXiv PDFs.

Items in this queue are not licensed documents and not verified evidence.  A
subsequent fixed-host license/PDF verifier must approve every item separately.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from neurolab.research_corpus import SourceAssessment


_ARXIV_ID = re.compile(r"^\d{4}\.\d{4,5}(?:v\d+)?$")


@dataclass(frozen=True)
class FulltextPreflightCandidate:
    source_key: str
    arxiv_id: str
    priority: float
    reason_codes: tuple[str, ...]
    required_next_action: str = "verify_arxiv_license_and_exact_pdf"

    def as_json_value(self) -> dict[str, object]:
        return asdict(self)


def _priority(assessment: SourceAssessment) -> tuple[float, tuple[str, ...]]:
    """Rank research utility, not truth or reproducibility, from existing axes."""
    layers = set(assessment.architecture_layers)
    score = 0.10 + 0.20 * assessment.conceptual_support + 0.10 * assessment.classification_confidence
    score += 0.10 * assessment.source_independence
    reasons = ["metadata_only", "license_preflight_required"]
    if "component" in layers or "feature" in layers:
        score += 0.25
        reasons.append("implementation_or_feature_coverage")
    if "subsystem" in layers:
        score += 0.15
        reasons.append("subsystem_coverage")
    if "global_architecture" in layers:
        score += 0.10
        reasons.append("global_architecture_context")
    # Conceptual/global work remains eligible; the score only prevents an
    # unbounded queue of metadata-only architecture essays from starving
    # implementation-oriented evidence.
    return round(min(score, 1.0), 3), tuple(reasons)


def build_fulltext_preflight_queue(
    assessments: tuple[SourceAssessment, ...], *, limit: int = 8
) -> tuple[FulltextPreflightCandidate, ...]:
    """Return bounded fixed-host candidates without following any URL."""
    if not 1 <= limit <= 20:
        raise ValueError("preflight queue limit must be between 1 and 20")
    by_source: dict[str, SourceAssessment] = {}
    for assessment in assessments:
        if assessment.item.provider != "arxiv" or assessment.verification_status != "metadata_observed":
            continue
        if not _ARXIV_ID.fullmatch(assessment.item.provider_id):
            continue
        previous = by_source.get(assessment.source_key)
        if previous is None or assessment.classification_confidence > previous.classification_confidence:
            by_source[assessment.source_key] = assessment
    candidates = []
    for assessment in by_source.values():
        priority, reasons = _priority(assessment)
        candidates.append(
            FulltextPreflightCandidate(
                source_key=assessment.source_key,
                arxiv_id=assessment.item.provider_id,
                priority=priority,
                reason_codes=reasons,
            )
        )
    return tuple(sorted(candidates, key=lambda item: (-item.priority, item.source_key))[:limit])
