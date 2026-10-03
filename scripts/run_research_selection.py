#!/usr/bin/env python3
"""Reassess public corpus relevance; bounded metadata/PDF I/O, zero LLM calls."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from neurolab.document_cards import parse_document_card
from neurolab.fulltext_verification import OpenAccessPdfRequest, extract_open_access_pdf
from neurolab.it_research import ItResearchError, ItResearchQuery, ItResearchRun, lookup_arxiv_identifier
from neurolab.research_selection import MISSIONS, VERSION, assess_content, screen_metadata
from neurolab.research_storage import load_corpus_assessments, persist_run
from neurolab.selection_storage import load_metadata_selections, persist_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key")
    parser.add_argument("--limit", type=int, choices=range(1, 7), default=2)
    parser.add_argument("--refresh-metadata", action="store_true")
    parser.add_argument("--assess-content", action="store_true")
    args = parser.parse_args()
    if args.source_key and not re.fullmatch(r"[0-9a-f]{64}", args.source_key):
        raise ValueError("invalid source identity")
    database_url = os.environ["DATABASE_URL"]
    unique = {}
    for assessment in load_corpus_assessments(database_url):
        if assessment.source_key not in unique or assessment.item.provider == "arxiv":
            unique[assessment.source_key] = assessment
    sources = sorted(unique.values(), key=lambda a: a.source_key)
    if args.source_key:
        if args.source_key not in unique:
            raise ValueError("source absent from corpus")
        sources = [unique[args.source_key]]
    run_id, receipts, failures = str(uuid4()), [], []
    for assessment in sources[:args.limit]:
        if args.assess_content and not args.refresh_metadata:
            # Corpus deliberately stores no abstract. A content-only replay
            # must use the existing hash-validated metadata verdict, not
            # replace it with a false "missing abstract" assessment.
            continue
        item = assessment.item
        current = [screen_metadata(item, m.mission_id, source_key=assessment.source_key) for m in MISSIONS]
        # An explicitly unrelated title costs no network/model calls.
        if args.refresh_metadata and any(r.decision != "reject" for r in current) and item.provider == "arxiv":
            try:
                fresh = lookup_arxiv_identifier(item.provider_id)
                if fresh.provider_id != item.provider_id:
                    raise ItResearchError("exact source version changed")
                item = replace(fresh, url=item.url, doi=item.doi)
                persist_run(database_url, ItResearchRun(ItResearchQuery("bounded exact metadata refresh", 2),
                    item.checked_on, (item,), (), "review_required", ()), artifact_ref=f"runtime/it-research/selection-{run_id}.json")
                current = [screen_metadata(item, m.mission_id, source_key=assessment.source_key) for m in MISSIONS]
            except ItResearchError:
                failures.append({"source_key": assessment.source_key, "code": "metadata_unavailable"})
                # Do not overwrite a previous admitted receipt with absence
                # of a transient network response. Existing verdict stays.
                continue
        for receipt in current:
            persist_selection(database_url, receipt)
            receipts.append(receipt.model_dump(mode="json"))
    if args.assess_content:
        metadata = load_metadata_selections(database_url)
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            rows = connection.execute("""SELECT c.card,c.card_sha256,c.source_key,c.document_id::text,
                d.document_url,d.license_id,d.pdf_sha256,d.page_count
                FROM it_research.document_cards c JOIN it_research.documents d ON d.id=c.document_id
                WHERE d.provider='arxiv' AND c.reviewer_status IN ('needs_review','reviewed')
                ORDER BY c.generated_at DESC LIMIT 12""").fetchall()
        allowed = {a.source_key for a in sources[:args.limit]}
        for row in rows:
            selections = [m for m in metadata if m.source_key == row["source_key"] and m.source_key in allowed]
            if not selections:
                continue
            body = dict(row["card"])
            for key in ("source_key", "document_id", "document_sha256", "reviewer_status", "card_version"):
                body.pop(key, None)
            card = parse_document_card(json.dumps(body), source_key=row["source_key"], document_id=row["document_id"],
                                       document_sha256=row["pdf_sha256"], page_count=row["page_count"])
            if card.card_sha256 != row["card_sha256"]:
                raise ValueError("stored card digest changed")
            request = OpenAccessPdfRequest(row["source_key"], row["document_url"].rsplit("/", 1)[-1], row["license_id"])
            if request.url != row["document_url"]:
                raise ValueError("fixed PDF route mismatch")
            document, pages = extract_open_access_pdf(request)
            if document.sha256 != row["pdf_sha256"] or document.page_count != row["page_count"]:
                raise ValueError("exact PDF changed")
            for selection in selections:
                receipt = assess_content(card, selection, pages)
                persist_selection(database_url, receipt)
                receipts.append(receipt.model_dump(mode="json"))
    result = {"run_id": run_id, "policy_version": VERSION, "receipts": receipts, "failures": failures,
              "new_model_calls": 0, "full_spec_allowed": False, "semantic_verification": "not_performed"}
    root = Path(__file__).resolve().parents[1] / "runtime/it-research"
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"selection-{run_id}.json"
    output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("research_selection_failed: integrity_storage_or_contract_failure") from None
