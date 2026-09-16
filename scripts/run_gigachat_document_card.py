#!/usr/bin/env python3
"""Create one review-required card from every extractable page of a verified arXiv PDF."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from neurolab.document_cards import (
    build_card_prompt,
    build_window_prompt,
    parse_document_card,
    parse_window_note,
    plan_page_windows,
)
from neurolab.fulltext_verification import OpenAccessPdfRequest, _extract_pdf, default_pdf_transport
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.research_storage import load_document_identity, persist_document_card


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-document-card.json"


class _WindowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    architecture_layers: list[str]
    implementation_signals: list[str]
    evaluation_signals: list[str]
    limitations: list[str]


class _FindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_start: int
    page_end: int
    kind: str
    summary: str


class _CardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_summary: str
    research_problem: str
    method: str
    architecture_layers: list[str]
    implementation_signals: list[str]
    evaluation_signals: list[str]
    limitations: list[str]
    findings: list[_FindingResponse]
    conceptual_support: float | None
    empirical_support: float | None
    reproducibility: float | None
    feasibility_now: float | None
    source_independence: float | None
    uncertainty: str


def _ask(client: Any, prompt: str, response_format: type[BaseModel]) -> str:
    """Use the SDK JSON-schema mode, then revalidate with the local contract."""
    try:
        _, response = client.chat_parse(prompt, response_format=response_format, strict=True)
        return response.model_dump_json()
    except Exception as error:
        raise RuntimeError("GigaChat structured document-card request failed") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--pages-per-window", type=int, default=2)
    parser.add_argument("--persist", action="store_true", help="Store only the bounded card using DATABASE_URL.")
    arguments = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL", "")
    identity = load_document_identity(
        database_url, source_key=arguments.source_key, document_id=arguments.document_id
    )
    if identity.provider != "arxiv":
        raise RuntimeError("document-card route currently accepts only verified arXiv documents")
    request = OpenAccessPdfRequest(identity.source_key, arguments.arxiv_id, identity.license_id)
    if request.url != identity.document_url:
        raise RuntimeError("arXiv identifier does not match the stored document receipt")
    receipt, page_texts = _extract_pdf(request, transport=default_pdf_transport)
    if receipt.sha256 != identity.document_sha256 or receipt.page_count != identity.page_count:
        raise RuntimeError("retrieved PDF does not match the stored document receipt")
    windows = plan_page_windows(page_texts, pages_per_window=arguments.pages_per_window)

    settings = GigaChatSettings.from_environment()
    with GigaChatClientFactory().create(settings) as client:
        notes = tuple(
            parse_window_note(
                _ask(client, build_window_prompt(title=identity.title, window=window), _WindowResponse),
                window=window,
            )
            for window in windows
        )
        card = parse_document_card(
            _ask(
                client,
                build_card_prompt(title=identity.title, page_count=receipt.page_count, notes=notes),
                _CardResponse,
            ),
            source_key=identity.source_key,
            document_id=identity.document_id,
            document_sha256=receipt.sha256,
            page_count=receipt.page_count,
        )

    result: dict[str, object] = {
        "card": asdict(card),
        "card_sha256": card.card_sha256,
        "model_calls": len(windows) + 1,
        "page_windows": [{"page_start": item.page_start, "page_end": item.page_end} for item in windows],
    }
    if arguments.persist:
        result["card_id"] = persist_document_card(database_url, card)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"document_card: needs_review; windows={len(windows)}")


if __name__ == "__main__":
    main()
