#!/usr/bin/env python3
"""Run licence proof then bounded full-text receipt for one corpus arXiv source."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from neurolab.fulltext_verification import OpenAccessPdfRequest, verify_open_access_pdf
from neurolab.license_verification import ArxivLicenseRequest, verify_arxiv_license
from neurolab.research_storage import persist_fulltext_receipt, persist_license_receipt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-arxiv-fulltext-cycle.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True, help="Existing 64-character corpus source key.")
    parser.add_argument("--arxiv-id", required=True, help="Modern arXiv identifier; arbitrary URL input is forbidden.")
    parser.add_argument("--persist", action="store_true", help="Store receipts in PostgreSQL using DATABASE_URL only in this process.")
    arguments = parser.parse_args()

    checked_on = datetime.now(UTC).date().isoformat()
    licence = verify_arxiv_license(
        ArxivLicenseRequest(arguments.source_key, arguments.arxiv_id), checked_on=checked_on
    )
    document = verify_open_access_pdf(
        OpenAccessPdfRequest(arguments.source_key, arguments.arxiv_id, licence.license_id)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"licence": asdict(licence), "document": asdict(document)}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if arguments.persist:
        database_url = os.environ.get("DATABASE_URL", "")
        persist_license_receipt(database_url, licence)
        persist_fulltext_receipt(database_url, document)
    print(f"verified_open_access: {document.page_count} pages; receipts written")


if __name__ == "__main__":
    main()
