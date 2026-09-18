#!/usr/bin/env python3
"""Persist a signed aggregate from the sealed semantic holdout, never its content."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.evaluator_storage import persist_evaluation_run, persist_evaluator_version
from neurolab.semantic_holdout_gate import (
    SignedSemanticHoldoutReceipt,
    semantic_holdout_evaluator,
    verified_semantic_holdout_run,
)


def _sha256_argument(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise argparse.ArgumentTypeError("must be a lower-case SHA-256 hash")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path, help="Signed aggregate JSON from the isolated evaluator.")
    parser.add_argument("--candidate-artifact-sha256", required=True, type=_sha256_argument)
    parser.add_argument("--candidate-model-sha256", required=True, type=_sha256_argument)
    parser.add_argument("--persist", action="store_true", help="Persist only verified aggregate metrics through DATABASE_URL.")
    arguments = parser.parse_args()

    if not arguments.receipt.is_file() or arguments.receipt.stat().st_size > 8192:
        raise RuntimeError("sealed receipt input is unavailable or exceeds the boundary")
    signing_key = os.environ.get("SEMANTIC_HOLDOUT_RECEIPT_KEY", "")
    receipt = SignedSemanticHoldoutReceipt.from_json(arguments.receipt.read_text(encoding="utf-8"))
    run = verified_semantic_holdout_run(
        receipt,
        signing_key=signing_key,
        expected_candidate_artifact_sha256=arguments.candidate_artifact_sha256,
        expected_candidate_model_sha256=arguments.candidate_model_sha256,
    )
    evaluator = semantic_holdout_evaluator()
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_evaluator_version(database_url, evaluator)
        persisted_run_id = persist_evaluation_run(database_url, run)
        if persisted_run_id != run.run_id:
            raise RuntimeError("semantic holdout run receipt identity changed")
    print(json.dumps({
        "mode": "shadow",
        "evaluator_kind": evaluator.kind,
        "version": evaluator.version,
        "definition_sha256": evaluator.definition_sha256,
        "cohort_sha256": run.cohort_sha256,
        "metrics": json.loads(run.metrics.as_json()),
        "assessor": run.assessor,
        "persisted": arguments.persist,
        "scope": "signed_aggregate_receipt_only",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
