#!/usr/bin/env python3
"""Run the metadata article-scorer contract in shadow mode.

No research records, titles, model prompts, or outputs are written to the
database.  ``--persist`` stores only hashes, version metadata, and aggregates.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.article_scoring_evaluator import article_scorer_baseline, evaluate_article_scorer
from neurolab.evaluator_storage import persist_evaluation_run, persist_evaluator_version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persist", action="store_true", help="Write redacted aggregate receipt through DATABASE_URL.")
    arguments = parser.parse_args()
    baseline = article_scorer_baseline()
    run = evaluate_article_scorer()
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_evaluator_version(database_url, baseline)
        persist_evaluation_run(database_url, run)
    receipt = {
        "mode": "shadow",
        "evaluator_kind": baseline.kind,
        "version": baseline.version,
        "definition_sha256": baseline.definition_sha256,
        "cohort_sha256": run.cohort_sha256,
        "metrics": json.loads(run.metrics.as_json()),
        "persisted": arguments.persist,
        "scope": "classifier_contract_only",
    }
    # The research image has a read-only application root.  Operators may bind
    # a durable redacted-receipt directory explicitly; otherwise this file is
    # an ephemeral convenience copy and PostgreSQL is the durable receipt.
    output = Path(os.environ.get("NEUROLAB_EVALUATOR_RECEIPT_DIR", "/tmp/neurolab-evaluator-runs"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "latest-article-scorer-shadow.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
