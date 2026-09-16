#!/usr/bin/env python3
"""Render candidate PDF pages in memory, analyse diagrams with Vision, then delete uploads."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO
import json, os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader
from gigachat.models import Chat, Messages
from neurolab.diagram_cards import build_diagram_prompt, candidate_diagram_pages, parse_diagram_card, render_page_png
from neurolab.fulltext_verification import OpenAccessPdfRequest, default_pdf_transport
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.research_storage import load_document_identity, persist_diagram_card

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "it-research" / "latest-diagram-cards.json"

class _VisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    diagram_kind: str; summary: str; components: list[str]; connections: list[str]; feedback_or_control: list[str]; limitations: list[str]

def _vision(client: Any, prompt: str, image: bytes, page: int) -> str:
    stream = BytesIO(image); stream.name = f"public-pdf-page-{page}.png"  # type: ignore[attr-defined]
    uploaded = None
    try:
        uploaded = client.upload_file(stream, purpose="general")
        # Vision attachments use the regular chat endpoint.  ``chat_parse``
        # accepts only a text/native Chat payload in the pinned SDK and would
        # silently make this visual route depend on an incompatible API type.
        request = Chat(
            messages=[Messages(role="user", content=prompt, attachments=[uploaded.id_])],
            temperature=0,
        )
        response = client.chat(request)
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise RuntimeError("Vision response does not contain text JSON")
        candidate = content.strip()
        if candidate.startswith("```json\n") and candidate.endswith("\n```"):
            candidate = candidate[8:-4].strip()
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as error:
            raise RuntimeError("Vision response is not JSON") from error
        # The provider occasionally serializes a one-item string instead of an
        # array. Normalize that narrow representation, then validate the exact
        # bounded schema; no unknown keys or arbitrary shapes are accepted.
        if isinstance(value, dict):
            for field in ("components", "connections", "feedback_or_control", "limitations"):
                if isinstance(value.get(field), str):
                    value[field] = [value[field]]
        return _VisionResponse.model_validate(value).model_dump_json()
    finally:
        if uploaded is not None:
            try:
                client.delete_file(uploaded.id_)
            except Exception as error:
                raise RuntimeError("temporary Vision upload could not be deleted") from error

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True); parser.add_argument("--document-id", required=True); parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--page", type=int, action="append", dest="pages"); parser.add_argument("--maximum-pages", type=int, default=8)
    args = parser.parse_args(); database_url = os.environ.get("DATABASE_URL", "")
    identity = load_document_identity(database_url, source_key=args.source_key, document_id=args.document_id)
    request = OpenAccessPdfRequest(identity.source_key, args.arxiv_id, identity.license_id)
    if identity.provider != "arxiv" or identity.document_url != request.url: raise RuntimeError("diagram route requires the exact verified arXiv document")
    response = default_pdf_transport(request.url)
    if not response.payload.startswith(b"%PDF-") or sha256(response.payload).hexdigest() != identity.document_sha256: raise RuntimeError("PDF does not match document receipt")
    reader = PdfReader(BytesIO(response.payload), strict=True); texts = tuple(page.extract_text() or "" for page in reader.pages)
    if len(texts) != identity.page_count: raise RuntimeError("PDF page count does not match document receipt")
    pages = tuple(args.pages) if args.pages else candidate_diagram_pages(texts, maximum_pages=args.maximum_pages)
    if not pages or len(pages) > 12 or any(not 1 <= page <= len(texts) for page in pages): raise RuntimeError("diagram page selection is outside the limit")
    results = []
    with GigaChatClientFactory().create(GigaChatSettings.from_environment()) as client:
        for page in dict.fromkeys(pages):
            image = render_page_png(response.payload, page_number=page)
            card = parse_diagram_card(_vision(client, build_diagram_prompt(title=identity.title, page_number=page), image, page), source_key=identity.source_key, document_id=identity.document_id, document_sha256=identity.document_sha256, page_number=page, image_bytes=image)
            results.append({"card_id": persist_diagram_card(database_url, card), "card": asdict(card), "card_sha256": card.card_sha256})
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(json.dumps({"cards": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"diagram_cards: needs_review; pages={len(results)}")

if __name__ == "__main__": main()
