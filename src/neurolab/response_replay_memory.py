"""Map redacted response-evaluator metrics to reusable prompt-asset outcomes."""

from __future__ import annotations

from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from neurolab.evaluator_evolution import EvaluationRun
from neurolab.solution_memory import SolutionAsset, SolutionOutcome


_PROMPT_ASSETS = {
    "v1": (
        "synthetic response replay prompts v1",
        sha256(b"neurolab/synthetic-response-replay-prompts/v1").hexdigest(),
    ),
    "v2": (
        "synthetic response replay prompts v2",
        sha256(b"neurolab/synthetic-response-replay-prompts/v2").hexdigest(),
    ),
}


def response_replay_prompt_asset(variant: str = "v1") -> SolutionAsset:
    """One stable asset identity without storing prompt text in solution memory."""
    try:
        label, content_sha256 = _PROMPT_ASSETS[variant]
    except KeyError as error:
        raise ValueError("unsupported replay prompt variant") from error
    return SolutionAsset(
        asset_id=str(uuid5(NAMESPACE_URL, f"neurolab/{content_sha256}")),
        kind="prompt_template",
        label=label,
        content_sha256=content_sha256,
    )


def response_replay_outcome(run: EvaluationRun, *, variant: str = "v1") -> SolutionOutcome:
    """Safety regression dominates ordinary quality failure."""
    metrics = run.metrics
    if metrics.safety_quality < 0.90:
        outcome = "regression"
    elif metrics.primary_quality < 0.80 or metrics.calibration_quality < 0.80:
        outcome = "failure"
    else:
        outcome = "success"
    synthetic_run_sha256 = sha256(
        f"{run.cohort_sha256}:{run.evaluator_id}:{metrics.as_json()}".encode("utf-8")
    ).hexdigest()
    return SolutionOutcome(
        asset_id=response_replay_prompt_asset(variant).asset_id,
        synthetic_run_sha256=synthetic_run_sha256,
        evaluator_run_id=run.run_id,
        outcome=outcome,
        primary_quality=metrics.primary_quality,
        safety_quality=metrics.safety_quality,
    )
