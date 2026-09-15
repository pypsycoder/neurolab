#!/usr/bin/env python3
"""Verify bounded GitHub metadata for a human-reviewed public research claim."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path

from neurolab.artifact_verification import PublicRepositoryRequest, verify_public_repository
from neurolab.research_storage import persist_public_artifact_receipt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-public-artifact-receipt.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--claim-id", required=True, help="Must refer to a human-reviewed claim.")
    parser.add_argument("--repository", required=True, help="Fixed public GitHub owner/name; URLs are forbidden.")
    parser.add_argument("--persist", action="store_true")
    arguments = parser.parse_args()

    receipt = verify_public_repository(
        PublicRepositoryRequest(arguments.source_key, arguments.claim_id, arguments.repository)
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if arguments.persist:
        persist_public_artifact_receipt(os.environ.get("DATABASE_URL", ""), receipt)
    print("public_artifact_metadata_verified: receipt written")


if __name__ == "__main__":
    main()
