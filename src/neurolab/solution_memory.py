"""Evidence-gated memory of reusable solutions and their synthetic outcomes."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal
from uuid import UUID


AssetKind = Literal["architecture_pattern", "workflow_scheme", "code_component", "test_suite", "evaluator", "prompt_template"]
AssetState = Literal["candidate", "promoted", "watchlist", "retired"]
OutcomeKind = Literal["success", "failure", "regression"]

_LABEL = re.compile(r"^[^\r\n]{3,160}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class SolutionMemoryError(ValueError):
    pass


def _uuid(value: str) -> bool:
    try:
        UUID(value)
    except (TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class SolutionAsset:
    asset_id: str
    kind: AssetKind
    label: str
    content_sha256: str
    state: AssetState = "candidate"

    def __post_init__(self) -> None:
        if not _uuid(self.asset_id) or self.kind not in {"architecture_pattern", "workflow_scheme", "code_component", "test_suite", "evaluator", "prompt_template"} or self.state not in {"candidate", "promoted", "watchlist", "retired"}:
            raise SolutionMemoryError("solution asset metadata is malformed")
        if not _LABEL.fullmatch(self.label) or not _HASH.fullmatch(self.content_sha256):
            raise SolutionMemoryError("solution asset receipt is malformed")


@dataclass(frozen=True)
class SolutionOutcome:
    asset_id: str
    synthetic_run_sha256: str
    evaluator_run_id: str
    outcome: OutcomeKind
    primary_quality: float
    safety_quality: float

    def __post_init__(self) -> None:
        if not _uuid(self.asset_id) or not _uuid(self.evaluator_run_id) or not _HASH.fullmatch(self.synthetic_run_sha256):
            raise SolutionMemoryError("solution outcome identity is malformed")
        if self.outcome not in {"success", "failure", "regression"} or not 0 <= self.primary_quality <= 1 or not 0 <= self.safety_quality <= 1:
            raise SolutionMemoryError("solution outcome is malformed")


def next_asset_state(asset: SolutionAsset, outcomes: tuple[SolutionOutcome, ...]) -> AssetState:
    """Promote only repeatedly successful, independently evaluated assets."""
    relevant = tuple(item for item in outcomes if item.asset_id == asset.asset_id)
    if len(relevant) != len(outcomes) or not relevant:
        raise SolutionMemoryError("outcomes must belong to exactly one asset")
    if sum(item.outcome == "regression" for item in relevant) >= 2:
        return "retired"
    successful = tuple(item for item in relevant if item.outcome == "success")
    if len(successful) >= 3 and all(item.safety_quality >= .90 for item in successful) and sum(item.primary_quality for item in successful) / len(successful) >= .80:
        return "promoted"
    if any(item.outcome in {"failure", "regression"} for item in relevant):
        return "watchlist"
    return "candidate"
