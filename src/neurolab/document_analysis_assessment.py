"""Independent deterministic structure/coverage checks, NOT scientific validation."""
from hashlib import sha256
import json
import re

from neurolab.document_cards import DocumentCard


def assess_document_analysis(card: DocumentCard, receipt: dict, *, page_count: int, pdf_sha256: str) -> dict:
    if type(page_count) is not int or not 1 <= page_count <= 100:
        raise ValueError("invalid document page count")
    attempts = receipt.get("attempts", [])
    if not isinstance(attempts, list) or len(attempts) > 51:
        raise ValueError("analysis attempt count outside boundary")
    covered = set()
    known_tokens = unknown_usage = new_calls = 0
    statuses_valid = True
    synthesis_count = 0
    window_count = 0
    keys = []
    for attempt in attempts:
        if attempt.get("kind") not in {"window", "synthesis"}:
            raise ValueError("unknown analysis step")
        keys.append(attempt.get("step_key"))
        if not isinstance(keys[-1], str) or not re.fullmatch(r"[0-9a-f]{64}", keys[-1]):
            raise ValueError("invalid analysis step digest")
        calls = attempt.get("new_model_calls")
        if type(calls) is not int or calls not in (0, 1):
            raise ValueError("invalid analysis call count")
        new_calls += calls
        statuses_valid &= (attempt.get("status") == "completed" and calls == 1
                           or attempt.get("status") == "reused" and calls == 0)
        if calls:
            usage = attempt.get("provider_tokens", {}).get("total_tokens")
            if type(usage) is int and usage >= 0:
                known_tokens += usage
            else:
                unknown_usage += 1
        if attempt["kind"] == "window":
            start, end = attempt.get("page_start"), attempt.get("page_end")
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= page_count:
                raise ValueError("invalid analysis page locator")
            covered.update(range(start, end + 1))
            window_count += 1
        else:
            synthesis_count += 1
    empty = receipt.get("empty_text_pages", [])
    if not isinstance(empty, list) or any(type(p) is not int or not 1 <= p <= page_count for p in empty):
        raise ValueError("invalid empty-page receipt")
    identity_ok = (receipt.get("version") == "document-analysis-v2"
                   and receipt.get("source_key") == card.source_key
                   and receipt.get("document_id") == card.document_id
                   and receipt.get("document_sha256") == pdf_sha256 == card.document_sha256
                   and receipt.get("page_count") == page_count
                   and receipt.get("card_sha256") == card.card_sha256)
    checks = {
        "exact_identity": identity_ok,
        "complete_extractable_page_coverage": covered == set(range(1, page_count + 1)) - set(empty),
        "all_steps_complete": bool(attempts) and statuses_valid and len(set(keys)) == len(keys)
            and window_count == receipt.get("window_count") and synthesis_count == 1
            and attempts[-1]["kind"] == "synthesis" and receipt.get("status") == "needs_review",
        "finding_pages_analysed": all(set(range(f.page_start, f.page_end + 1)) <= covered for f in card.findings),
        "russian_language_hint": all(len(re.findall(r"[А-Яа-яЁё]", s)) >= 10
                                     for s in (card.document_summary, card.research_problem, card.method)),
        "limitations_explicit": bool(card.limitations),
    }
    passed = all(checks.values())
    return {"assessment_version": "document-structure-v1", "run_id": receipt.get("run_id"),
            "source_key": card.source_key, "document_id": card.document_id,
            "card_sha256": card.card_sha256,
            "receipt_sha256": sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
            "structure_passed": passed, "extractable_pages_covered": len(covered),
            "empty_text_pages": empty, "new_model_calls_in_source_run": new_calls,
            "known_provider_tokens_in_source_run": known_tokens, "calls_with_unknown_usage": unknown_usage,
            "decision": "experimental_hypothesis_only" if passed else "repair_analysis_contract",
            "semantic_verification": "not_performed", "independent_reproduction": "not_performed",
            "full_spec_allowed": False, "production_deployed": False, "new_model_calls": 0}


def assess_numeric_anchors(card: DocumentCard, page_texts: tuple[str, ...]) -> dict:
    """Detect invented numeric anchors on cited pages; matching is NOT truth."""
    failed, checked = [], 0
    for index, finding in enumerate(card.findings, 1):
        if finding.page_end > len(page_texts):
            raise ValueError("numeric grounding page mismatch")
        excerpt = "\n".join(page_texts[finding.page_start - 1:finding.page_end])
        # Normalize only thousands-group separators, not arbitrary decimal
        # points. Eg 8,504 can support 8504, but 85.04 cannot support 8504.
        excerpt = re.sub(r"(?<!\d)\d{1,3}(?:[,\u00a0 ]\d{3})+(?!\d)",
                         lambda m: re.sub(r"[,\u00a0 ]", "", m.group()), excerpt)
        observed = set(re.findall(r"(?<!\d)\d+(?:\.\d+)?(?!\d)", excerpt))
        claimed = set(re.findall(r"(?<!\d)\d+(?:\.\d+)?(?!\d)", finding.summary))
        if claimed:
            checked += 1
            if not claimed <= observed:
                failed.append(f"finding_{index}")
    return {"numeric_grounding_version": "numeric-page-anchors-v1",
            "findings_with_numeric_anchors": checked, "failed_numeric_anchor_cases": failed,
            "numeric_anchor_status": "mismatch" if failed else ("supported" if checked else "not_applicable"),
            "semantic_entailment_verified": False, "independent_reproduction": "not_performed"}
