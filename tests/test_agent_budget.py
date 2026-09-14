"""Tests for bounded metadata of the local-only synthetic architecture run."""

import unittest

from neurolab.agent_budget import AgentBudgetPolicyError, require_within_budget


class AgentBudgetPolicyTests(unittest.TestCase):
    def test_exact_synthetic_budget_is_allowed(self):
        require_within_budget(
            transitions=5, elapsed_ms=5_000, external_calls=0, cost_units=0
        )

    def test_any_budget_limit_exceeded_is_denied(self):
        for values in (
            {"transitions": 6, "elapsed_ms": 1, "external_calls": 0, "cost_units": 0},
            {"transitions": 5, "elapsed_ms": 5_001, "external_calls": 0, "cost_units": 0},
            {"transitions": 5, "elapsed_ms": 1, "external_calls": 1, "cost_units": 0},
            {"transitions": 5, "elapsed_ms": 1, "external_calls": 0, "cost_units": 1},
        ):
            with self.assertRaises(AgentBudgetPolicyError):
                require_within_budget(**values)

    def test_negative_or_boolean_metadata_is_denied(self):
        for values in (
            {"transitions": -1, "elapsed_ms": 1, "external_calls": 0, "cost_units": 0},
            {"transitions": 5, "elapsed_ms": True, "external_calls": 0, "cost_units": 0},
        ):
            with self.assertRaises(AgentBudgetPolicyError):
                require_within_budget(**values)
