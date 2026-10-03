#!/usr/bin/env python3
"""Compare a redacted analysis receipt with the exact stored card and PDF identity."""
import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from neurolab.document_analysis_assessment import assess_document_analysis, assess_numeric_anchors
from neurolab.document_cards import parse_document_card
from neurolab.fulltext_verification import OpenAccessPdfRequest, extract_open_access_pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "runtime" / "it-research"
    path = root / f"document-receipt-{args.run_id}.json"
    if path.is_symlink() or path.stat().st_size > 60000:
        raise ValueError("receipt boundary invalid")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt["run_id"] != str(args.run_id):
        raise ValueError("receipt identity mismatch")
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as connection:
        row = connection.execute("""SELECT c.card,c.card_sha256,c.source_key,c.document_id::text,
            d.pdf_sha256,d.page_count,d.document_url,d.license_id FROM it_research.document_cards c JOIN it_research.documents d
            ON d.id=c.document_id AND d.source_key=c.source_key WHERE c.id=%s""",
            (UUID(receipt["card_id"]),)).fetchone()
    if row is None:
        raise ValueError("stored card missing")
    value = dict(row["card"])
    for field in ("source_key", "document_id", "document_sha256", "reviewer_status", "card_version"):
        value.pop(field, None)
    card = parse_document_card(json.dumps(value), source_key=row["source_key"], document_id=row["document_id"],
                               document_sha256=row["pdf_sha256"], page_count=row["page_count"])
    if card.card_sha256 != row["card_sha256"]:
        raise ValueError("stored card digest mismatch")
    assessment = assess_document_analysis(card, receipt, page_count=row["page_count"], pdf_sha256=row["pdf_sha256"])
    request = OpenAccessPdfRequest(row["source_key"], row["document_url"].rsplit("/", 1)[-1], row["license_id"])
    if request.url != row["document_url"]:
        raise ValueError("numeric grounding route mismatch")
    document, texts = extract_open_access_pdf(request)
    if document.sha256 != row["pdf_sha256"] or document.page_count != row["page_count"]:
        raise ValueError("grounding document digest mismatch")
    assessment.update(assess_numeric_anchors(card, texts))
    if assessment["failed_numeric_anchor_cases"]:
        assessment["decision"] = "repair_analysis_contract"
    output = root / f"document-assessment-{args.run_id}.json"
    if output.is_symlink():
        raise ValueError("assessment boundary invalid")
    output.write_text(json.dumps(assessment, sort_keys=True) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps(assessment, sort_keys=True))
    if not assessment["structure_passed"] or assessment["failed_numeric_anchor_cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("document_assessment_failed: integrity_storage_or_contract_failure") from None
