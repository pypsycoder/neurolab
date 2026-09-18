"""Versioned, independently evaluated evolution of research evaluators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Literal
from uuid import UUID, uuid4


EvaluatorKind = Literal["article_scoring", "response_quality"]
EvaluatorState = Literal["proposed", "shadow", "promoted", "reverted"]
AssessorRole = Literal["author", "independent_evaluator"]
Decision = Literal["shadow", "promoted", "reverted"]

_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_MINIMUM_HOLDOUT_CASES = 20
_PRIMARY_IMPROVEMENT = 0.02


class EvaluatorEvolutionError(ValueError):
    """An evaluator change breaks a non-negotiable autonomous-loop rule."""


def _is_uuid(value: str | None) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class EvaluatorVersion:
    """A redacted evaluator definition; test content is intentionally absent."""

    evaluator_id: str
    kind: EvaluatorKind
    version: str
    proposed_by: str
    definition_sha256: str
    frozen_case_ids: tuple[str, ...]
    active_case_ids: tuple[str, ...]
    state: EvaluatorState = "proposed"
    parent_evaluator_id: str | None = None

    def __post_init__(self) -> None:
        if not _is_uuid(self.evaluator_id) or (self.parent_evaluator_id is not None and not _is_uuid(self.parent_evaluator_id)):
            raise EvaluatorEvolutionError("evaluator identifier is malformed")
        if self.kind not in {"article_scoring", "response_quality"} or self.state not in {"proposed", "shadow", "promoted", "reverted"}:
            raise EvaluatorEvolutionError("evaluator kind or state is malformed")
        if not _ID.fullmatch(self.version) or not _ID.fullmatch(self.proposed_by) or not _HASH.fullmatch(self.definition_sha256):
            raise EvaluatorEvolutionError("evaluator metadata is malformed")
        if not self.frozen_case_ids or len(set(self.frozen_case_ids)) != len(self.frozen_case_ids) or len(set(self.active_case_ids)) != len(self.active_case_ids):
            raise EvaluatorEvolutionError("evaluator case IDs are malformed")
        if any(not _ID.fullmatch(case_id) for case_id in self.frozen_case_ids + self.active_case_ids):
            raise EvaluatorEvolutionError("evaluator case ID is malformed")
        if not set(self.frozen_case_ids).issubset(self.active_case_ids):
            raise EvaluatorEvolutionError("frozen cases cannot be removed")

    @property
    def frozen_case_set_sha256(self) -> str:
        return sha256("\n".join(sorted(self.frozen_case_ids)).encode()).hexdigest()

    @property
    def active_case_set_sha256(self) -> str:
        return sha256("\n".join(sorted(self.active_case_ids)).encode()).hexdigest()


@dataclass(frozen=True)
class EvaluationMetrics:
    """Comparable holdout metrics, without test inputs or model outputs."""

    primary_quality: float
    safety_quality: float
    calibration_quality: float
    cost_efficiency: float
    evaluated_case_count: int

    def __post_init__(self) -> None:
        if self.evaluated_case_count < 1 or any(not 0.0 <= metric <= 1.0 for metric in (self.primary_quality, self.safety_quality, self.calibration_quality, self.cost_efficiency)):
            raise EvaluatorEvolutionError("evaluation metrics are malformed")

    def as_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    evaluator_id: str
    cohort_sha256: str
    assessor: str
    assessor_role: AssessorRole
    metrics: EvaluationMetrics

    def __post_init__(self) -> None:
        if not _is_uuid(self.run_id) or not _is_uuid(self.evaluator_id) or not _HASH.fullmatch(self.cohort_sha256):
            raise EvaluatorEvolutionError("evaluation run identity is malformed")
        if not _ID.fullmatch(self.assessor) or self.assessor_role not in {"author", "independent_evaluator"}:
            raise EvaluatorEvolutionError("evaluation assessor is malformed")


@dataclass(frozen=True)
class EvaluatorDecision:
    decision_id: str
    baseline_evaluator_id: str
    candidate_evaluator_id: str
    baseline_run_id: str
    candidate_run_id: str
    decision: Decision
    reason_codes: tuple[str, ...]
    policy_version: str = "evaluator-evolution-v1"

    def __post_init__(self) -> None:
        if any(not _is_uuid(value) for value in (self.decision_id, self.baseline_evaluator_id, self.candidate_evaluator_id, self.baseline_run_id, self.candidate_run_id)):
            raise EvaluatorEvolutionError("decision identity is malformed")
        if self.decision not in {"shadow", "promoted", "reverted"} or not self.reason_codes or any(not _ID.fullmatch(code) for code in self.reason_codes):
            raise EvaluatorEvolutionError("decision metadata is malformed")


def decide_evaluator_transition(baseline: EvaluatorVersion, candidate: EvaluatorVersion, baseline_run: EvaluationRun, candidate_run: EvaluationRun) -> EvaluatorDecision:
    """Apply immutable gates before a candidate evaluator can be promoted."""
    if baseline.state != "promoted" or candidate.parent_evaluator_id != baseline.evaluator_id or candidate.kind != baseline.kind:
        raise EvaluatorEvolutionError("candidate must extend one promoted evaluator of the same kind")
    if baseline_run.evaluator_id != baseline.evaluator_id or candidate_run.evaluator_id != candidate.evaluator_id:
        raise EvaluatorEvolutionError("evaluation run is not linked to its evaluator")
    if baseline_run.cohort_sha256 != candidate_run.cohort_sha256:
        return _decision(baseline, candidate, baseline_run, candidate_run, "shadow", "cohort_not_comparable")
    if not set(baseline.frozen_case_ids).issubset(candidate.active_case_ids):
        return _decision(baseline, candidate, baseline_run, candidate_run, "reverted", "frozen_cases_missing")
    if candidate_run.assessor_role != "independent_evaluator" or candidate_run.assessor == candidate.proposed_by:
        return _decision(baseline, candidate, baseline_run, candidate_run, "shadow", "independent_evaluation_required")
    if min(baseline_run.metrics.evaluated_case_count, candidate_run.metrics.evaluated_case_count) < _MINIMUM_HOLDOUT_CASES:
        return _decision(baseline, candidate, baseline_run, candidate_run, "shadow", "holdout_too_small")
    if candidate_run.metrics.safety_quality < baseline_run.metrics.safety_quality:
        return _decision(baseline, candidate, baseline_run, candidate_run, "reverted", "safety_regression")
    if candidate_run.metrics.primary_quality < baseline_run.metrics.primary_quality:
        return _decision(baseline, candidate, baseline_run, candidate_run, "reverted", "primary_regression")
    if candidate_run.metrics.primary_quality < baseline_run.metrics.primary_quality + _PRIMARY_IMPROVEMENT:
        return _decision(baseline, candidate, baseline_run, candidate_run, "shadow", "improvement_not_yet_material")
    if candidate_run.metrics.calibration_quality < baseline_run.metrics.calibration_quality:
        return _decision(baseline, candidate, baseline_run, candidate_run, "shadow", "calibration_not_improved")
    return _decision(baseline, candidate, baseline_run, candidate_run, "promoted", "independent_holdout_improvement")


def _decision(baseline: EvaluatorVersion, candidate: EvaluatorVersion, baseline_run: EvaluationRun, candidate_run: EvaluationRun, decision: Decision, *reason_codes: str) -> EvaluatorDecision:
    return EvaluatorDecision(str(uuid4()), baseline.evaluator_id, candidate.evaluator_id, baseline_run.run_id, candidate_run.run_id, decision, tuple(reason_codes))
