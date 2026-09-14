"""Tests for the default-deny synthetic agent role policy."""

import unittest

from neurolab.agent_roles import (
    AgentRolePolicyError,
    allowed_actions,
    require_allowed_action,
    required_role_actions,
)


class AgentRolePolicyTests(unittest.TestCase):
    def test_minimal_architecture_path_is_explicitly_allowed(self):
        for role, action in required_role_actions():
            require_allowed_action(role, action)

    def test_each_role_receives_only_its_own_actions(self):
        self.assertEqual(allowed_actions("developer"), {"engineering.worktree.edit"})
        with self.assertRaises(AgentRolePolicyError):
            require_allowed_action("developer", "engineering.worktree.test")
        with self.assertRaises(AgentRolePolicyError):
            require_allowed_action("tester", "engineering.worktree.edit")

    def test_unknown_and_sensitive_actions_are_default_denied(self):
        for role, action in (
            ("developer", "shell.exec"),
            ("supervisor", "git.push"),
            ("reviewer", "deployment.production"),
            ("researcher", "secrets.read"),
            ("unknown", "workflow.route"),
            ("tester", "../malformed"),
        ):
            with self.assertRaises(AgentRolePolicyError):
                require_allowed_action(role, action)
