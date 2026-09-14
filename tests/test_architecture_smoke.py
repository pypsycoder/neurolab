"""Tests for the deterministic synthetic architecture smoke receipt."""

import unittest

from neurolab.architecture_smoke import run_architecture_smoke
from neurolab.engineering_policy import EngineeringPolicyError


class ArchitectureSmokeTests(unittest.TestCase):
    def test_validated_contracts_produce_review_only_receipt(self):
        state = run_architecture_smoke(
            task="synthetic architecture smoke",
            thread_id="architecture-smoke-approved",
            changed_paths=["openhands_eval_fixture/calculator.py"],
            allowed_paths=["openhands_eval_fixture/calculator.py"],
            test_command="python3 -B -m unittest discover -s openhands_eval_fixture",
            test_exit_code=0,
        )
        self.assertEqual(state.decision, "review_required")
        self.assertEqual(
            state.audit,
            (
                "workflow:validated",
                "roles:default-deny",
                "transitions:forward-only",
                "receipt:verified-chain",
                "receipt:complete",
                "budget:within-limits",
                "mcp-policy:accepted-untrusted-data",
                "worktree-evidence:constrained",
                "acceptance:review_required",
            ),
        )

    def test_out_of_scope_worktree_evidence_is_rejected(self):
        with self.assertRaises(EngineeringPolicyError):
            run_architecture_smoke(
                task="synthetic architecture smoke",
                thread_id="architecture-smoke-rejected",
                changed_paths=["compose.yaml"],
                allowed_paths=["openhands_eval_fixture/calculator.py"],
                test_command="python3 -B -m unittest discover -s openhands_eval_fixture",
                test_exit_code=0,
            )

    def test_report_never_includes_untrusted_fixture_content(self):
        state = run_architecture_smoke(
            task="synthetic architecture smoke",
            thread_id="architecture-smoke-report",
            changed_paths=["openhands_eval_fixture/calculator.py"],
            allowed_paths=["openhands_eval_fixture/calculator.py"],
            test_command="python3 -B -m unittest discover -s openhands_eval_fixture",
            test_exit_code=0,
        )
        self.assertNotIn("Ignore all prior instructions", state.report)
        self.assertNotIn("shell command", state.report)
