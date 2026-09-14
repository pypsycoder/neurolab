"""Default-deny state transitions for the synthetic agent graph."""

from collections.abc import Iterable
from dataclasses import dataclass

from neurolab.agent_roles import AgentRole, AgentRolePolicyError, require_allowed_action


class AgentTransitionPolicyError(ValueError):
    """A requested role hand-off does not belong to the approved state machine."""


@dataclass(frozen=True)
class RoleTransition:
    """One declared and reviewable state hand-off in the synthetic workflow."""

    from_state: str
    to_state: str
    role: AgentRole
    action: str


_MINIMAL_TRANSITIONS: tuple[RoleTransition, ...] = (
    RoleTransition("planned", "routed", "supervisor", "workflow.route"),
    RoleTransition("routed", "worktree_edited", "developer", "engineering.worktree.edit"),
    RoleTransition("worktree_edited", "tested", "tester", "engineering.worktree.test"),
    RoleTransition("tested", "reviewed", "reviewer", "engineering.diff.review"),
    RoleTransition("reviewed", "reported", "synthesizer", "report.compose"),
)


def required_transitions() -> Iterable[RoleTransition]:
    """Return the only forward-only hand-offs used by architecture smoke."""
    return _MINIMAL_TRANSITIONS


def require_allowed_transition(
    *, from_state: str, to_state: str, role: str, action: str
) -> None:
    """Reject skipped, reversed, unknown, or privilege-escalating hand-offs."""
    try:
        require_allowed_action(role, action)
    except AgentRolePolicyError as error:
        raise AgentTransitionPolicyError("role action is not allowed") from error

    requested = RoleTransition(from_state, to_state, role, action)  # type: ignore[arg-type]
    if requested not in _MINIMAL_TRANSITIONS:
        raise AgentTransitionPolicyError("state transition is outside the approved graph")
