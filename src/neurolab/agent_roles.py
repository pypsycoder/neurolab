"""Default-deny role and action policy for the synthetic agent graph."""

from collections.abc import Iterable
import re
from typing import Literal


AgentRole = Literal[
    "supervisor",
    "researcher",
    "developer",
    "tester",
    "reviewer",
    "synthesizer",
]


class AgentRolePolicyError(ValueError):
    """A role or requested action is not allowed by the graph policy."""


_ACTION = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_ROLE_ACTIONS: dict[AgentRole, frozenset[str]] = {
    "supervisor": frozenset(
        {"workflow.plan", "workflow.route", "workflow.cancel", "workflow.report"}
    ),
    "researcher": frozenset({"research.evidence.inspect"}),
    "developer": frozenset({"engineering.worktree.edit"}),
    "tester": frozenset({"engineering.worktree.test", "policy.validate"}),
    "reviewer": frozenset({"engineering.diff.review"}),
    "synthesizer": frozenset({"report.compose"}),
}


def allowed_actions(role: str) -> frozenset[str]:
    """Return the immutable allowlist for one declared agent role."""
    try:
        return _ROLE_ACTIONS[role]  # type: ignore[index]
    except (KeyError, TypeError):
        raise AgentRolePolicyError("unknown agent role") from None


def require_allowed_action(role: str, action: str) -> None:
    """Accept only a syntactically valid action in the role's exact allowlist."""
    if not isinstance(action, str) or not _ACTION.fullmatch(action):
        raise AgentRolePolicyError("action name is malformed")
    if action not in allowed_actions(role):
        raise AgentRolePolicyError("action is outside the role allowlist")


def required_role_actions() -> Iterable[tuple[AgentRole, str]]:
    """Return the minimal synthetic path used by the architecture smoke."""
    return (
        ("supervisor", "workflow.route"),
        ("developer", "engineering.worktree.edit"),
        ("tester", "engineering.worktree.test"),
        ("reviewer", "engineering.diff.review"),
        ("synthesizer", "report.compose"),
    )
