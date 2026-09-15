#!/usr/bin/env python3
"""Record a human-reviewed, page-located claim in the public research corpus."""

from __future__ import annotations

import argparse
import os

from neurolab.claim_review import ClaimAssessment, ReviewedClaim
from neurolab.research_storage import persist_reviewed_claim


def _score(value: str) -> float | None:
    return None if value == "unknown" else float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--summary", required=True, help="Reviewer-written one-line claim; not copied source text.")
    parser.add_argument("--page-start", required=True, type=int)
    parser.add_argument("--page-end", required=True, type=int)
    parser.add_argument("--maturity", required=True, choices=["hypothesis", "formal_or_method", "simulated_or_benchmarked", "prototype", "replicated", "operational"])
    parser.add_argument("--lane", required=True, choices=["watchlist", "research_experiment", "implementation_candidate", "production_candidate"])
    parser.add_argument("--conceptual", default="unknown")
    parser.add_argument("--empirical", default="unknown")
    parser.add_argument("--reproducibility", default="unknown")
    parser.add_argument("--feasibility", default="unknown")
    parser.add_argument("--independence", default="unknown")
    parser.add_argument("--uncertainty", required=True, choices=["low", "medium", "high", "unknown"])
    parser.add_argument("--assessor", required=True, choices=["human", "approved_model"], help="Model-created claims remain needs_review.")
    parser.add_argument("--rationale", required=True, action="append", help="One reviewer-written one-line evidence note; repeatable.")
    arguments = parser.parse_args()

    claim = ReviewedClaim(
        source_key=arguments.source_key,
        document_id=arguments.document_id,
        summary=arguments.summary,
        page_start=arguments.page_start,
        page_end=arguments.page_end,
        maturity=arguments.maturity,
        action_lane=arguments.lane,
        assessment=ClaimAssessment(
            assessor=arguments.assessor,
            conceptual_support=_score(arguments.conceptual),
            empirical_support=_score(arguments.empirical),
            reproducibility=_score(arguments.reproducibility),
            feasibility_now=_score(arguments.feasibility),
            source_independence=_score(arguments.independence),
            uncertainty=arguments.uncertainty,
            rationale=tuple(arguments.rationale),
        ),
    )
    claim_id = persist_reviewed_claim(os.environ.get("DATABASE_URL", ""), claim)
    print(f"claim_recorded:{claim.reviewer_status}: {claim_id}")


if __name__ == "__main__":
    main()
