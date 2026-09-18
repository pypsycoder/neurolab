#!/usr/bin/env python3
"""Evaluate four synthetic GigaChat responses with the deterministic v1 suite."""

from __future__ import annotations

import argparse
import json
import os

from neurolab.evaluator_storage import (
    persist_evaluation_run,
    persist_evaluator_version,
    persist_response_replay_diagnostics,
    persist_solution_asset,
    persist_solution_outcomes,
)
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.gigachat_response_replay import request_synthetic_replay
from neurolab.response_replay_memory import response_replay_outcome, response_replay_prompt_asset
from neurolab.response_replay_diagnostics import diagnostic_summary, diagnose_response_quality
from neurolab.response_quality_evaluator import evaluate_response_quality, response_quality_shadow_evaluator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", action="store_true", help="Store only redacted aggregate metrics through DATABASE_URL.")
    parser.add_argument("--variant", choices=("v1", "v2"), default="v1", help="Fixed synthetic prompt variant to replay.")
    arguments = parser.parse_args()

    settings = GigaChatSettings.from_environment()
    with GigaChatClientFactory().create(settings) as client:
        responses = request_synthetic_replay(client, variant=arguments.variant)
    evaluator = response_quality_shadow_evaluator()
    run = evaluate_response_quality(responses, assessor="deterministic_contract_evaluator")
    diagnostics = diagnose_response_quality(responses)
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_evaluator_version(database_url, evaluator)
        evaluator_run_id = persist_evaluation_run(database_url, run)
        if evaluator_run_id != run.run_id:
            raise RuntimeError("evaluator run receipt identity changed")
        persist_response_replay_diagnostics(database_url, run, diagnostics)
        asset = response_replay_prompt_asset(arguments.variant)
        persist_solution_asset(database_url, asset)
        persist_solution_outcomes(database_url, asset, (response_replay_outcome(run, variant=arguments.variant),))
    receipt = {
        "mode": "shadow",
        "prompt_variant": arguments.variant,
        "evaluator_kind": evaluator.kind,
        "version": evaluator.version,
        "definition_sha256": evaluator.definition_sha256,
        "cohort_sha256": run.cohort_sha256,
        "metrics": json.loads(run.metrics.as_json()),
        "model_calls": len(responses),
        "persisted": arguments.persist,
        "diagnostic_summary": diagnostic_summary(diagnostics),
        "solution_memory_outcome": response_replay_outcome(run, variant=arguments.variant).outcome,
        "scope": "live_model_over_synthetic_prompts_only",
    }
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
