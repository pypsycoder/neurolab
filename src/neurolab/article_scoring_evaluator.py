"""Replayable contract evaluator for the metadata-only article classifier.

This is deliberately a classifier-contract evaluator, not a judgement about a
paper's scientific truth, usefulness, or reproducibility.  Those properties
need verified full text and later independently evaluated build outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import inspect
from typing import Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun, EvaluatorVersion
from neurolab.it_research import ResearchItem
from neurolab.research_corpus import ArchitectureLayer, SourceAssessment, classify_item


ARTICLE_SCORER_VERSION = "metadata_title_v1"
_CASE_IDS = ("arch_system", "workflow_tools", "trace_feature", "no_signal")


@dataclass(frozen=True)
class ArticleScoringCase:
    """Synthetic frozen case; it is never sent to a model or stored in PostgreSQL."""

    case_id: str
    item: ResearchItem
    expected_layers: tuple[ArchitectureLayer, ...]
    expected_confidence: float


def _item(title: str, provider: str, evidence_level: str) -> ResearchItem:
    return ResearchItem(
        provider=provider,  # type: ignore[arg-type]
        provider_id=f"synthetic-{sha256(title.encode()).hexdigest()[:12]}",
        url="https://example.invalid/synthetic",
        title=title,
        published_on="2026-01-01",
        checked_on="2026-01-01",
        evidence_level=evidence_level,  # type: ignore[arg-type]
        limitations=("synthetic evaluator fixture",),
        abstract="",
    )


def frozen_article_scoring_cases() -> tuple[ArticleScoringCase, ...]:
    """Return a compact, public/synthetic regression suite for the baseline."""
    return (
        ArticleScoringCase("arch_system", _item("Agentic system architecture", "arxiv", "reference"), ("global_architecture",), 0.45),
        ArticleScoringCase("workflow_tools", _item("Workflow planner with MCP tools", "openalex", "primary"), ("subsystem", "component"), 0.55),
        ArticleScoringCase("trace_feature", _item("Tracing and audit search", "crossref", "secondary"), ("feature",), 0.45),
        ArticleScoringCase("no_signal", _item("Methods for nocturnal butterflies", "arxiv", "reference"), ("component",), 0.20),
    )


def article_scorer_definition_sha256() -> str:
    """Fingerprint the implementation and frozen contract without retaining inputs."""
    material = "\n".join((ARTICLE_SCORER_VERSION, inspect.getsource(classify_item), *(_CASE_IDS)))
    return sha256(material.encode("utf-8")).hexdigest()


def article_scorer_baseline() -> EvaluatorVersion:
    """Stable identity makes repeated shadow runs attach to one baseline version."""
    definition = article_scorer_definition_sha256()
    evaluator_id = uuid5(NAMESPACE_URL, f"neurolab/article_scoring/{ARTICLE_SCORER_VERSION}/{definition}")
    return EvaluatorVersion(
        evaluator_id=str(evaluator_id),
        kind="article_scoring",
        version=ARTICLE_SCORER_VERSION,
        proposed_by="baseline_policy",
        definition_sha256=definition,
        frozen_case_ids=_CASE_IDS,
        active_case_ids=_CASE_IDS,
        state="promoted",
    )


def _cohort_sha256(cases: tuple[ArticleScoringCase, ...]) -> str:
    return sha256("\n".join(case.case_id for case in cases).encode("utf-8")).hexdigest()


def evaluate_article_scorer(
    *,
    classify: Callable[[ResearchItem], SourceAssessment] = classify_item,
    assessor: str = "contract_evaluator",
) -> EvaluationRun:
    """Measure only deterministic classifier-contract behaviour on frozen cases."""
    cases = frozen_article_scoring_cases()
    assessments = tuple(classify(case.item) for case in cases)
    primary = sum(assessment.architecture_layers == case.expected_layers for case, assessment in zip(cases, assessments, strict=True)) / len(cases)
    calibration = sum(abs(assessment.classification_confidence - case.expected_confidence) < 1e-9 for case, assessment in zip(cases, assessments, strict=True)) / len(cases)
    safety = sum(
        assessment.implementation_readiness == 0.0
        and assessment.reproducibility == 0.0
        and assessment.verification_status == "metadata_observed"
        for assessment in assessments
    ) / len(cases)
    return EvaluationRun(
        run_id=str(uuid4()),
        evaluator_id=article_scorer_baseline().evaluator_id,
        cohort_sha256=_cohort_sha256(cases),
        assessor=assessor,
        assessor_role="independent_evaluator",
        metrics=EvaluationMetrics(primary, safety, calibration, 1.0, len(cases)),
    )
