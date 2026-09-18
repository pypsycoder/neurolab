import unittest
from hashlib import sha256

from neurolab.corpus_spec_observer import observe_corpus_to_spec
from neurolab.evaluator_evolution import EvaluationMetrics
from neurolab.evaluator_storage import EvaluatorReceipt
from neurolab.research_corpus import CoverageAssessment


def coverage(status: str) -> CoverageAssessment:
    return CoverageAssessment(
        status=status,  # type: ignore[arg-type]
        unique_source_count=12,
        provider_provenance_count=2,
        sources_per_layer={"global_architecture": 3, "subsystem": 3, "component": 3, "feature": 3},
        content_verified_count=4,
        buildable_reproducibility_mean=.5,
        unmet_requirements=() if status == "ready_for_synthesis" else ("need evidence",),
    )


def receipt(kind: str, version: str, state: str, *, primary=1.0) -> EvaluatorReceipt:
    return EvaluatorReceipt(kind, version, state, sha256(version.encode()).hexdigest(), EvaluationMetrics(primary, 1.0, 1.0, 1.0, 4))


class CorpusSpecObserverTests(unittest.TestCase):
    def test_collecting_corpus_remains_authoritative_even_with_healthy_evaluators(self):
        result = observe_corpus_to_spec(
            coverage("collecting_evidence"),
            article_scorer=receipt("article_scoring", "metadata_title_v1", "promoted"),
            response_quality=receipt("response_quality", "response_contract_v1", "shadow"),
        )
        self.assertEqual(result.decision, "continue_collecting_evidence")

    def test_ready_coverage_requires_article_baseline_but_never_dispatches_code_agent(self):
        result = observe_corpus_to_spec(
            coverage("ready_for_synthesis"),
            article_scorer=receipt("article_scoring", "metadata_title_v1", "promoted"),
            response_quality=receipt("response_quality", "response_contract_v1", "shadow"),
        )
        self.assertEqual(result.decision, "review_only_synthesis_candidate")
        self.assertIn("no_code_agent_dispatch", result.reasons)

    def test_ready_coverage_holds_when_baseline_contract_is_not_healthy(self):
        result = observe_corpus_to_spec(
            coverage("ready_for_synthesis"), article_scorer=None, response_quality=None
        )
        self.assertEqual(result.decision, "hold_for_article_evaluator")
