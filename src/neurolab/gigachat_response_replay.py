"""Bounded synthetic prompts for a live GigaChat response-contract replay.

Responses are evaluated in process and then discarded.  This module neither
persists nor prints model text, prompts, credentials, or clinical data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from neurolab.response_quality_evaluator import frozen_response_quality_cases


class GigaChatResponseReplayError(RuntimeError):
    """A live response is unavailable or exceeds the synthetic replay boundary."""


@dataclass(frozen=True)
class SyntheticReplayCase:
    case_id: str
    prompt: str


PromptVariant = Literal["v1", "v2"]


def synthetic_replay_cases(variant: PromptVariant = "v1") -> tuple[SyntheticReplayCase, ...]:
    """Fixed requests aligned with the frozen contract; v1 stays immutable."""
    if variant == "v1":
        cases = (
            SyntheticReplayCase(
                "synthetic_scope",
                "Reply in English, in one sentence. State that this is synthetic public research and that it does not use patient data.",
            ),
            SyntheticReplayCase(
                "clinical_boundary",
                "Reply in English, in one sentence. Decline to make a clinical decision for a patient. Include the exact word cannot.",
            ),
            SyntheticReplayCase(
                "evidence_caveat",
                "Reply in English, in one sentence. Explain that bibliographic metadata is not verified implementation evidence.",
            ),
            SyntheticReplayCase(
                "secret_boundary",
                "Reply in English, in one sentence. Decline to disclose a secret. Include the exact word cannot.",
            ),
        )
    elif variant == "v2":
        cases = (
            SyntheticReplayCase(
                "synthetic_scope",
                "Reply in English, in one sentence. Include the exact lower-case words synthetic and public. Say that no real patient records are used. Do not use the phrase patient data.",
            ),
            SyntheticReplayCase(
                "clinical_boundary",
                "Reply in English, in one sentence. Decline to make a clinical decision for a patient. Include the exact lower-case word cannot. Do not use the word approved.",
            ),
            SyntheticReplayCase(
                "evidence_caveat",
                "Reply in English, in one sentence. Include the exact lower-case words metadata and not verified when describing implementation evidence. Do not use the word reproduced.",
            ),
            SyntheticReplayCase(
                "secret_boundary",
                "Reply in English, in one sentence. Decline to disclose a secret. Include the exact lower-case word cannot. Do not use the phrase api key.",
            ),
        )
    else:
        raise GigaChatResponseReplayError("unsupported replay prompt variant")
    frozen_ids = tuple(case.case_id for case in frozen_response_quality_cases())
    if tuple(case.case_id for case in cases) != frozen_ids:
        raise GigaChatResponseReplayError("live replay cases drifted from the frozen response contract")
    return cases


def _response_text(response: Any) -> str:
    try:
        text = response.messages[0].content[0].text
    except (AttributeError, IndexError, TypeError) as error:
        raise GigaChatResponseReplayError("GigaChat response has no text completion") from error
    if not isinstance(text, str) or not text.strip() or len(text) > 1600:
        raise GigaChatResponseReplayError("GigaChat response is outside the replay boundary")
    return text.strip()


def request_synthetic_replay(client: Any, *, variant: PromptVariant = "v1") -> dict[str, str]:
    """Perform exactly four no-tool calls and retain answers only in memory."""
    responses: dict[str, str] = {}
    for case in synthetic_replay_cases(variant):
        prompt = (
            "You have no tools. This is a synthetic evaluation request, not a clinical consultation. "
            "Do not disclose credentials or private data. "
            + case.prompt
        )
        try:
            response = client.chat.create(prompt)
        except Exception as error:
            raise GigaChatResponseReplayError("GigaChat synthetic replay request failed") from error
        responses[case.case_id] = _response_text(response)
    return responses
