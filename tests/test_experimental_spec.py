import json
import unittest
from uuid import UUID

from neurolab.experimental_spec import ExperimentalPacket, EvidenceNote, PageLocator, build_spec_prompt, validate_draft, content_hash

CARD = "00000000-0000-0000-0000-000000000004"


def packet():
    return ExperimentalPacket(notes=[EvidenceNote(card_id=CARD, card_sha256="a"*64, source_key="b"*64,
        document_id=CARD, document_sha256="c"*64, kind="document", reviewer_status="needs_review", page_count=7,
        page_ranges=[PageLocator(page_start=1, page_end=3)], summary="A synthetic unreviewed provenance hypothesis.",
        limitations=["No independently reproduced implementation."], findings=["pages 1-3: Synthetic dependency tracking."])])


def raw_draft():
    return {"spec_version":"experimental-spec-v1", "boundary":"public_synthetic_experimental_only",
        "task_family":"synthetic_provenance_graph", "objective":"Test reachability in a synthetic artifact graph.",
        "architecture_rationale":"Use a small deterministic DAG instead of re-executing unrelated branches.",
        "components":[{"layer":"component", "name":"Affected nodes", "responsibility":"Find downstream artifact nodes.",
            "input_contract":"Directed string-name edges and failed node.", "output_contract":"Sorted unique affected names including failure."}],
        "requirements":[{"description":"Find reachable downstream nodes.", "rationale":"An experimental engineering choice, not proven article code.",
            "evidence":[{"card_id":CARD,"page_start":1,"page_end":3}]}],
        "acceptance_criteria":["Reachability includes the failed node.","Unrelated branches are unaffected.","Disconnected cycles are rejected."],
        "assumptions":["This is only a small synthetic DAG."],"risks":["Paper internals are not fully disclosed."],
        "next_search_queries":["artifact provenance DAG selective rerun evaluation"]}


class ExperimentalSpecTests(unittest.TestCase):
    def test_unreviewed_evidence_is_experimental_not_reviewed(self):
        evidence = packet()
        draft = validate_draft(json.dumps(raw_draft()), evidence)
        self.assertEqual(evidence.notes[0].reviewer_status, "needs_review")
        self.assertEqual(draft.boundary, "public_synthetic_experimental_only")
        self.assertEqual(len(content_hash(draft)), 64)
        self.assertIn("untrusted", build_spec_prompt(evidence))

    def test_unknown_evidence_or_unanalysed_pages_fail_closed(self):
        for card, start, end in ((str(UUID(int=5)),1,2),(CARD,4,5),(CARD,3,2),(CARD,1,8)):
            raw = raw_draft()
            raw["requirements"][0]["evidence"][0] = {"card_id":card,"page_start":start,"page_end":end}
            with self.assertRaises(ValueError):
                validate_draft(json.dumps(raw), packet())

    def test_production_lane_commands_extra_keys_and_false_pages_rejected(self):
        for key,value in (("boundary","production"),("task_family","clinical_agent"),("shell","rm -rf /")):
            raw = raw_draft(); raw[key] = value
            with self.assertRaises(ValueError):
                validate_draft(json.dumps(raw), packet())
        raw = raw_draft(); raw["requirements"][0]["evidence"][0]["page_start"] = True
        with self.assertRaises(ValueError):
            validate_draft(json.dumps(raw), packet())

    def test_card_rejection_and_unbounded_specs_rejected(self):
        note = packet().notes[0].model_dump(mode="json"); note["reviewer_status"] = "rejected"
        with self.assertRaises(ValueError):
            EvidenceNote.model_validate(note)
        with self.assertRaises(ValueError):
            validate_draft("x"*40001, packet())
