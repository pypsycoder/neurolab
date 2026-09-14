"""Tests for synthetic tamper-evident role hand-off receipts."""

from dataclasses import replace
import unittest

from neurolab.agent_receipts import (
    AgentReceiptPolicyError,
    append_transition,
    new_transition_receipt,
    verify_transition_receipt,
)
from neurolab.agent_transitions import RoleTransition, required_transitions


class AgentReceiptPolicyTests(unittest.TestCase):
    def test_complete_ordered_chain_is_verified(self):
        receipt = new_transition_receipt()
        for transition in required_transitions():
            receipt = append_transition(receipt, transition)

        verify_transition_receipt(receipt)
        self.assertEqual(receipt.state, "reported")
        self.assertEqual(len(receipt.transitions), 5)

    def test_skipped_or_out_of_order_transition_is_denied(self):
        receipt = new_transition_receipt()
        skipped = tuple(required_transitions())[1]
        with self.assertRaises(AgentReceiptPolicyError):
            append_transition(receipt, skipped)

    def test_altered_state_or_transition_is_detected(self):
        receipt = new_transition_receipt()
        first = tuple(required_transitions())[0]
        receipt = append_transition(receipt, first)
        for altered in (
            replace(receipt, state="reported"),
            replace(
                receipt,
                transitions=(
                    RoleTransition("planned", "reviewed", "reviewer", "engineering.diff.review"),
                ),
            ),
        ):
            with self.assertRaises(AgentReceiptPolicyError):
                verify_transition_receipt(altered)
