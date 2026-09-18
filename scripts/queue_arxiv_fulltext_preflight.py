#!/usr/bin/env python3
"""Write a bounded, metadata-only queue for arXiv license/PDF preflight."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from neurolab.fulltext_candidate_queue import build_fulltext_preflight_queue
from neurolab.research_storage import load_corpus_assessments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    arguments = parser.parse_args()
    candidates = build_fulltext_preflight_queue(
        load_corpus_assessments(os.environ.get("DATABASE_URL", "")), limit=arguments.limit
    )
    receipt = {
        "queue_version": "arxiv-fulltext-preflight-v1",
        "boundary": "Candidates are metadata-only and require exact arXiv license/PDF verification before download or use.",
        "candidate_count": len(candidates),
        "candidates": [candidate.as_json_value() for candidate in candidates],
    }
    output = Path("/app/runtime/it-research/latest-arxiv-fulltext-preflight.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"arxiv_fulltext_preflight: candidates={len(candidates)}")


if __name__ == "__main__":
    main()
