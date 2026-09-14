#!/usr/bin/env python3
"""Run public IT research on RP5 and write review-only local artifacts."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

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
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_run(database_url, run, artifact_ref="runtime/it-research/latest-research.json")
        coverage = evaluate_coverage(load_corpus_assessments(database_url))
    else:
        coverage = evaluate_coverage(classify_item(item) for item in run.items)
    (OUTPUT_DIR / "latest-code-agent-task.md").write_text(
        render_synthesis_status(coverage, goal=arguments.goal), encoding="utf-8"
    )
    if arguments.persist:
        record_synthesis_status(database_url, coverage, artifact_ref="runtime/it-research/latest-code-agent-task.md")
    print(f"{coverage.status}: {len(run.items)} public records -> {OUTPUT_DIR / 'latest-code-agent-task.md'}")


if __name__ == "__main__":
    main()
