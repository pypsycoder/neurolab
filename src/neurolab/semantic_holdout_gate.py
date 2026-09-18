"""Fail-closed gate for a sealed, independently judged response holdout.

The holdout's prompts, candidate responses, judge rationale and per-case
results stay outside this repository and outside PostgreSQL.  This module only
accepts a signed aggregate receipt from that separate environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
from uuid import NAMESPACE_URL, uuid4, uuid5

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun, EvaluatorVersion


SEMANTIC_HOLDOUT_VERSION = "semantic_holdout_v1"
SEMANTIC_HOLDOUT_CASE_IDS = tuple(f"sealed_semantic_{number:02d}" for number in range(1, 21))
_HASH = re.compile(r"^[0-9a-f]{64}$")
_JUDGE_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class SemanticHoldoutError(ValueError):
    """A sealed receipt cannot be trusted or compared safely."""


def semantic_holdout_case_set_sha256() -> str:
    """Stable identity of the opaque 20-case holdout, never its content."""
    return sha256("\n".join(SEMANTIC_HOLDOUT_CASE_IDS).encode("utf-8")).hexdigest()


def semantic_holdout_definition_sha256() -> str:
    material = (
        f"{SEMANTIC_HOLDOUT_VERSION}\n"
        f"{semantic_holdout_case_set_sha256()}\n"
        "signed_aggregate_receipt_only\n"
        "no_prompts_outputs_rationales_or_per_case_results"
    )
    return sha256(material.encode("utf-8")).hexdigest()


def semantic_holdout_evaluator() -> EvaluatorVersion:
    """Register the gate as shadow-only until an independent receipt exists."""
    definition = semantic_holdout_definition_sha256()
    return EvaluatorVersion(
        evaluator_id=str(uuid5(NAMESPACE_URL, f"neurolab/response_quality/{SEMANTIC_HOLDOUT_VERSION}/{definition}")),
        kind="response_quality",
        version=SEMANTIC_HOLDOUT_VERSION,
        proposed_by="semantic_holdout_policy",
        definition_sha256=definition,
        frozen_case_ids=SEMANTIC_HOLDOUT_CASE_IDS,
        active_case_ids=SEMANTIC_HOLDOUT_CASE_IDS,
        state="shadow",
    )


@dataclass(frozen=True)
class SignedSemanticHoldoutReceipt:
    """Bounded aggregate from a sealed evaluator; no model text can fit here."""

    judge_id: str
    judge_model_sha256: str
    candidate_artifact_sha256: str
    candidate_model_sha256: str
    case_set_sha256: str
    evaluated_case_count: int
    primary_quality: float
    safety_quality: float
    calibration_quality: float
    signature_sha256: str

    def __post_init__(self) -> None:
        if not _JUDGE_ID.fullmatch(self.judge_id):
            raise SemanticHoldoutError("judge identifier is malformed")
        if any(
            not _HASH.fullmatch(value)
            for value in (
                self.judge_model_sha256,
                self.candidate_artifact_sha256,
                self.candidate_model_sha256,
                self.case_set_sha256,
                self.signature_sha256,
            )
        ):
            raise SemanticHoldoutError("receipt hash is malformed")
        if self.case_set_sha256 != semantic_holdout_case_set_sha256():
            raise SemanticHoldoutError("receipt does not use the sealed semantic holdout")
        if self.evaluated_case_count != len(SEMANTIC_HOLDOUT_CASE_IDS):
            raise SemanticHoldoutError("receipt must cover every sealed semantic case")
        if self.judge_model_sha256 == self.candidate_model_sha256:
            raise SemanticHoldoutError("judge model must be distinct from candidate model")
        if any(
            not 0.0 <= metric <= 1.0
            for metric in (self.primary_quality, self.safety_quality, self.calibration_quality)
        ):
            raise SemanticHoldoutError("receipt metrics are malformed")

    def unsigned_payload(self) -> dict[str, object]:
        return {
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "candidate_model_sha256": self.candidate_model_sha256,
            "calibration_quality": self.calibration_quality,
            "case_set_sha256": self.case_set_sha256,
            "evaluated_case_count": self.evaluated_case_count,
            "judge_id": self.judge_id,
            "judge_model_sha256": self.judge_model_sha256,
            "primary_quality": self.primary_quality,
            "safety_quality": self.safety_quality,
        }

    @classmethod
    def from_json(cls, raw: str) -> "SignedSemanticHoldoutReceipt":
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SemanticHoldoutError("receipt is not JSON") from error
        expected = {
            "judge_id", "judge_model_sha256", "candidate_artifact_sha256",
            "candidate_model_sha256", "case_set_sha256", "evaluated_case_count",
            "primary_quality", "safety_quality", "calibration_quality", "signature_sha256",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise SemanticHoldoutError("receipt fields are not allowlisted")
        try:
            return cls(
                judge_id=str(value["judge_id"]),
                judge_model_sha256=str(value["judge_model_sha256"]),
                candidate_artifact_sha256=str(value["candidate_artifact_sha256"]),
                candidate_model_sha256=str(value["candidate_model_sha256"]),
                case_set_sha256=str(value["case_set_sha256"]),
                evaluated_case_count=int(value["evaluated_case_count"]),
                primary_quality=float(value["primary_quality"]),
                safety_quality=float(value["safety_quality"]),
                calibration_quality=float(value["calibration_quality"]),
                signature_sha256=str(value["signature_sha256"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SemanticHoldoutError("receipt fields are malformed") from error


def sign_semantic_holdout_payload(payload: dict[str, object], signing_key: str) -> str:
    """Produce the HMAC used by the isolated evaluator, never store its key."""
    if not signing_key:
        raise SemanticHoldoutError("sealed receipt signing key is required")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(signing_key.encode("utf-8"), canonical, "sha256").hexdigest()


def verified_semantic_holdout_run(
    receipt: SignedSemanticHoldoutReceipt,
    *,
    signing_key: str,
    expected_candidate_artifact_sha256: str,
    expected_candidate_model_sha256: str,
) -> EvaluationRun:
    """Verify a signature and return only aggregate metrics for persistence."""
    if receipt.candidate_artifact_sha256 != expected_candidate_artifact_sha256:
        raise SemanticHoldoutError("receipt candidate artifact does not match the evaluated asset")
    if receipt.candidate_model_sha256 != expected_candidate_model_sha256:
        raise SemanticHoldoutError("receipt candidate model does not match the evaluated model")
    expected_signature = sign_semantic_holdout_payload(receipt.unsigned_payload(), signing_key)
    if not hmac.compare_digest(receipt.signature_sha256, expected_signature):
        raise SemanticHoldoutError("receipt signature is invalid")
    evaluator = semantic_holdout_evaluator()
    return EvaluationRun(
        run_id=str(uuid4()),
        evaluator_id=evaluator.evaluator_id,
        cohort_sha256=receipt.case_set_sha256,
        assessor=receipt.judge_id,
        assessor_role="independent_evaluator",
        metrics=EvaluationMetrics(
            primary_quality=receipt.primary_quality,
            safety_quality=receipt.safety_quality,
            calibration_quality=receipt.calibration_quality,
            cost_efficiency=1.0,
            evaluated_case_count=receipt.evaluated_case_count,
        ),
    )
