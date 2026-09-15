"""Validated, human-reviewed claim records for the public IT corpus."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
from uuid import UUID


Maturity = Literal[
    "hypothesis", "formal_or_method", "simulated_or_benchmarked", "prototype", "replicated", "operational"
]
ActionLane = Literal["watchlist", "research_experiment", "implementation_candidate", "production_candidate"]
Uncertainty = Literal["low", "medium", "high", "unknown"]
Assessor = Literal["human", "approved_model"]

_MATURITY_RANK: dict[Maturity, int] = {
    "hypothesis": 0,
    "formal_or_method": 1,
    "simulated_or_benchmarked": 2,
    "prototype": 3,
    "replicated": 4,
    "operational": 5,
}
_ONE_LINE = re.compile(r"^[^\r\n]{20,1200}$")


class ClaimReviewError(ValueError):
    """A claim lacks a bounded page reference or violates maturity policy."""


@dataclass(frozen=True)
class ClaimAssessment:
    assessor: Assessor
    conceptual_support: float | None
    empirical_support: float | None
    reproducibility: float | None
    feasibility_now: float | None
    source_independence: float | None
    uncertainty: Uncertainty
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        for score in (
            self.conceptual_support,
            self.empirical_support,
            self.reproducibility,
            self.feasibility_now,
            self.source_independence,
        ):
            if score is not None and not 0 <= score <= 1:
                raise ClaimReviewError("claim score must be between 0 and 1")
        if not self.rationale or any(not _ONE_LINE.fullmatch(item) for item in self.rationale):
            raise ClaimReviewError("claim rationale must contain bounded one-line evidence notes")


@dataclass(frozen=True)
class ReviewedClaim:
    source_key: str
    document_id: str
    summary: str
    page_start: int
    page_end: int
    maturity: Maturity
    action_lane: ActionLane
    assessment: ClaimAssessment

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_key):
            raise ClaimReviewError("source key is malformed")
        try:
            UUID(self.document_id)
        except ValueError as error:
            raise ClaimReviewError("document id is malformed") from error
        if not _ONE_LINE.fullmatch(self.summary):
            raise ClaimReviewError("claim summary must be a bounded one-line statement")
        if not 1 <= self.page_start <= self.page_end <= 100:
            raise ClaimReviewError("claim page range is malformed")
        _validate_maturity_lane(self.maturity, self.action_lane)

    @property
    def evidence_locator(self) -> str:
        return f"page {self.page_start}" if self.page_start == self.page_end else f"pages {self.page_start}-{self.page_end}"

    @property
    def reviewer_status(self) -> Literal["needs_review", "reviewed"]:
        return "reviewed" if self.assessment.assessor == "human" else "needs_review"


def _validate_maturity_lane(maturity: Maturity, lane: ActionLane) -> None:
    rank = _MATURITY_RANK[maturity]
    if lane == "production_candidate":
        raise ClaimReviewError("production candidate claims are outside the current research-only scope")
    if rank <= 1 and lane not in {"watchlist", "research_experiment"}:
        raise ClaimReviewError("theory may enter watchlist or bounded research experiments only")
    if rank == 2 and lane == "implementation_candidate":
        raise ClaimReviewError("benchmark-only claims require a prototype before implementation candidacy")
