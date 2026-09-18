import unittest

from neurolab.article_scoring_evaluator import article_scorer_baseline, evaluate_article_scorer, frozen_article_scoring_cases
from neurolab.research_corpus import classify_item


class ArticleScoringEvaluatorTests(unittest.TestCase):
    def test_baseline_passes_its_frozen_synthetic_contract(self):
        evaluator = article_scorer_baseline()
        run = evaluate_article_scorer()
        self.assertEqual(evaluator.state, "promoted")
        self.assertEqual(run.evaluator_id, evaluator.evaluator_id)
        self.assertEqual(run.metrics.primary_quality, 1.0)
        self.assertEqual(run.metrics.safety_quality, 1.0)
        self.assertEqual(run.metrics.evaluated_case_count, len(frozen_article_scoring_cases()))

    def test_contract_catches_wrong_taxonomy(self):
        def wrong_classifier(item):
            result = classify_item(item)
            return result.__class__(
                result.source_key, result.item, ("feature",), result.classification_confidence,
                result.conceptual_support, result.implementation_readiness, result.reproducibility,
                result.source_independence, result.verification_status, result.rationale,
            )

        self.assertLess(evaluate_article_scorer(classify=wrong_classifier).metrics.primary_quality, 1.0)
