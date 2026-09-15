#!/usr/bin/env python3
"""Verify one explicitly licensed arXiv PDF without retaining its bytes or text."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.fulltext_verification import OpenAccessPdfRequest, verify_open_access_pdf
from neurolab.research_storage import persist_fulltext_receipt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-fulltext-receipt.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True, help="Existing 64-character corpus source key.")
    parser.add_argument("--arxiv-id", required=True, help="Modern arXiv identifier; arbitrary URL input is forbidden.")
    parser.add_argument("--license", required=True, help="Explicit compatible licence, e.g. CC-BY-4.0.")
    parser.add_argument("--persist", action="store_true", help="Store only the receipt in PostgreSQL using DATABASE_URL.")
    arguments = parser.parse_args()

    receipt = verify_open_access_pdf(
        OpenAccessPdfRequest(arguments.source_key, arguments.arxiv_id, arguments.license)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(receipt.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if arguments.persist:
        persist_fulltext_receipt(os.environ.get("DATABASE_URL", ""), receipt)
    print(f"{receipt.extraction_status}: {receipt.page_count} pages; receipt written")


if __name__ == "__main__":
    main()
