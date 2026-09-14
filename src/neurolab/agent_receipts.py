"""Tamper-evident in-memory receipts for the synthetic role hand-off chain."""

from dataclasses import dataclass
from hashlib import sha256
import json

from neurolab.agent_transitions import (
    AgentTransitionPolicyError,
    RoleTransition,
    require_allowed_transition,
)


class AgentReceiptPolicyError(ValueError):
    """A receipt is invalid, altered, or cannot accept the requested hand-off."""


@dataclass(frozen=True)
class TransitionReceipt:
    """Minimal synthetic chain evidence; it contains no task content or credentials."""

    state: str
    transitions: tuple[RoleTransition, ...]
    integrity: str


def _integrity(state: str, transitions: tuple[RoleTransition, ...]) -> str:
    payload = {
        "state": state,
        "transitions": [
            {
                "from_state": item.from_state,
                "to_state": item.to_state,
                "role": item.role,
                "action": item.action,
            }
            for item in transitions
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def new_transition_receipt() -> TransitionReceipt:
    """Start an empty receipt at the only permitted initial state."""
    return TransitionReceipt(state="planned", transitions=(), integrity=_integrity("planned", ()))


def verify_transition_receipt(receipt: TransitionReceipt) -> None:
    """Verify digest, continuity, and every exact transition in the receipt."""
    if receipt.integrity != _integrity(receipt.state, receipt.transitions):
        raise AgentReceiptPolicyError("receipt integrity check failed")

    current_state = "planned"
    for transition in receipt.transitions:
        if transition.from_state != current_state:
            raise AgentReceiptPolicyError("receipt transition continuity failed")
        try:
            require_allowed_transition(
                from_state=transition.from_state,
                to_state=transition.to_state,
                role=transition.role,
                action=transition.action,
            )
        except AgentTransitionPolicyError as error:
            raise AgentReceiptPolicyError("receipt contains an unapproved transition") from error
        current_state = transition.to_state

    if receipt.state != current_state:
        raise AgentReceiptPolicyError("receipt terminal state does not match transitions")


def require_completed_transition_receipt(receipt: TransitionReceipt) -> None:
    """Fail closed unless the verified chain reaches its sole terminal state."""
    verify_transition_receipt(receipt)
    if receipt.state != "reported":
        raise AgentReceiptPolicyError("receipt has not reached the terminal state")


def append_transition(
    receipt: TransitionReceipt, transition: RoleTransition
) -> TransitionReceipt:
    """Return a new receipt only for the next exact, verified hand-off."""
    verify_transition_receipt(receipt)
    if transition.from_state != receipt.state:
        raise AgentReceiptPolicyError("transition does not start at receipt state")
    try:
        require_allowed_transition(
            from_state=transition.from_state,
            to_state=transition.to_state,
            role=transition.role,
            action=transition.action,
        )
    except AgentTransitionPolicyError as error:
        raise AgentReceiptPolicyError("transition is outside the approved graph") from error

    transitions = receipt.transitions + (transition,)
    return TransitionReceipt(
        state=transition.to_state,
        transitions=transitions,
        integrity=_integrity(transition.to_state, transitions),
    )
