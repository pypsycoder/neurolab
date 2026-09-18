#!/usr/bin/env python3
"""Run public IT research on RP5 and write review-only local artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.corpus_spec_observer import observe_corpus_to_spec
from neurolab.evaluator_storage import load_evaluator_receipt
from neurolab.it_research import ItResearchQuery, run_it_research, run_to_json
from neurolab.research_corpus import classify_item, evaluate_coverage, render_synthesis_status
from neurolab.research_storage import load_corpus_assessments, persist_run, record_synthesis_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "runtime" / "it-research"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="Public IT research topic; never include personal or clinical data.")
    parser.add_argument("--goal", required=True, help="Concrete development goal for the Code-agent brief.")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--persist", action="store_true", help="Store public metadata in PostgreSQL using DATABASE_URL from this process only.")
    arguments = parser.parse_args()

    query = ItResearchQuery(arguments.topic, arguments.max_results)
    run = run_it_research(
        query,
        api_key=os.environ.get("OPENALEX_API_KEY"),
        mailto=os.environ.get("CROSSREF_MAILTO"),
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "latest-research.json").write_text(run_to_json(run), encoding="utf-8")
    observation = None
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_run(database_url, run, artifact_ref="runtime/it-research/latest-research.json")
        coverage = evaluate_coverage(load_corpus_assessments(database_url))
        observation = observe_corpus_to_spec(
            coverage,
            article_scorer=load_evaluator_receipt(database_url, kind="article_scoring", version="metadata_title_v1"),
            response_quality=load_evaluator_receipt(database_url, kind="response_quality", version="response_contract_v1"),
        )
    else:
        coverage = evaluate_coverage(classify_item(item) for item in run.items)
    (OUTPUT_DIR / "latest-code-agent-task.md").write_text(
        render_synthesis_status(coverage, goal=arguments.goal), encoding="utf-8"
    )
    if arguments.persist:
        record_synthesis_status(
            database_url,
            coverage,
            artifact_ref="runtime/it-research/latest-code-agent-task.md",
            evaluator_observation=observation.as_snapshot(),
        )
        (OUTPUT_DIR / "latest-evaluator-observation.json").write_text(
            json.dumps(observation.as_snapshot(), indent=2) + "\n", encoding="utf-8"
        )
    decision = observation.decision if observation is not None else "not_persisted"
    print(f"{coverage.status}/{decision}: {len(run.items)} public records -> {OUTPUT_DIR / 'latest-code-agent-task.md'}")


if __name__ == "__main__":
    main()
