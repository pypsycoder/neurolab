#!/usr/bin/env python3
"""Create one review-required card from every extractable page of a verified arXiv PDF."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from gigachat import GigaChat
from gigachat.models import Chat, Messages, JsonSchemaResponseFormat

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from neurolab.document_cards import (
    build_card_prompt,
    build_window_prompt,
    parse_document_card,
    parse_window_note,
    plan_page_windows,
)
from neurolab.gigachat_retry import is_transient_gigachat_error, run_redacted_cli
from neurolab.document_analysis_cache import run_cached_step, step_key, AnalysisOutcomeUnknown
from neurolab.document_cards import DocumentCardError
from neurolab.fulltext_verification import OpenAccessPdfRequest, extract_open_access_pdf, default_pdf_transport
from neurolab.gigachat import GigaChatClientFactory, GigaChatSettings
from neurolab.research_storage import load_document_identity, persist_document_card
from neurolab.task_document_cards import (
    condition_prompt, require_task_selection, task_context, validate_task_note, validate_task_card,
    serialize_task_card,
)
from neurolab.task_document_storage import persist_task_card
from neurolab.research_selection import MISSIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "runtime" / "it-research" / "latest-document-card.json"


class _WindowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    architecture_layers: list[Literal["global_architecture", "subsystem", "component", "feature"]]
    implementation_signals: list[str]
    evaluation_signals: list[str]
    limitations: list[str]


class _FindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_start: int
    page_end: int
    kind: Literal["architecture", "method", "implementation", "evaluation", "limitation"]
    summary: str


class _CardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_summary: str
    research_problem: str
    method: str
    architecture_layers: list[Literal["global_architecture", "subsystem", "component", "feature"]]
    implementation_signals: list[str]
    evaluation_signals: list[str]
    limitations: list[str]
    findings: list[_FindingResponse]
    conceptual_support: float | None
    empirical_support: float | None
    reproducibility: float | None
    feasibility_now: float | None
    source_independence: float | None
    uncertainty: Literal["low", "medium", "high", "unknown"]


class _TaskFindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_start: int
    page_end: int
    kind: Literal["architecture", "method", "implementation", "evaluation", "limitation"]
    source_statement: str = Field(min_length=20, max_length=400)
    task_application: str = Field(min_length=20, max_length=400)
    missing_details: str = Field(min_length=20, max_length=400)


class _TaskCardResponse(_CardResponse):
    findings: list[_TaskFindingResponse]
    reproducibility: None
    source_independence: None


def _parse_task_card(raw, *, identity, receipt):
    value = _TaskCardResponse.model_validate_json(raw).model_dump(mode="json")
    value["findings"] = [{"page_start": f["page_start"], "page_end": f["page_end"], "kind": f["kind"],
        "summary": f"В статье: {f['source_statement'].strip()} Применение: {f['task_application'].strip()} Пробел: {f['missing_details'].strip()}"}
        for f in value["findings"]]
    parsed = parse_document_card(json.dumps(value, ensure_ascii=False), source_key=identity.source_key,
        document_id=identity.document_id, document_sha256=receipt.sha256, page_count=receipt.page_count)
    return validate_task_card(parsed)


def _ask(client: Any, prompt: str, response_format: type[BaseModel], *, metadata: dict) -> str:
    """Official structured Chat, capturing usage before local parsing can fail."""
    request = Chat(messages=[Messages(role="user", content=prompt)], temperature=0,
                   max_tokens=2048 if response_format is _WindowResponse else 4096,
                   response_format=JsonSchemaResponseFormat(schema=response_format, strict=True))
    response = client.chat(request)
    usage = getattr(response, "usage", None)
    metadata["provider_tokens"] = {
        name: n if type(n := getattr(usage, name, None)) is int and n >= 0 else None
        for name in ("prompt_tokens", "completion_tokens", "total_tokens")}
    if not response.choices or response.choices[0].finish_reason != "stop":
        metadata["failure_code"] = "incomplete_response"
        raise DocumentCardError("document response is incomplete")
    raw = response.choices[0].message.content
    if not isinstance(raw, str) or len(raw.encode()) > 48000:
        metadata["failure_code"] = "response_boundary"
        raise DocumentCardError("document response outside boundary")
    try:
        return response_format.model_validate_json(raw).model_dump_json()
    except ValidationError:
        metadata["failure_code"] = "response_schema"
        raise DocumentCardError("document response schema invalid") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--arxiv-id", required=True)
    parser.add_argument("--pages-per-window", type=int, default=2)
    parser.add_argument("--mission", choices=[m.mission_id for m in MISSIONS],
                        help="Разбор под одну допущенную задачу; отдельная карточка, только сравнительный режим.")
    parser.add_argument("--reuse-windows-only", action="store_true",
                        help="Только готовые окна; новые вызовы для текста запрещены. Максимум один новый синтез.")
    parser.add_argument("--max-rate-limit-retries", type=int, choices=[0], default=0,
                        help="Retries belong to the two-lane wrapper; no hidden per-window retries.")
    parser.add_argument("--plan-only", action="store_true", help="Extract/plan without credentials or model calls.")
    parser.add_argument("--persist", action="store_true", help="Store only the bounded card using DATABASE_URL.")
    arguments = parser.parse_args()
    if arguments.reuse_windows_only and not arguments.mission:
        raise DocumentCardError("cached windows only requires a trusted task")

    database_url = os.environ.get("DATABASE_URL", "")
    from neurolab.selection_storage import require_metadata_selection, persist_selection
    from neurolab.research_selection import assess_content
    selections = require_metadata_selection(database_url, arguments.source_key)
    identity = load_document_identity(
        database_url, source_key=arguments.source_key, document_id=arguments.document_id
    )
    if arguments.mission:
        selections = (require_task_selection(selections, mission_id=arguments.mission,
                         source_key=identity.source_key, title=identity.title),)
    if identity.provider != "arxiv":
        raise RuntimeError("document-card route currently accepts only verified arXiv documents")
    request = OpenAccessPdfRequest(identity.source_key, arguments.arxiv_id, identity.license_id)
    if request.url != identity.document_url:
        raise RuntimeError("arXiv identifier does not match the stored document receipt")
    receipt, page_texts = extract_open_access_pdf(request, transport=default_pdf_transport)
    if receipt.sha256 != identity.document_sha256 or receipt.page_count != identity.page_count:
        raise RuntimeError("retrieved PDF does not match the stored document receipt")
    windows = plan_page_windows(page_texts, pages_per_window=arguments.pages_per_window)
    run_id = str(uuid4())
    audit = {"run_id": run_id, "version": "document-analysis-v2", "source_key": identity.source_key,
             "document_id": identity.document_id, "document_sha256": identity.document_sha256,
             "page_count": receipt.page_count, "window_count": len(windows),
             "empty_text_pages": [i for i, text in enumerate(page_texts, 1) if not text.strip()],
             "planned_max_model_calls": len(windows) + 1, "status": "planned", "attempts": [],
             "raw_content_retained": False, "production_deployed": False}
    if arguments.mission:
        audit.update(analysis_mode="task_conditioned_shadow", task_context=task_context(arguments.mission),
                     semantic_verification="not_performed", full_spec_allowed=False,
                     synthesis_contract="task-synthesis-v2")
    if arguments.reuse_windows_only:
        audit.update(reuse_windows_only=True, planned_max_new_model_calls=1)
    if arguments.plan_only:
        print(json.dumps(audit, sort_keys=True))
        return

    settings = GigaChatSettings.from_environment()
    audit.update(model_label=settings.model, status="failed")
    def step(prompt, schema, validator, *, kind, start=None, end=None):
        metadata = {"kind": kind, "page_start": start, "page_end": end,
                    "new_model_calls": 0, "status": "failed"}
        audit["attempts"].append(metadata)
        key = step_key(document_sha256=receipt.sha256, model_label=settings.model, prompt=prompt)
        metadata["step_key"] = key
        directory = "task-document-analysis-cache" if arguments.mission else "document-analysis-cache"
        def ask_step():
            if arguments.reuse_windows_only and kind == "window":
                raise DocumentCardError("new window call forbidden")
            return _ask(client, prompt, schema, metadata=metadata)
        def validate_with_diagnostics(raw):
            try:
                return validator(raw)
            except Exception as error:
                codes = {"Russian explanatory prose required": "russian_prose",
                         "task finding sections required": "finding_sections",
                         "task finding section too vague": "finding_detail",
                         "independent evidence must remain unknown": "independent_score_claim"}
                metadata["failure_code"] = (codes.get(str(error), "validator_contract")
                                            if isinstance(error, DocumentCardError) else "validator_contract")
                raise
        return run_cached_step(OUTPUT_PATH.parent / directory, key, metadata,
                               ask_step, validate_with_diagnostics,
                               serialize=serialize_task_card if arguments.mission and kind == "synthesis" else None)
    def prompt_for_task(prompt, *, synthesis=False):
        return condition_prompt(prompt, arguments.mission, synthesis=synthesis) if arguments.mission else prompt

    def parse_note(raw, window):
        note = parse_window_note(raw, window=window)
        return validate_task_note(note) if arguments.mission else note

    def parse_card(raw):
        if arguments.mission:
            return _parse_task_card(raw, identity=identity, receipt=receipt)
        parsed = parse_document_card(raw, source_key=identity.source_key,
            document_id=identity.document_id, document_sha256=receipt.sha256, page_count=receipt.page_count)
        return parsed
    try:
        if arguments.reuse_windows_only:
            from neurolab.document_analysis_cache import canonical, VERSION as CACHE_VERSION
            for w in windows:
                key = step_key(document_sha256=receipt.sha256, model_label=settings.model,
                    prompt=prompt_for_task(build_window_prompt(title=identity.title, window=w)))
                path = OUTPUT_PATH.parent / "task-document-analysis-cache" / f"{key}.json"
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 60000:
                    raise DocumentCardError("required completed window unavailable")
                value = json.loads(path.read_text(encoding="utf-8"))
                if (set(value) != {"version", "step_key", "status", "requests", "validated_output", "output_sha256"}
                        or value["version"] != CACHE_VERSION or value["step_key"] != key
                        or value["status"] != "completed"):
                    raise DocumentCardError("required completed window unavailable")
                from hashlib import sha256
                raw = canonical(value["validated_output"])
                if sha256(raw.encode()).hexdigest() != value["output_sha256"]:
                    raise DocumentCardError("required completed window corrupted")
                parse_note(raw, w)
        # Disable SDK retries, so each audited invocation is one generation attempt.
        factory = GigaChatClientFactory(constructor=lambda **kw: GigaChat(max_retries=0, **kw))
        with factory.create(settings) as client:
            notes = tuple(step(prompt_for_task(build_window_prompt(title=identity.title, window=w)), _WindowResponse,
                               lambda raw, w=w: parse_note(raw, w),
                               kind="window", start=w.page_start, end=w.page_end) for w in windows)
            card = step(prompt_for_task(build_card_prompt(title=identity.title, page_count=receipt.page_count, notes=notes),
                                        synthesis=True), _TaskCardResponse if arguments.mission else _CardResponse,
                        parse_card, kind="synthesis")
        # A finding must belong to analysed windows, not just fall within PDF length.
        covered = {p for w in windows for p in range(w.page_start, w.page_end + 1)}
        if any(not set(range(f.page_start, f.page_end + 1)) <= covered for f in card.findings):
            raise DocumentCardError("finding outside analysed windows")
        result = {"run_id": run_id, "card": asdict(card), "card_sha256": card.card_sha256,
                  "model_calls": sum(a["new_model_calls"] for a in audit["attempts"]),
                  "page_windows": [{"page_start": w.page_start, "page_end": w.page_end} for w in windows]}
        audit.update(status="needs_review", card_sha256=card.card_sha256)
        utility = [assess_content(card, selected, page_texts) for selected in selections]
        if arguments.mission:
            audit["legacy_utility_shadow"] = [s.model_dump(mode="json") for s in utility]
            result["task_context"] = audit["task_context"]
        if arguments.persist:
            result["card_id"] = (persist_task_card(database_url, card, selections[0], audit)
                                 if arguments.mission else persist_document_card(database_url, card))
            audit["card_id"] = result["card_id"]
            # Новый режим не меняет прежние решения допуска и пакет ТЗ.
            if not arguments.mission:
                for selection in utility:
                    persist_selection(database_url, selection)
            audit["utility_decisions"] = {s.mission_id: s.decision for s in utility}
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = OUTPUT_PATH.parent / "latest-task-document-card.json" if arguments.mission else OUTPUT_PATH
        if output.is_symlink():
            raise DocumentCardError("document output symlink forbidden")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.chmod(0o600)
        if arguments.mission:
            per_run = output.parent / f"task-document-card-{run_id}.json"
            with per_run.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            per_run.chmod(0o600)
    except Exception as error:
        # Only definite quota refusals may trigger wrapper failover and reuse.
        # Timeouts/unknown provider execution stay closed, never blind replay.
        if is_transient_gigachat_error(error) and audit["attempts"] and audit["attempts"][-1]["status"] != "quota_refused":
            raise AnalysisOutcomeUnknown("provider outcome unknown; automatic repeat blocked") from None
        raise
    finally:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        prefix = "task-document-receipt" if arguments.mission else "document-receipt"
        path = OUTPUT_PATH.parent / f"{prefix}-{run_id}.json"
        path.write_text(json.dumps(audit, sort_keys=True) + "\n", encoding="utf-8")
        path.chmod(0o600)
    print(f"document_card: needs_review; run_id={run_id}; windows={len(windows)}; new_model_calls={result['model_calls']}")


if __name__ == "__main__":
    run_redacted_cli(main, component="document_card")
