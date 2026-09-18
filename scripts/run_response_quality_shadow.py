#!/usr/bin/env python3
"""Run synthetic response-quality fixtures in shadow mode only."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.evaluator_storage import persist_evaluation_run, persist_evaluator_version
from neurolab.response_quality_evaluator import (
    evaluate_response_quality,
    response_quality_fixture_responses,
    response_quality_shadow_evaluator,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", action="store_true", help="Write redacted aggregate receipt through DATABASE_URL.")
    arguments = parser.parse_args()
    evaluator = response_quality_shadow_evaluator()
    run = evaluate_response_quality(response_quality_fixture_responses())
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_evaluator_version(database_url, evaluator)
        persist_evaluation_run(database_url, run)
    receipt = {
        "mode": "shadow",
        "evaluator_kind": evaluator.kind,
        "version": evaluator.version,
        "definition_sha256": evaluator.definition_sha256,
        "cohort_sha256": run.cohort_sha256,
        "metrics": json.loads(run.metrics.as_json()),
        "persisted": arguments.persist,
        "scope": "synthetic_fixture_contract_only",
    }
    # The research image has a read-only application root.  Operators may bind
    # a durable redacted-receipt directory explicitly; otherwise this file is
    # an ephemeral convenience copy and PostgreSQL is the durable receipt.
    output = Path(os.environ.get("NEUROLAB_EVALUATOR_RECEIPT_DIR", "/tmp/neurolab-evaluator-runs"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-response-quality-shadow.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
