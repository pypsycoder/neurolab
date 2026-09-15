#!/usr/bin/env python3
"""Persist one exact arXiv metadata record for review-only evidence work."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path

from neurolab.it_research import ItResearchQuery, ItResearchRun, lookup_arxiv_identifier, run_to_json
from neurolab.research_corpus import evaluate_coverage, render_synthesis_status
from neurolab.research_storage import load_corpus_assessments, persist_run, record_synthesis_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "runtime" / "it-research"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arxiv-id", required=True, help="Exact modern arXiv identifier; URLs are forbidden.")
    parser.add_argument("--topic", required=True, help="Review-only topic; never include personal or clinical data.")
    parser.add_argument("--goal", required=True, help="Concrete goal for the Code-agent brief gate.")
    parser.add_argument("--persist", action="store_true", help="Store public metadata using DATABASE_URL only in this process.")
    arguments = parser.parse_args()

    item = lookup_arxiv_identifier(arguments.arxiv_id)
    run = ItResearchRun(
        query=ItResearchQuery(arguments.topic),
        checked_on=datetime.now(UTC).date().isoformat(),
        items=(item,),
        provider_errors=(),
        decision="review_required",
        audit=("targeted_arxiv_identifier_lookup", "public_metadata_only", "review_required"),
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata_path = OUTPUT_DIR / "latest-targeted-arxiv-record.json"
    metadata_path.write_text(run_to_json(run), encoding="utf-8")
    if not arguments.persist:
        print("review_required: metadata receipt written without persistence")
        return
    database_url = os.environ.get("DATABASE_URL", "")
    persist_run(database_url, run, artifact_ref="runtime/it-research/latest-targeted-arxiv-record.json")
    coverage = evaluate_coverage(load_corpus_assessments(database_url))
    task_path = OUTPUT_DIR / "latest-code-agent-task.md"
    task_path.write_text(render_synthesis_status(coverage, goal=arguments.goal), encoding="utf-8")
    record_synthesis_status(database_url, coverage, artifact_ref="runtime/it-research/latest-code-agent-task.md")
    print(f"{coverage.status}: targeted public metadata receipt persisted")


if __name__ == "__main__":
    main()
