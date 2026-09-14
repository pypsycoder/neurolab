"""Minimal acceptance gate for future isolated engineering-agent output."""

from dataclasses import dataclass
import re
from typing import Iterable


class EngineeringPolicyError(ValueError):
    """An isolated worktree result is not eligible for human review."""


_SAFE_PATH = re.compile(r"^[a-z0-9][a-z0-9_./-]{0,255}$")


@dataclass(frozen=True)
class ReviewReceipt:
    changed_paths: tuple[str, ...]
    test_command: str
    decision: str = "review_required"


def require_reviewable_change(
    *,
    changed_paths: Iterable[str],
    allowed_paths: Iterable[str],
    test_command: str,
    test_exit_code: int,
) -> ReviewReceipt:
    """Accept only a narrow, tested diff and always require human review.

    This function does not invoke an agent, execute a command, merge, push, or
    deploy. It validates metadata supplied by a separately sandboxed evaluator.
    """
    changes = tuple(changed_paths)
    allowed = frozenset(allowed_paths)
    if not changes:
        raise EngineeringPolicyError("a reviewable change must contain a diff")
    if len(changes) != len(set(changes)):
        raise EngineeringPolicyError("duplicate changed paths are forbidden")
    if not all(isinstance(path, str) and _SAFE_PATH.fullmatch(path) for path in changes):
        raise EngineeringPolicyError("changed path is malformed")
    if any(path not in allowed for path in changes):
        raise EngineeringPolicyError("changed path is outside the approved worktree scope")
    if not isinstance(test_command, str) or not test_command.strip():
        raise EngineeringPolicyError("a concrete test command is required")
    if test_exit_code != 0:
        raise EngineeringPolicyError("tests must pass before human review")
    return ReviewReceipt(changed_paths=changes, test_command=test_command.strip())
