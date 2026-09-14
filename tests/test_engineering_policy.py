"""Tests for the no-merge engineering-agent acceptance gate."""

import unittest

from neurolab.engineering_policy import EngineeringPolicyError, require_reviewable_change


class EngineeringPolicyTests(unittest.TestCase):
    def test_narrow_passing_change_requires_human_review(self):
        receipt = require_reviewable_change(
            changed_paths=["openhands_eval_fixture/calculator.py"],
            allowed_paths=["openhands_eval_fixture/calculator.py"],
            test_command="python3 -m unittest discover -s openhands_eval_fixture",
            test_exit_code=0,
        )
        self.assertEqual(receipt.decision, "review_required")
        self.assertEqual(receipt.changed_paths, ("openhands_eval_fixture/calculator.py",))

    def test_out_of_scope_or_traversal_change_is_rejected(self):
        with self.assertRaises(EngineeringPolicyError):
            require_reviewable_change(
                changed_paths=["compose.yaml"],
                allowed_paths=["openhands_eval_fixture/calculator.py"],
                test_command="python3 -m unittest",
                test_exit_code=0,
            )
        with self.assertRaises(EngineeringPolicyError):
            require_reviewable_change(
                changed_paths=["openhands_eval_fixture/../.env"],
                allowed_paths=["openhands_eval_fixture/calculator.py"],
                test_command="python3 -m unittest",
                test_exit_code=0,
            )

    def test_failing_or_missing_test_evidence_is_rejected(self):
        for command, exit_code in [("", 0), ("python3 -m unittest", 1)]:
            with self.assertRaises(EngineeringPolicyError):
                require_reviewable_change(
                    changed_paths=["openhands_eval_fixture/calculator.py"],
                    allowed_paths=["openhands_eval_fixture/calculator.py"],
                    test_command=command,
                    test_exit_code=exit_code,
                )
