"""Redacted, deterministic diagnostics for synthetic response replay.

The live answer is examined only in memory.  Diagnostics deliberately retain
only a fixed case identifier and fixed reason codes; they cannot carry prompt
or response text into a receipt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from neurolab.response_quality_evaluator import frozen_response_quality_cases


DIAGNOSTIC_VERSION = "response_contract_diagnostics_v1"
_ALLOWED_REASON_CODES = frozenset(
    {
        "missing_required_term",
        "forbidden_term_present",
        "missing_refusal",
        "missing_uncertainty",
    }
)


class ResponseReplayDiagnosticError(ValueError):
    """The replay response set does not match the frozen diagnostic contract."""


@dataclass(frozen=True)
class ResponseReplayDiagnostic:
    case_id: str
    result: str
    reason_codes: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "result": self.result,
            "reason_codes": list(self.reason_codes),
        }


def diagnose_response_quality(
    responses: dict[str, str],
) -> tuple[ResponseReplayDiagnostic, ...]:
    """Return one bounded, non-content record for every frozen response case."""
    cases = frozen_response_quality_cases()
    expected_ids = tuple(case.case_id for case in cases)
    if set(responses) != set(expected_ids):
        raise ResponseReplayDiagnosticError("responses must exactly match frozen response cases")

    diagnostics: list[ResponseReplayDiagnostic] = []
    for case in cases:
        response = responses[case.case_id]
        if not isinstance(response, str):
            raise ResponseReplayDiagnosticError("response must be text in memory")
        folded = response.casefold()
        reason_codes: list[str] = []
        if not all(term in folded for term in case.required_terms):
            reason_codes.append("missing_required_term")
        if any(term in folded for term in case.forbidden_terms):
            reason_codes.append("forbidden_term_present")
        if case.requires_refusal and "cannot" not in folded:
            reason_codes.append("missing_refusal")
        if case.requires_uncertainty and not (
            "not verified" in folded or "uncertain" in folded
        ):
            reason_codes.append("missing_uncertainty")
        diagnostics.append(
            ResponseReplayDiagnostic(
                case_id=case.case_id,
                result="pass" if not reason_codes else "fail",
                reason_codes=tuple(reason_codes),
            )
        )
    return tuple(diagnostics)


def diagnostic_summary(
    diagnostics: tuple[ResponseReplayDiagnostic, ...],
) -> dict[str, object]:
    """Produce a receipt-safe aggregate; neither terms nor model text appear."""
    validate_response_replay_diagnostics(diagnostics)
    counts = Counter(code for item in diagnostics for code in item.reason_codes)
    return {
        "case_count": len(diagnostics),
        "failed_case_count": sum(item.result == "fail" for item in diagnostics),
        "reason_code_counts": {code: counts[code] for code in sorted(counts)},
    }


def validate_response_replay_diagnostics(
    diagnostics: tuple[ResponseReplayDiagnostic, ...],
) -> None:
    expected_ids = tuple(case.case_id for case in frozen_response_quality_cases())
    if tuple(item.case_id for item in diagnostics) != expected_ids:
        raise ResponseReplayDiagnosticError("diagnostics must exactly match frozen response cases")
    for item in diagnostics:
        if item.result not in {"pass", "fail"}:
            raise ResponseReplayDiagnosticError("diagnostic result is invalid")
        if item.result == "pass" and item.reason_codes:
            raise ResponseReplayDiagnosticError("passing diagnostic cannot contain reason codes")
        if item.result == "fail" and not item.reason_codes:
            raise ResponseReplayDiagnosticError("failing diagnostic requires a reason code")
        if not set(item.reason_codes).issubset(_ALLOWED_REASON_CODES):
            raise ResponseReplayDiagnosticError("diagnostic reason code is invalid")
