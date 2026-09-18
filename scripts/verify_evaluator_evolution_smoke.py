#!/usr/bin/env python3
"""Run one synthetic-only evaluator-promotion and solution-memory smoke."""

from __future__ import annotations

from hashlib import sha256
import os
from uuid import uuid4

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun, EvaluatorVersion, decide_evaluator_transition
from neurolab.evaluator_storage import (
    persist_evaluation_run,
    persist_evaluator_decision,
    persist_evaluator_version,
    persist_solution_asset,
    persist_solution_outcomes,
)
from neurolab.solution_memory import SolutionAsset, SolutionOutcome


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "")
    suffix = uuid4().hex[:12]
    frozen = ("synthetic_case_a", "synthetic_case_b")
    baseline = EvaluatorVersion(str(uuid4()), "article_scoring", f"v_base_{suffix}", "author_agent", digest("baseline" + suffix), frozen, frozen, "promoted")
    candidate = EvaluatorVersion(str(uuid4()), "article_scoring", f"v_candidate_{suffix}", "author_agent", digest("candidate" + suffix), frozen, frozen + ("synthetic_case_c",), "shadow", baseline.evaluator_id)
    persist_evaluator_version(database_url, baseline)
    persist_evaluator_version(database_url, candidate)
    cohort = digest("synthetic-holdout-" + suffix)
    baseline_run = EvaluationRun(str(uuid4()), baseline.evaluator_id, cohort, "baseline_evaluator", "independent_evaluator", EvaluationMetrics(.80, .95, .80, .70, 24))
    candidate_run = EvaluationRun(str(uuid4()), candidate.evaluator_id, cohort, "independent_evaluator", "independent_evaluator", EvaluationMetrics(.84, .95, .83, .70, 24))
    persist_evaluation_run(database_url, baseline_run)
    persist_evaluation_run(database_url, candidate_run)
    decision = decide_evaluator_transition(baseline, candidate, baseline_run, candidate_run)
    if decision.decision != "promoted":
        raise RuntimeError("synthetic evaluator candidate was not promoted")
    persist_evaluator_decision(database_url, decision)
    asset = SolutionAsset(str(uuid4()), "workflow_scheme", "synthetic evaluator workflow", digest("asset" + suffix))
    persist_solution_asset(database_url, asset)
    outcomes = tuple(SolutionOutcome(asset.asset_id, digest(f"run-{suffix}-{index}"), candidate_run.run_id, "success", .85, .95) for index in range(3))
    persist_solution_outcomes(database_url, asset, outcomes)
    print("evaluator_evolution_smoke: promoted")


if __name__ == "__main__":
    main()
