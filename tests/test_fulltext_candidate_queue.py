import unittest

from neurolab.fulltext_candidate_queue import build_fulltext_preflight_queue
from neurolab.it_research import ResearchItem
from neurolab.research_corpus import SourceAssessment


def assessment(*, key, provider="arxiv", provider_id="2609.12345", layers=("component",), status="metadata_observed"):
    item = ResearchItem(
        provider=provider, provider_id=provider_id, url="https://example.invalid", title="Synthetic title",
        published_on="2026-01-01", checked_on="2026-01-01", evidence_level="primary", limitations=(), abstract="",
    )
    return SourceAssessment(key, item, layers, .8, .55, 0.0, 0.0, .45, status, ("synthetic",))


class FulltextCandidateQueueTests(unittest.TestCase):
    def test_only_unverified_exact_arxiv_metadata_enters_queue(self):
        candidates = build_fulltext_preflight_queue((
            assessment(key="a" * 64, layers=("global_architecture",)),
            assessment(key="b" * 64, provider="openalex"),
            assessment(key="c" * 64, provider_id="bad-id"),
            assessment(key="d" * 64, status="content_verified"),
        ))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].source_key, "a" * 64)
        self.assertIn("license_preflight_required", candidates[0].reason_codes)

    def test_implementation_work_ranks_ahead_but_architecture_stays_eligible(self):
        candidates = build_fulltext_preflight_queue((
            assessment(key="a" * 64, layers=("global_architecture",)),
            assessment(key="b" * 64, layers=("component", "feature")),
        ))
        self.assertEqual([candidate.source_key for candidate in candidates], ["b" * 64, "a" * 64])

    def test_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            build_fulltext_preflight_queue((), limit=21)
