#!/usr/bin/env python3
"""Подготовить ограниченный план смысловой проверки; модель не вызывается."""
import argparse
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from neurolab.fulltext_verification import OpenAccessPdfRequest, extract_open_access_pdf
from neurolab.selection_storage import require_metadata_selection
from neurolab.research_selection import digest
from neurolab.task_document_cards import build_semantic_packet, task_context
from neurolab.task_document_storage import load_task_card


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card-id", type=UUID, required=True)
    parser.add_argument("--judge-model", help="Имя другой модели только для планирования; не разрешение её вызова.")
    args = parser.parse_args()
    database = os.environ["DATABASE_URL"]
    card, row = load_task_card(database, str(args.card_id))
    context = task_context(row["mission_id"])
    if context["mission_sha256"] != row["mission_sha256"]:
        raise ValueError("task mission changed")
    selections = require_metadata_selection(database, card.source_key)
    matched = [s for s in selections if s.mission_id == row["mission_id"] and digest(s) == row["metadata_sha256"]]
    if len(matched) != 1:
        raise ValueError("current exact task metadata required")
    result = {"run_id": str(uuid4()), "card_id": str(args.card_id), "card_sha256": card.card_sha256,
              "task_context": context, "status": "distinct_judge_required", "new_model_calls": 0,
              "expected_judge_calls": 0, "semantic_verification": "not_performed", "full_spec_allowed": False,
              "model_profile_verified": False, "raw_content_retained": False}
    if args.judge_model:
        if args.judge_model.strip().casefold() == row["model_label"].strip().casefold():
            raise ValueError("same model is not independent")
        request = OpenAccessPdfRequest(card.source_key, row["document_url"].rsplit("/", 1)[-1], row["license_id"])
        if request.url != row["document_url"]:
            raise ValueError("exact arxiv route required")
        pdf, pages = extract_open_access_pdf(request)
        if pdf.sha256 != card.document_sha256 or pdf.page_count != row["page_count"]:
            raise ValueError("exact PDF changed")
        packet = build_semantic_packet(card, pages, mission_id=row["mission_id"],
                                       candidate_model=row["model_label"], judge_model=args.judge_model)
        result.update(status="planned_contract_only", identity=packet["identity"],
                      expected_judge_calls=packet["expected_judge_calls"])
    output = Path(__file__).resolve().parents[1] / "runtime/it-research" / f"task-semantic-plan-{result['run_id']}.json"
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True) + "\n")
    output.chmod(0o600)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("task_semantic_plan_failed: identity_or_contract_boundary") from None
