"""Fail-closed limits for the local-only synthetic architecture scenario."""

from dataclasses import dataclass


class AgentBudgetPolicyError(ValueError):
    """Observed synthetic run metadata exceeds or violates the declared budget."""


@dataclass(frozen=True)
class SyntheticRunBudget:
    """Bounded metadata limits; no provider billing or runtime control is implied."""

    max_transitions: int
    max_elapsed_ms: int
    max_external_calls: int
    max_cost_units: int


SYNTHETIC_ARCHITECTURE_BUDGET = SyntheticRunBudget(
    max_transitions=5,
    max_elapsed_ms=5_000,
    max_external_calls=0,
    max_cost_units=0,
)


def require_within_budget(
    *,
    transitions: int,
    elapsed_ms: int,
    external_calls: int,
    cost_units: int,
    budget: SyntheticRunBudget = SYNTHETIC_ARCHITECTURE_BUDGET,
) -> None:
    """Accept only non-negative observed metadata within all declared limits."""
    observed = {
        "transitions": transitions,
        "elapsed_ms": elapsed_ms,
        "external_calls": external_calls,
        "cost_units": cost_units,
    }
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in observed.values()):
        raise AgentBudgetPolicyError("budget metadata must be non-negative integers")

    limits = {
        "transitions": budget.max_transitions,
        "elapsed_ms": budget.max_elapsed_ms,
        "external_calls": budget.max_external_calls,
        "cost_units": budget.max_cost_units,
    }
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in limits.values()):
        raise AgentBudgetPolicyError("budget limits must be non-negative integers")
    if any(observed[name] > limit for name, limit in limits.items()):
        raise AgentBudgetPolicyError("synthetic run exceeded its declared budget")
