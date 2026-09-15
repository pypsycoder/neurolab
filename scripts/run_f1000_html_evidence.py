#!/usr/bin/env python3
"""Verify one fixed F1000Research HTML article and write review-only evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import os
from pathlib import Path

from neurolab.publisher_evidence import F1000ArticleRequest, verify_f1000_article
from neurolab.research_storage import persist_publisher_html_receipt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-f1000-html-evidence.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True, help="Existing 64-character corpus source key.")
    parser.add_argument("--article-id", required=True, help="F1000 volume-article identifier; arbitrary URLs are forbidden.")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--persist", action="store_true", help="Store only the receipt in PostgreSQL.")
    arguments = parser.parse_args()

    evidence = verify_f1000_article(
        F1000ArticleRequest(arguments.source_key, arguments.article_id, arguments.version),
        checked_on=datetime.now(UTC).date().isoformat(),
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"receipt": asdict(evidence.receipt), "excerpt": evidence.excerpt}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if arguments.persist:
        persist_publisher_html_receipt(os.environ.get("DATABASE_URL", ""), evidence.receipt)
    print("publisher_html_verified: receipt and bounded review excerpt written")


if __name__ == "__main__":
    main()
