"""Conservative classification and coverage gates for public IT research.

This module deliberately does not decide whether a claim is true.  It keeps
conceptual support, implementation readiness, reproducibility and source
independence on separate axes so that a useful theoretical paper is not
mistakenly treated as a reproduced implementation (or vice versa).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Literal

from neurolab.it_research import ResearchItem


ArchitectureLayer = Literal["global_architecture", "subsystem", "component", "feature"]
SynthesisStatus = Literal["collecting_evidence", "ready_for_synthesis"]

_LAYERS: tuple[ArchitectureLayer, ...] = (
    "global_architecture",
    "subsystem",
    "component",
    "feature",
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{2,}", re.IGNORECASE)
_LAYER_TERMS: dict[ArchitectureLayer, frozenset[str]] = {
    "global_architecture": frozenset({"architecture", "architectures", "framework", "system", "systems", "agentic", "orchestration"}),
    "subsystem": frozenset({"pipeline", "workflow", "planner", "planning", "memory", "retrieval", "supervisor", "routing"}),
    "component": frozenset({"mcp", "langgraph", "tool", "tools", "evaluation", "benchmark", "guardrail", "testing", "agent"}),
    "feature": frozenset({"review", "trace", "tracing", "logging", "observability", "search", "ranking", "citation", "audit"}),
}
_VERIFICATION_RANK = {"metadata_observed": 0, "metadata_corroborated": 1, "content_verified": 2}


@dataclass(frozen=True)
class SourceAssessment:
    """A reviewable assessment based only on the currently observed metadata."""

    source_key: str
    item: ResearchItem
    architecture_layers: tuple[ArchitectureLayer, ...]
    classification_confidence: float
    conceptual_support: float
    implementation_readiness: float
    reproducibility: float
    source_independence: float
    verification_status: Literal["metadata_observed", "metadata_corroborated", "content_verified"]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class CoveragePolicy:
    """Versioned, deliberately modest gate before an LLM may draft a task."""

    minimum_unique_sources: int = 12
    minimum_sources_per_layer: int = 3
    minimum_provider_provenance: int = 2
    minimum_content_verified_sources: int = 4
    minimum_reproducibility_mean_for_buildable_layers: float = 0.35


@dataclass(frozen=True)
class CoverageAssessment:
    status: SynthesisStatus
    unique_source_count: int
    provider_provenance_count: int
    sources_per_layer: dict[ArchitectureLayer, int]
    content_verified_count: int
    buildable_reproducibility_mean: float
    unmet_requirements: tuple[str, ...]


def canonical_source_key(item: ResearchItem) -> str:
    """Deduplicate observations without storing an abstract or following a URL."""
    stable = (item.doi or item.url).strip().casefold()
    return sha256(stable.encode("utf-8")).hexdigest()


def classify_item(item: ResearchItem) -> SourceAssessment:
    """Classify title metadata conservatively; a human can later amend it."""
    terms = set(_TOKEN.findall(item.title.casefold()))
    layers = tuple(layer for layer in _LAYERS if terms & _LAYER_TERMS[layer])
    if not layers:
        layers = ("component",)
        confidence = 0.2
        rationale = ("Title has no taxonomy signal; assigned component only as a low-confidence review queue.",)
    else:
        confidence = min(0.8, 0.35 + (0.1 * len(layers)))
        rationale = ("Architecture layer is a deterministic title-metadata classification and requires human review.",)

    # Discovery APIs provide bibliographic metadata only.  No code, dataset,
    # reproduction procedure or independent replication has been verified.
    provider_independence = {"arxiv": 0.45, "openalex": 0.55, "crossref": 0.55}[item.provider]
    conceptual = {"reference": 0.45, "secondary": 0.5, "primary": 0.55}[item.evidence_level]
    return SourceAssessment(
        source_key=canonical_source_key(item),
        item=item,
        architecture_layers=layers,
        classification_confidence=confidence,
        conceptual_support=conceptual,
        implementation_readiness=0.0,
        reproducibility=0.0,
        source_independence=provider_independence,
        verification_status="metadata_observed",
        rationale=rationale
        + (
            "Metadata-only discovery is not evidence of executable code, dataset availability, or reproduced results.",
        ),
    )


def evaluate_coverage(
    assessments: Iterable[SourceAssessment], *, policy: CoveragePolicy = CoveragePolicy()
) -> CoverageAssessment:
    """Fail closed until the corpus has balanced, reproducible verified evidence."""
    by_key: dict[str, SourceAssessment] = {}
    providers: set[str] = set()
    for assessment in assessments:
        providers.add(assessment.item.provider)
        previous = by_key.get(assessment.source_key)
        # A later, more strongly verified assessment may replace a metadata-only
        # observation of the same DOI/landing record.
        if previous is None or _VERIFICATION_RANK[assessment.verification_status] > _VERIFICATION_RANK[previous.verification_status]:
            by_key[assessment.source_key] = assessment

    values = tuple(by_key.values())
    layer_counts = {
        layer: sum(layer in assessment.architecture_layers for assessment in values)
        for layer in _LAYERS
    }
    buildable = tuple(
        assessment.reproducibility
        for assessment in values
        if "component" in assessment.architecture_layers or "feature" in assessment.architecture_layers
    )
    reproducibility_mean = sum(buildable) / len(buildable) if buildable else 0.0
    verified_count = sum(assessment.verification_status == "content_verified" for assessment in values)

    unmet: list[str] = []
    if len(values) < policy.minimum_unique_sources:
        unmet.append(f"need {policy.minimum_unique_sources - len(values)} more unique sources")
    if len(providers) < policy.minimum_provider_provenance:
        unmet.append("need metadata from at least two provider provenances")
    for layer in _LAYERS:
        missing = policy.minimum_sources_per_layer - layer_counts[layer]
        if missing > 0:
            unmet.append(f"need {missing} more sources for {layer}")
    if verified_count < policy.minimum_content_verified_sources:
        unmet.append(f"need {policy.minimum_content_verified_sources - verified_count} more content-verified sources")
    if reproducibility_mean < policy.minimum_reproducibility_mean_for_buildable_layers:
        unmet.append("need reproducibility evidence for component and feature sources")

    return CoverageAssessment(
        status="ready_for_synthesis" if not unmet else "collecting_evidence",
        unique_source_count=len(values),
        provider_provenance_count=len(providers),
        sources_per_layer=layer_counts,
        content_verified_count=verified_count,
        buildable_reproducibility_mean=round(reproducibility_mean, 3),
        unmet_requirements=tuple(unmet),
    )


def render_synthesis_status(coverage: CoverageAssessment, *, goal: str) -> str:
    """Produce a human-readable refusal/receipt, never an early Code-agent task."""
    if coverage.status == "ready_for_synthesis":
        return (
            f"# Корпус готов к синтезу\n\nЦель: {goal}\n\n"
            "Coverage gate пройден. Следующий шаг — отдельный review-only синтез "
            "из структурированных, проверенных записей корпуса.\n"
        )
    missing = "\n".join(f"- {item}" for item in coverage.unmet_requirements)
    return f"""# ТЗ для Code agent не сформировано

Цель: {goal}

Статус корпуса: `collecting_evidence`. Одноразовая выдача discovery-провайдеров
не считается достаточным основанием для архитектурного ТЗ. Сначала нужны
накопление, дедупликация, проверка воспроизводимости и покрытие всех уровней.

## Что ещё требуется

{missing}

Никакой Code agent не должен получать задание из этого артефакта.
"""
