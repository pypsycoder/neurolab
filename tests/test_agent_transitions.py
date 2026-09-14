"""Tests for default-deny hand-offs in the synthetic agent graph."""

import unittest

from neurolab.agent_transitions import (
    AgentTransitionPolicyError,
    require_allowed_transition,
    required_transitions,
)


class AgentTransitionPolicyTests(unittest.TestCase):
    def test_minimal_forward_path_is_explicitly_allowed(self):
        for transition in required_transitions():
            require_allowed_transition(
                from_state=transition.from_state,
                to_state=transition.to_state,
                role=transition.role,
                action=transition.action,
            )

    def test_skipped_and_reversed_states_are_denied(self):
        for request in (
            ("planned", "worktree_edited", "developer", "engineering.worktree.edit"),
            ("tested", "worktree_edited", "tester", "engineering.worktree.test"),
            ("reviewed", "reported", "reviewer", "engineering.diff.review"),
        ):
            with self.assertRaises(AgentTransitionPolicyError):
                require_allowed_transition(
                    from_state=request[0],
                    to_state=request[1],
                    role=request[2],
                    action=request[3],
                )

    def test_wrong_role_action_and_unknown_states_are_denied(self):
        for request in (
            ("routed", "worktree_edited", "tester", "engineering.worktree.test"),
            ("routed", "tested", "developer", "engineering.worktree.edit"),
            ("unknown", "routed", "supervisor", "workflow.route"),
        ):
            with self.assertRaises(AgentTransitionPolicyError):
                require_allowed_transition(
                    from_state=request[0],
                    to_state=request[1],
                    role=request[2],
                    action=request[3],
                )
