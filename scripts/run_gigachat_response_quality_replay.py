#!/usr/bin/env python3
"""Evaluate four synthetic GigaChat responses with the deterministic v1 suite."""

from __future__ import annotations

import argparse
import json
import os

from neurolab.evaluator_storage import (
    persist_evaluation_run,
    persist_evaluator_version,
    persist_solution_asset,
    persist_solution_outcomes,
)
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.gigachat_response_replay import request_synthetic_replay
from neurolab.response_replay_memory import response_replay_outcome, response_replay_prompt_asset
from neurolab.response_quality_evaluator import evaluate_response_quality, response_quality_shadow_evaluator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", action="store_true", help="Store only redacted aggregate metrics through DATABASE_URL.")
    arguments = parser.parse_args()

    settings = GigaChatSettings.from_environment()
    with GigaChatClientFactory().create(settings) as client:
        responses = request_synthetic_replay(client)
    evaluator = response_quality_shadow_evaluator()
    run = evaluate_response_quality(responses, assessor="deterministic_contract_evaluator")
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_evaluator_version(database_url, evaluator)
        evaluator_run_id = persist_evaluation_run(database_url, run)
        if evaluator_run_id != run.run_id:
            raise RuntimeError("evaluator run receipt identity changed")
        asset = response_replay_prompt_asset()
        persist_solution_asset(database_url, asset)
        persist_solution_outcomes(database_url, asset, (response_replay_outcome(run),))
    receipt = {
        "mode": "shadow",
        "evaluator_kind": evaluator.kind,
        "version": evaluator.version,
        "definition_sha256": evaluator.definition_sha256,
        "cohort_sha256": run.cohort_sha256,
        "metrics": json.loads(run.metrics.as_json()),
        "model_calls": len(responses),
        "persisted": arguments.persist,
        "solution_memory_outcome": response_replay_outcome(run).outcome,
        "scope": "live_model_over_synthetic_prompts_only",
    }
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
