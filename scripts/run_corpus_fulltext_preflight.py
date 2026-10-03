#!/usr/bin/env python3
"""Consume one corpus gap PDF candidate through the existing legal-first route."""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg

from neurolab.corpus_gap_plan import VERSION, plan_corpus_gaps
from neurolab.fulltext_verification import OpenAccessPdfRequest, FullTextVerificationError, verify_open_access_pdf
from neurolab.license_verification import ArxivLicenseRequest, LicenseVerificationError, verify_arxiv_license
from neurolab.research_storage import load_corpus_assessments, persist_fulltext_receipt, persist_license_receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        searched = tuple(row[0] for row in connection.execute(
            "SELECT template_id FROM it_research.corpus_gap_rounds WHERE policy_version=%s", (VERSION,)))
        documents = frozenset(row[0] for row in connection.execute(
            "SELECT DISTINCT source_key FROM it_research.documents"))
        attempted = frozenset(row[0] for row in connection.execute(
            "SELECT source_key FROM it_research.corpus_fulltext_attempts WHERE policy_version=%s", (VERSION,)))
    plan = plan_corpus_gaps(load_corpus_assessments(database_url), attempted_templates=searched,
                           document_source_keys=documents, attempted_fulltext_source_keys=attempted)
    candidate = next(iter(plan["fulltext_candidates"]), None)
    run_id = str(uuid4())
    receipt = {"run_id": run_id, "policy_version": VERSION, "status": "planned",
               "checked_at": datetime.now(UTC).isoformat(), "corpus_sha256": plan["corpus_sha256"],
               "candidate": candidate, "new_model_calls": 0, "full_spec_allowed": False}
    if args.execute and candidate:
        receipt["status"] = "inflight"
        with psycopg.connect(database_url) as connection:
            reserved = connection.execute("""INSERT INTO it_research.corpus_fulltext_attempts
                (run_id,policy_version,source_key,status,receipt) VALUES (%s,%s,%s,'inflight',%s::jsonb)
                ON CONFLICT (policy_version,source_key) DO NOTHING RETURNING run_id""",
                (run_id, VERSION, candidate["source_key"], json.dumps(receipt))).fetchone()
        if not reserved:
            raise RuntimeError("fulltext reservation already taken")
        try:
            licence = verify_arxiv_license(ArxivLicenseRequest(candidate["source_key"], candidate["arxiv_id"]),
                                           checked_on=datetime.now(UTC).date().isoformat())
        except LicenseVerificationError:
            # May mean unavailable transport OR incompatible licence. Never
            # invent permission or label every transport failure a copyright ban.
            receipt.update(status="license_unverified", next_action="retain_metadata_no_pdf_download")
        else:
            persist_license_receipt(database_url, licence)
            try:
                document = verify_open_access_pdf(OpenAccessPdfRequest(
                    candidate["source_key"], candidate["arxiv_id"], licence.license_id))
            except FullTextVerificationError:
                receipt.update(status="document_unverified", next_action="retain_license_receipt_no_model_analysis")
            else:
                document_id = persist_fulltext_receipt(database_url, document)
                receipt.update(status="completed", license_id=licence.license_id, document_id=document_id,
                               pdf_sha256=document.sha256, page_count=document.page_count,
                               next_action="bounded_document_card_analysis")
        with psycopg.connect(database_url) as connection:
            connection.execute("""UPDATE it_research.corpus_fulltext_attempts
                SET status=%s,receipt=%s::jsonb,completed_at=now() WHERE run_id=%s AND status='inflight'""",
                (receipt["status"], json.dumps(receipt), run_id))
    elif not candidate:
        receipt.update(status="queue_exhausted", next_action="refine_discovery_or_legal_ingestion_route")
    output = Path(__file__).resolve().parents[1] / "runtime" / "it-research"
    output.mkdir(parents=True, exist_ok=True)
    data = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    (output / f"corpus-fulltext-{run_id}.json").write_text(data, encoding="utf-8")
    (output / "latest-corpus-fulltext.json").write_text(data, encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("corpus_fulltext_failed: integrity_storage_or_reservation_failure") from None
