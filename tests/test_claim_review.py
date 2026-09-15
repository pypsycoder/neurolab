"""Maturity policy must keep promising theory available but out of premature implementation."""

import unittest

from neurolab.claim_review import ClaimAssessment, ClaimReviewError, ReviewedClaim


SOURCE_KEY = "c" * 64
DOCUMENT_ID = "00000000-0000-0000-0000-000000000001"
ASSESSMENT = ClaimAssessment(
    assessor="approved_model",
    conceptual_support=0.8,
    empirical_support=None,
    reproducibility=None,
    feasibility_now=0.3,
    source_independence=0.4,
    uncertainty="high",
    rationale=("The method is explicitly specified, but no independently reproduced implementation was reviewed.",),
)


class ClaimReviewTests(unittest.TestCase):
    def test_formal_theory_is_kept_as_bounded_research_experiment(self):
        claim = ReviewedClaim(
            SOURCE_KEY,
            DOCUMENT_ID,
            "The proposed algorithm is formally specified and should be evaluated in a synthetic experiment before implementation.",
            3,
            5,
            "formal_or_method",
            "research_experiment",
            ASSESSMENT,
        )
        self.assertEqual(claim.evidence_locator, "pages 3-5")
        self.assertEqual(claim.reviewer_status, "needs_review")

    def test_theory_and_benchmark_cannot_be_promoted_by_a_single_score(self):
        with self.assertRaisesRegex(ClaimReviewError, "theory"):
            ReviewedClaim(SOURCE_KEY, DOCUMENT_ID, "A formal method should not skip prototype validation before implementation.", 1, 1, "formal_or_method", "implementation_candidate", ASSESSMENT)
        with self.assertRaisesRegex(ClaimReviewError, "benchmark"):
            ReviewedClaim(SOURCE_KEY, DOCUMENT_ID, "A benchmark result requires a prototype before implementation candidacy.", 1, 1, "simulated_or_benchmarked", "implementation_candidate", ASSESSMENT)

    def test_production_lane_is_outside_this_research_only_scope(self):
        with self.assertRaisesRegex(ClaimReviewError, "production"):
            ReviewedClaim(SOURCE_KEY, DOCUMENT_ID, "An operational result cannot enter production automatically from this corpus.", 1, 1, "operational", "production_candidate", ASSESSMENT)


if __name__ == "__main__":
    unittest.main()
