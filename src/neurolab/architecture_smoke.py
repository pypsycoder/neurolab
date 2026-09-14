"""Deterministic architecture-level synthetic smoke orchestration.

This module joins already independently verified local contracts. It never
opens MCP transport, a network connection, a worktree, or an LLM session.
The runner invokes the real synthetic worktree check before calling this
orchestration layer and supplies only its constrained evidence.
"""

from dataclasses import dataclass
from time import monotonic
from typing import Iterable

from neurolab.agent_budget import require_within_budget
from neurolab.agent_roles import require_allowed_action, required_role_actions
from neurolab.agent_receipts import (
    append_transition,
    new_transition_receipt,
    require_completed_transition_receipt,
    verify_transition_receipt,
)
from neurolab.agent_transitions import require_allowed_transition, required_transitions
from neurolab.engineering_policy import ReviewReceipt, require_reviewable_change
from neurolab.run_trace import build_synthetic_run_trace
from neurolab.synthetic_mcp_trace import TraceState, run_synthetic_mcp_trace
from neurolab.workflow import WorkflowState, run_smoke_task


@dataclass(frozen=True)
class ArchitectureSmokeReport:
    """Review-only receipt for a fully synthetic architecture scenario."""

    decision: str
    audit: tuple[str, ...]
    report: str


def run_architecture_smoke(
    *,
    task: str,
    thread_id: str,
    changed_paths: Iterable[str],
    allowed_paths: Iterable[str],
    test_command: str,
    test_exit_code: int,
) -> ArchitectureSmokeReport:
    """Join workflow, untrusted MCP data, and a review-only change receipt.

    The caller must run the controlled worktree evaluator first. This function
    deliberately receives only its narrowed metadata: permitted changed paths
    and a concrete test result.
    """

    started_at = monotonic()
    workflow_state: WorkflowState = run_smoke_task(
        task, "engineering", thread_id=f"{thread_id}:workflow"
    )
    if workflow_state["status"] != "validated":
        raise ValueError("architecture workflow did not validate")

    for role, action in required_role_actions():
        require_allowed_action(role, action)
    transition_receipt = new_transition_receipt()
    for transition in required_transitions():
        require_allowed_transition(
            from_state=transition.from_state,
            to_state=transition.to_state,
            role=transition.role,
            action=transition.action,
        )
        transition_receipt = append_transition(transition_receipt, transition)
    verify_transition_receipt(transition_receipt)
    require_completed_transition_receipt(transition_receipt)
    elapsed_ms = int((monotonic() - started_at) * 1_000)
    require_within_budget(
        transitions=len(transition_receipt.transitions),
        elapsed_ms=elapsed_ms,
        external_calls=0,
        cost_units=0,
    )

    mcp_state: TraceState = run_synthetic_mcp_trace(
        task, thread_id=f"{thread_id}:mcp"
    )
    if mcp_state["status"] != "validated":
        raise ValueError("synthetic MCP trace did not validate")

    receipt: ReviewReceipt = require_reviewable_change(
        changed_paths=changed_paths,
        allowed_paths=allowed_paths,
        test_command=test_command,
        test_exit_code=test_exit_code,
    )

    audit = (
        "workflow:validated",
        "roles:default-deny",
        "transitions:forward-only",
        "receipt:verified-chain",
        "receipt:complete",
        "budget:within-limits",
        "mcp-policy:accepted-untrusted-data",
        "worktree-evidence:constrained",
        f"acceptance:{receipt.decision}",
    )
    build_synthetic_run_trace(
        thread_id=thread_id,
        decision=receipt.decision,
        latency_ms=elapsed_ms,
        audit=audit,
    )
    audit = audit + ("trace:metadata-validated",)
    return ArchitectureSmokeReport(
        decision=receipt.decision,
        audit=audit,
        report=f"{receipt.decision}: {' → '.join(audit)}",
    )
