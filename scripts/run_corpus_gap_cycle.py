#!/usr/bin/env python3
"""Plan corpus gaps or execute one reserved public search. Never invoke an LLM."""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg

from neurolab.research_selection import VERSION, MISSIONS, screen_metadata
from neurolab.selection_plan import plan_selected_corpus as plan_corpus_gaps
from neurolab.selection_storage import load_metadata_selections, persist_selection
from neurolab.it_research import ItResearchError, ItResearchQuery, run_it_research
from neurolab.research_storage import load_corpus_assessments, persist_run, record_synthesis_status
from neurolab.research_corpus import evaluate_coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        attempted = tuple(row[0] for row in connection.execute(
            "SELECT template_id FROM it_research.corpus_gap_rounds WHERE policy_version=%s", (VERSION,)))
        documents = frozenset(row[0] for row in connection.execute(
            "SELECT DISTINCT source_key FROM it_research.documents"))
        attempted_fulltext = frozenset(row[0] for row in connection.execute(
            "SELECT source_key FROM it_research.corpus_fulltext_attempts"))
    before = load_corpus_assessments(database_url)
    eligible = frozenset(r.source_key for r in load_metadata_selections(database_url))
    plan = plan_corpus_gaps(before, attempted_templates=attempted, document_source_keys=documents,
                           attempted_fulltext_source_keys=attempted_fulltext, eligible_source_keys=eligible)
    run_id = str(uuid4())
    receipt = {"run_id": run_id, "checked_at": datetime.now(UTC).isoformat(),
               "status": "planned", "before": plan, "new_model_calls": 0}
    if args.execute and plan["next_search"]:
        template = plan["next_search"]
        receipt["status"] = "inflight"
        # Reservation commits BEFORE any network request; parallel invocations
        # or a process crash cannot silently repeat this template.
        with psycopg.connect(database_url) as connection:
            reserved = connection.execute("""INSERT INTO it_research.corpus_gap_rounds
                (run_id,policy_version,template_id,status,receipt)
                VALUES (%s,%s,%s,'inflight',%s::jsonb)
                ON CONFLICT (policy_version,template_id) DO NOTHING RETURNING run_id""",
                (run_id, VERSION, template["template_id"], json.dumps(receipt))).fetchone()
        if not reserved:
            raise RuntimeError("search reservation already taken")
        try:
            run = run_it_research(ItResearchQuery(template["topic"], 2, template["arxiv_terms"]),
                                  api_key=os.environ.get("OPENALEX_API_KEY"),
                                  mailto=os.environ.get("CROSSREF_MAILTO"))
            persist_run(database_url, run, artifact_ref=f"runtime/it-research/corpus-gap-{run_id}.json")
            decisions = []
            for item in run.items:
                # Assess every existing trusted mission: discovery may find a
                # useful source for a different gap, but cannot invent a goal.
                for mission in MISSIONS:
                    selection = screen_metadata(item, mission.mission_id)
                    persist_selection(database_url, selection)
                    decisions.append(selection.decision)
            eligible = frozenset(r.source_key for r in load_metadata_selections(database_url))
            after = load_corpus_assessments(database_url)
            receipt.update(status="completed", public_record_count=len(run.items),
                           selection_decisions={d: decisions.count(d) for d in sorted(set(decisions))},
                           provider_errors=list(run.provider_errors),
                           new_unique_sources=max(0, evaluate_coverage(after).unique_source_count -
                                                  evaluate_coverage(before).unique_source_count),
                           after=plan_corpus_gaps(after, attempted_templates=attempted + (template["template_id"],),
                                                 document_source_keys=documents, attempted_fulltext_source_keys=attempted_fulltext,
                                                 eligible_source_keys=eligible))
            record_synthesis_status(database_url, evaluate_coverage(after),
                                    artifact_ref=f"runtime/it-research/corpus-gap-{run_id}.json")
        except ItResearchError:
            receipt.update(status="unavailable", failure_code="insufficient_public_provider_evidence",
                           public_record_count=0, new_unique_sources=0)
        # Other failures intentionally retain inflight: outcome is unknown and
        # no blind retry is permitted. Never persist raw exception/provider text.
        with psycopg.connect(database_url) as connection:
            connection.execute("""UPDATE it_research.corpus_gap_rounds
                SET status=%s,receipt=%s::jsonb,completed_at=now()
                WHERE run_id=%s AND status='inflight'""",
                (receipt["status"], json.dumps(receipt), run_id))
    output = Path(__file__).resolve().parents[1] / "runtime" / "it-research"
    output.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    (output / f"corpus-gap-{run_id}.json").write_text(data, encoding="utf-8")
    (output / "latest-corpus-gap.json").write_text(data, encoding="utf-8")
    current = receipt.get("after", plan)
    print(json.dumps({"run_id": run_id, "status": receipt["status"],
                      "unique_sources": current["coverage"]["unique_source_count"],
                      "new_unique_sources": receipt.get("new_unique_sources", 0),
                      "fulltext_candidates": len(current["fulltext_candidates"]),
                      "next_search": current["next_search"],
                      "blocking_gaps": current["blocking_gaps"],
                      "full_spec_allowed": False, "new_model_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("corpus_gap_failed: integrity_storage_or_reservation_failure") from None
