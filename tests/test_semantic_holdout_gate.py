import unittest
from hashlib import sha256
import json

from neurolab.semantic_holdout_gate import (
    SEMANTIC_HOLDOUT_CASE_IDS,
    SemanticHoldoutError,
    SignedSemanticHoldoutReceipt,
    semantic_holdout_case_set_sha256,
    semantic_holdout_evaluator,
    sign_semantic_holdout_payload,
    verified_semantic_holdout_run,
)


KEY = "unit-test-sealed-key"
CANDIDATE_ASSET = sha256(b"candidate-asset").hexdigest()
CANDIDATE_MODEL = sha256(b"candidate-model").hexdigest()
JUDGE_MODEL = sha256(b"independent-judge-model").hexdigest()


def receipt(**changes):
    payload = {
        "judge_id": "external_semantic_judge",
        "judge_model_sha256": JUDGE_MODEL,
        "candidate_artifact_sha256": CANDIDATE_ASSET,
        "candidate_model_sha256": CANDIDATE_MODEL,
        "case_set_sha256": semantic_holdout_case_set_sha256(),
        "evaluated_case_count": 20,
        "primary_quality": 0.9,
        "safety_quality": 1.0,
        "calibration_quality": 0.85,
    }
    payload.update(changes)
    signature = sign_semantic_holdout_payload(payload, KEY)
    return SignedSemanticHoldoutReceipt(**payload, signature_sha256=signature)


class SemanticHoldoutGateTests(unittest.TestCase):
    def test_holdout_is_opaque_20_case_shadow_contract(self):
        evaluator = semantic_holdout_evaluator()
        self.assertEqual(len(SEMANTIC_HOLDOUT_CASE_IDS), 20)
        self.assertEqual(evaluator.state, "shadow")
        self.assertEqual(evaluator.frozen_case_set_sha256, semantic_holdout_case_set_sha256())

    def test_valid_signed_aggregate_creates_independent_run(self):
        run = verified_semantic_holdout_run(
            receipt(),
            signing_key=KEY,
            expected_candidate_artifact_sha256=CANDIDATE_ASSET,
            expected_candidate_model_sha256=CANDIDATE_MODEL,
        )
        self.assertEqual(run.assessor, "external_semantic_judge")
        self.assertEqual(run.metrics.evaluated_case_count, 20)

    def test_signature_or_candidate_mismatch_fails_closed(self):
        signed = receipt()
        with self.assertRaises(SemanticHoldoutError):
            verified_semantic_holdout_run(
                signed,
                signing_key="wrong-key",
                expected_candidate_artifact_sha256=CANDIDATE_ASSET,
                expected_candidate_model_sha256=CANDIDATE_MODEL,
            )
        with self.assertRaises(SemanticHoldoutError):
            verified_semantic_holdout_run(
                signed,
                signing_key=KEY,
                expected_candidate_artifact_sha256=sha256(b"other").hexdigest(),
                expected_candidate_model_sha256=CANDIDATE_MODEL,
            )

    def test_same_model_is_rejected_before_signature_trust(self):
        payload = receipt().unsigned_payload()
        payload["judge_model_sha256"] = CANDIDATE_MODEL
        with self.assertRaises(SemanticHoldoutError):
            SignedSemanticHoldoutReceipt(
                **payload,
                signature_sha256=sign_semantic_holdout_payload(payload, KEY),
            )

    def test_json_allowlist_rejects_content_bearing_fields(self):
        signed = receipt()
        raw = {**signed.unsigned_payload(), "signature_sha256": signed.signature_sha256}
        rebuilt = SignedSemanticHoldoutReceipt.from_json(json.dumps(raw))
        self.assertEqual(rebuilt, signed)
        raw["response"] = "must not enter the receipt"
        with self.assertRaises(SemanticHoldoutError):
            SignedSemanticHoldoutReceipt.from_json(json.dumps(raw))
