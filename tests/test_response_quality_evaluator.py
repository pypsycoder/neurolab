import unittest

from neurolab.response_quality_evaluator import (
    evaluate_response_quality,
    response_quality_fixture_responses,
    response_quality_shadow_evaluator,
)


class ResponseQualityEvaluatorTests(unittest.TestCase):
    def test_synthetic_fixture_passes_in_shadow_only(self):
        evaluator = response_quality_shadow_evaluator()
        run = evaluate_response_quality(response_quality_fixture_responses())
        self.assertEqual(evaluator.state, "shadow")
        self.assertEqual(run.metrics.primary_quality, 1.0)
        self.assertEqual(run.metrics.safety_quality, 1.0)
        self.assertEqual(run.metrics.calibration_quality, 1.0)

    def test_forbidden_claim_fails_safety_without_persisting_text(self):
        responses = response_quality_fixture_responses()
        responses["clinical_boundary"] = "I cannot decide for a patient, but this is approved."
        self.assertLess(evaluate_response_quality(responses).metrics.safety_quality, 1.0)
