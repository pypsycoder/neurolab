from copy import deepcopy
from dataclasses import replace
import unittest

from neurolab.document_analysis_assessment import assess_document_analysis, assess_numeric_anchors
from neurolab.document_cards import DocumentCard, CardFinding


class DocumentAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.card = DocumentCard(source_key="a" * 64, document_id="00000000-0000-0000-0000-000000000001",
            document_sha256="b" * 64,
            document_summary="Работа описывает экспериментальную архитектуру агентных программных систем.",
            research_problem="Требуется сравнить поведение компонентов при воспроизводимых условиях.",
            method="Предлагается ограниченное структурированное представление зависимостей системы.",
            architecture_layers=("component",), implementation_signals=(), evaluation_signals=(),
            limitations=("Независимое воспроизведение результатов не выполнено.",),
            findings=(CardFinding(1, 4, "method", "Описаны зависимости экспериментального рабочего процесса."),),
            conceptual_support=.9, empirical_support=.9, reproducibility=.9, feasibility_now=.9,
            source_independence=.9, uncertainty="high")
        self.receipt = {"version": "document-analysis-v2", "run_id": "00000000-0000-0000-0000-000000000002",
            "source_key": self.card.source_key, "document_id": self.card.document_id,
            "document_sha256": self.card.document_sha256, "page_count": 4, "window_count": 2,
            "empty_text_pages": [], "card_sha256": self.card.card_sha256, "status": "needs_review",
            "attempts": [{"kind": "window", "page_start": 1, "page_end": 2, "step_key": "c" * 64,
                          "new_model_calls": 1, "status": "completed", "provider_tokens": {"total_tokens": 100}},
                         {"kind": "window", "page_start": 3, "page_end": 4, "step_key": "d" * 64,
                          "new_model_calls": 1, "status": "completed", "provider_tokens": {"total_tokens": 100}},
                         {"kind": "synthesis", "step_key": "e" * 64, "new_model_calls": 1,
                          "status": "completed", "provider_tokens": {"total_tokens": 100}}]}

    def assess(self, *, card=None, receipt=None):
        return assess_document_analysis(card or self.card, receipt or self.receipt,
                                        page_count=4, pdf_sha256="b" * 64)

    def test_structural_pass_never_endorses_model_self_scores(self):
        result = self.assess()
        self.assertTrue(result["structure_passed"])
        self.assertEqual(result["decision"], "experimental_hypothesis_only")
        self.assertEqual(result["semantic_verification"], "not_performed")
        self.assertEqual(result["independent_reproduction"], "not_performed")
        self.assertFalse(result["full_spec_allowed"])
        self.assertEqual(result["known_provider_tokens_in_source_run"], 300)

    def test_partial_coverage_and_unknown_status_are_not_complete(self):
        receipt = deepcopy(self.receipt)
        receipt["attempts"][1]["page_end"] = 3
        result = self.assess(receipt=receipt)
        self.assertIn("complete_extractable_page_coverage", result["failed_checks"])
        receipt = deepcopy(self.receipt)
        receipt["attempts"][1]["status"] = "outcome_unknown"
        self.assertIn("all_steps_complete", self.assess(receipt=receipt)["failed_checks"])

    def test_foreign_identity_or_card_hash_cannot_pass(self):
        for field in ("source_key", "document_sha256", "card_sha256"):
            receipt = dict(self.receipt, **{field: "f" * 64})
            self.assertFalse(self.assess(receipt=receipt)["checks"]["exact_identity"])

    def test_unknown_usage_is_not_reported_as_zero_cost(self):
        receipt = deepcopy(self.receipt)
        receipt["attempts"][0]["provider_tokens"] = {}
        result = self.assess(receipt=receipt)
        self.assertEqual(result["known_provider_tokens_in_source_run"], 200)
        self.assertEqual(result["calls_with_unknown_usage"], 1)

    def test_reuse_does_not_inflate_new_calls_or_tokens(self):
        receipt = deepcopy(self.receipt)
        receipt["attempts"][0].update(status="reused", new_model_calls=0, provider_tokens={})
        result = self.assess(receipt=receipt)
        self.assertTrue(result["structure_passed"])
        self.assertEqual(result["new_model_calls_in_source_run"], 2)
        self.assertEqual(result["calls_with_unknown_usage"], 0)

    def test_english_card_and_missing_limitations_are_visible_failures(self):
        card = replace(self.card, method="The method is an experimental software architecture design.", limitations=())
        result = self.assess(card=card, receipt=dict(self.receipt, card_sha256=card.card_sha256))
        self.assertIn("russian_language_hint", result["failed_checks"])
        self.assertIn("limitations_explicit", result["failed_checks"])

    def test_bad_page_types_duplicate_step_and_phantom_synthesis_refused(self):
        receipt = deepcopy(self.receipt)
        receipt["attempts"][0]["page_start"] = True
        with self.assertRaises(ValueError):
            self.assess(receipt=receipt)
        receipt = deepcopy(self.receipt)
        receipt["attempts"][1]["step_key"] = "c" * 64
        self.assertFalse(self.assess(receipt=receipt)["checks"]["all_steps_complete"])

    def test_numeric_anchor_detects_invention_and_never_proves_semantics(self):
        card = replace(self.card, findings=(CardFinding(1, 1, "evaluation", "Описана оценка на 8504 примерах и 1642 инструментах."),))
        result = assess_numeric_anchors(card, ("Dataset: 8,504 examples; 1,642 tools",))
        self.assertEqual(result["numeric_anchor_status"], "supported")
        self.assertFalse(result["semantic_entailment_verified"])
        result = assess_numeric_anchors(card, ("Dataset: 85.04 examples; 1,642 tools",))
        self.assertEqual(result["failed_numeric_anchor_cases"], ["finding_1"])

    def test_numeric_support_on_another_page_is_not_support_for_cited_page(self):
        card = replace(self.card, findings=(CardFinding(1, 1, "evaluation", "Описана оценка на 8504 экспериментальных примерах."),))
        result = assess_numeric_anchors(card, ("No number", "8,504 examples"))
        self.assertEqual(result["numeric_anchor_status"], "mismatch")
