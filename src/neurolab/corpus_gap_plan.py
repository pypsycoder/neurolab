"""Bounded acquisition policy, not an article judge or a specification author.

Only trusted query templates drive searches. Metadata supplies counts/ranking,
never commands. Discovery provenance is not independent scientific replication.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from neurolab.fulltext_candidate_queue import build_fulltext_preflight_queue
from neurolab.research_corpus import SourceAssessment, CoveragePolicy, evaluate_coverage

VERSION = "corpus-gap-v1"
LAYERS = ("global_architecture", "subsystem", "component", "feature")


@dataclass(frozen=True)
class SearchTemplate:
    template_id: str
    layer: str
    topic: str
    lane: str
    arxiv_terms: tuple[str, ...]


# Feasibility/quality are deliberately not inferred from these labels. The
# exploration slot keeps conceptual work eligible without authorising a build.
SEARCH_TEMPLATES = (
    SearchTemplate("architecture", "global_architecture", "agentic software architecture orchestration", "exploration", ("agent", "architecture", "orchestration")),
    SearchTemplate("workflow", "subsystem", "LLM agent workflow memory retrieval", "implementation_evidence_search", ("agent", "workflow", "memory")),
    SearchTemplate("evaluation", "component", "software agent evaluation benchmark reproducibility", "implementation_evidence_search", ("agent", "benchmark", "evaluation")),
    SearchTemplate("provenance", "feature", "workflow provenance tracing failure recovery", "implementation_evidence_search", ("workflow", "provenance", "recovery")),
    SearchTemplate("contracts", "component", "LLM tool contracts verification testing", "implementation_evidence_search", ("llm", "verification", "testing")),
    SearchTemplate("theory", "global_architecture", "formal verification autonomous agent systems", "exploration", ("agent", "formal", "verification")),
)


def corpus_fingerprint(assessments: tuple[SourceAssessment, ...]) -> str:
    """Ignore titles/content/duplicate observations; hash actual decision axes."""
    rows = sorted(set((a.source_key, a.item.provider, tuple(sorted(a.architecture_layers)),
                       a.verification_status, a.reproducibility) for a in assessments))
    return sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_corpus_gaps(
    assessments: tuple[SourceAssessment, ...], *, attempted_templates: tuple[str, ...] = (),
    document_source_keys: frozenset[str] = frozenset(), fulltext_limit: int = 6,
    policy: CoveragePolicy = CoveragePolicy(),
) -> dict[str, object]:
    """One search at most; no model call, status promotion, or executable task."""
    if any(t not in {t.template_id for t in SEARCH_TEMPLATES} for t in attempted_templates):
        raise ValueError("unknown search template history")
    if type(fulltext_limit) is not int or not 1 <= fulltext_limit <= 20:
        raise ValueError("fulltext limit outside boundary")
    coverage = evaluate_coverage(assessments, policy=policy)
    deficits = {layer: max(0, policy.minimum_sources_per_layer - coverage.sources_per_layer[layer])
                for layer in LAYERS}
    available = [t for t in SEARCH_TEMPLATES if t.template_id not in attempted_templates]
    # Largest missing layer first; stable order gives exploration a first slot
    # when all layers are empty. Six distinct attempts maximum per policy version.
    available.sort(key=lambda t: (-deficits[t.layer], LAYERS.index(t.layer),
                                 SEARCH_TEMPLATES.index(t)))
    next_search = asdict(available[0]) if available else None

    # Do not re-download a document just because its model card is unreviewed.
    pending = tuple(a for a in assessments if a.source_key not in document_source_keys)
    # Build each layer shortlist separately: a global/theory item must not be
    # lost to the top-20 practical utility cut before balancing even begins.
    by_key = {}
    for layer in LAYERS:
        for candidate in build_fulltext_preflight_queue(
                tuple(a for a in pending if layer in a.architecture_layers), limit=20):
            by_key[candidate.source_key] = candidate
    candidates = sorted(by_key.values(), key=lambda c: (-c.priority, c.source_key))
    source_layers = {a.source_key: a.architecture_layers for a in pending}
    selected = []
    selected_keys: set[str] = set()
    layer_order = sorted(LAYERS, key=lambda layer: (-deficits[layer], LAYERS.index(layer)))
    # Round-robin coverage: one candidate per layer before filling leftovers.
    # Multiple labels on one source never manufacture extra independent sources.
    for layer in layer_order:
        for candidate in candidates:
            if candidate.source_key not in selected_keys and layer in source_layers[candidate.source_key]:
                selected.append(candidate)
                selected_keys.add(candidate.source_key)
                break
        if len(selected) >= fulltext_limit:
            break
    for candidate in candidates:
        if len(selected) >= fulltext_limit:
            break
        if candidate.source_key not in selected_keys:
            selected.append(candidate)
            selected_keys.add(candidate.source_key)
    gaps = ["independent_semantic_spec_evaluation_required"]
    if any(deficits.values()):
        gaps.append("metadata_layer_coverage_incomplete")
    if coverage.content_verified_count < policy.minimum_content_verified_sources:
        gaps.append("verified_fulltext_claims_required")
    if coverage.buildable_reproducibility_mean < policy.minimum_reproducibility_mean_for_buildable_layers:
        gaps.append("measured_reproduction_required")
    return {
        "policy_version": VERSION, "boundary": "public_synthetic_experimental_only",
        "corpus_sha256": corpus_fingerprint(assessments),
        "coverage": asdict(coverage), "metadata_layer_deficits": deficits,
        "document_source_count": len(document_source_keys),
        "blocking_gaps": gaps, "full_spec_allowed": False,
        "next_search": next_search, "remaining_search_templates": len(available),
        "fulltext_candidates": [c.as_json_value() for c in selected],
        "decision": "continue_search" if next_search else "search_catalog_exhausted",
        "new_model_calls": 0,
    }
