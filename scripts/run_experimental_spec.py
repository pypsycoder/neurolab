#!/usr/bin/env python3
"""GigaChat drafts an experimental spec from receipt-backed public cards, without tools."""
import json
import os
from pathlib import Path
from uuid import uuid4

from neurolab.experimental_spec import DraftSpec, build_spec_prompt, canonical_json, content_hash, load_experimental_packet, render_draft_markdown, validate_draft
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.gigachat_retry import bounded_gigachat_call, run_redacted_cli


def main() -> None:
    packet = load_experimental_packet(os.environ.get("DATABASE_URL", ""))
    settings = GigaChatSettings.from_environment()
    run_id = str(uuid4())
    with GigaChatClientFactory().create(settings) as client:
        _, response = bounded_gigachat_call(lambda: client.chat_parse(build_spec_prompt(packet), response_format=DraftSpec, strict=True), max_retries=0)
        draft = validate_draft(response.model_dump_json(), packet)
    receipt = {"run_id": run_id, "boundary": draft.boundary, "status": "draft_experimental",
               "packet_sha256": content_hash(packet), "spec_sha256": content_hash(draft),
               "card_count": len(packet.notes), "model_calls": 1, "model_label": settings.model,
               "code_executed": False, "independent_evaluation": "pending"}
    import psycopg
    with psycopg.connect(os.environ.get("DATABASE_URL", "")) as connection:
        connection.execute("""INSERT INTO it_research.experimental_specs
            (run_id,boundary,packet_sha256,spec_sha256,model_label,status,spec,receipt)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
            (run_id,draft.boundary,content_hash(packet),content_hash(draft),settings.model,
             "draft_experimental",canonical_json(draft),json.dumps(receipt)))
    root = Path(__file__).resolve().parents[1] / "runtime/it-research"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"spec-{run_id}.json").write_text(canonical_json(draft) + "\n", encoding="utf-8")
    (root / f"spec-{run_id}.md").write_text(render_draft_markdown(draft), encoding="utf-8")
    (root / "latest-spec-receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    run_redacted_cli(main, component="experimental_spec")
