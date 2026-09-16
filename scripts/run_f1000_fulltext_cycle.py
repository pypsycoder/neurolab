#!/usr/bin/env python3
"""Verify F1000 CC-BY HTML licence then retrieve its bounded PDF receipt."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from neurolab.publisher_evidence import F1000ArticleRequest, verify_f1000_article
from neurolab.publisher_fulltext_verification import F1000OpenAccessPdfRequest, verify_f1000_open_access_pdf
from neurolab.research_storage import persist_fulltext_receipt, persist_publisher_html_receipt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-f1000-fulltext-cycle.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True, help="Existing 64-character corpus source key.")
    parser.add_argument("--article-id", required=True, help="F1000 volume-article identifier; URLs are forbidden.")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--persist", action="store_true", help="Store receipts in PostgreSQL using DATABASE_URL only in this process.")
    arguments = parser.parse_args()

    evidence = verify_f1000_article(
        F1000ArticleRequest(arguments.source_key, arguments.article_id, arguments.version),
        checked_on=datetime.now(UTC).date().isoformat(),
    )
    document = verify_f1000_open_access_pdf(
        F1000OpenAccessPdfRequest(arguments.source_key, arguments.article_id, arguments.version, evidence.receipt.license_id)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"publisher_receipt": asdict(evidence.receipt), "document_receipt": asdict(document)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_publisher_html_receipt(database_url, evidence.receipt)
        persist_fulltext_receipt(database_url, document)
    print(f"verified_open_access: {document.page_count} pages; F1000 receipts written")


if __name__ == "__main__":
    main()
