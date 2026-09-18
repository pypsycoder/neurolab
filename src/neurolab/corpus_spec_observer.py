"""Observe, but never control, the transition from corpus to specification.

The existing coverage gate remains the only authority in this module.  The
evaluator evidence is attached as a redacted receipt so operators can see
whether the classifiers used to build the corpus have a healthy baseline.
This observer cannot create a Code-agent task or change a coverage decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from neurolab.evaluator_storage import EvaluatorReceipt
from neurolab.research_corpus import CoverageAssessment


ObserverDecision = Literal[
    "continue_collecting_evidence",
    "hold_for_article_evaluator",
    "review_only_synthesis_candidate",
]


@dataclass(frozen=True)
class CorpusToSpecObservation:
    """Bounded facts used for logging an observe-only corpus decision."""

    policy_version: str
    coverage_status: str
    article_scorer_status: str
    response_quality_status: str
    decision: ObserverDecision
    reasons: tuple[str, ...]

    def as_snapshot(self) -> dict[str, object]:
        """Return only enums and fixed identifiers; never a source or response."""
        return asdict(self)


def _article_baseline_is_healthy(receipt: EvaluatorReceipt | None) -> bool:
    """Check the narrow metadata-classifier contract, not article truth."""
    if receipt is None or receipt.state != "promoted" or receipt.metrics is None:
        return False
    metrics = receipt.metrics
    return (
        metrics.primary_quality >= 0.99
        and metrics.safety_quality >= 0.99
        and metrics.calibration_quality >= 0.99
    )


def observe_corpus_to_spec(
    coverage: CoverageAssessment,
    *,
    article_scorer: EvaluatorReceipt | None,
    response_quality: EvaluatorReceipt | None,
) -> CorpusToSpecObservation:
    """Make a logged recommendation without modifying the coverage gate."""
    article_status = "healthy_baseline" if _article_baseline_is_healthy(article_scorer) else "baseline_missing_or_unhealthy"
    if response_quality is None:
        response_status = "not_observed"
    elif response_quality.state == "shadow" and response_quality.metrics is not None:
        response_status = "shadow_observed"
    else:
        response_status = "not_ready"

    if coverage.status != "ready_for_synthesis":
        return CorpusToSpecObservation(
            "corpus-spec-observer-v1",
            coverage.status,
            article_status,
            response_status,
            "continue_collecting_evidence",
            ("coverage_gate_not_ready",),
        )
    if article_status != "healthy_baseline":
        return CorpusToSpecObservation(
            "corpus-spec-observer-v1",
            coverage.status,
            article_status,
            response_status,
            "hold_for_article_evaluator",
            ("article_scorer_baseline_required",),
        )
    return CorpusToSpecObservation(
        "corpus-spec-observer-v1",
        coverage.status,
        article_status,
        response_status,
        "review_only_synthesis_candidate",
        ("coverage_gate_ready", "article_scorer_contract_healthy", "no_code_agent_dispatch"),
    )
