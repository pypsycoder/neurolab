#!/usr/bin/env python3
"""Record one human decision for a bounded document card."""

from __future__ import annotations

import argparse
import os

from neurolab.research_storage import review_document_card


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-id", required=True)
    parser.add_argument("--decision", required=True, choices=("reviewed", "rejected"))
    arguments = parser.parse_args()
    card_id = review_document_card(
        os.environ.get("DATABASE_URL", ""), card_id=arguments.card_id, decision=arguments.decision
    )
    print(f"document_card: {arguments.decision}; id={card_id}")


if __name__ == "__main__":
    main()
