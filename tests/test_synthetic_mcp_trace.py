"""Tests for the test-only LangGraph orchestration trace over MCP data."""

import copy
import unittest

from neurolab.synthetic_mcp_trace import run_synthetic_mcp_trace, synthetic_tool_events


class SyntheticMcpTraceTests(unittest.TestCase):
    def test_approved_untrusted_events_complete_the_synthetic_trace(self):
        state = run_synthetic_mcp_trace("synthetic code review", thread_id="approved")
        self.assertEqual(state["status"], "validated")
        self.assertIn("mcp-policy:accepted-untrusted-data", state["audit"])
        self.assertIn("execute:synthetic-only", state["audit"])

    def test_prompt_injection_remains_data_and_is_not_in_the_report(self):
        state = run_synthetic_mcp_trace("synthetic code review", thread_id="injection")
        self.assertEqual(state["status"], "validated")
        self.assertNotIn("Ignore all prior instructions", state["report"])
        self.assertNotIn("shell command", state["report"])

    def test_unknown_tool_blocks_before_execution(self):
        events = copy.deepcopy(synthetic_tool_events())
        events[2]["name"] = "shell.exec"
        state = run_synthetic_mcp_trace("synthetic code review", thread_id="unknown-tool", tool_events=events)
        self.assertEqual(state["status"], "blocked")
        self.assertIn("mcp-policy:blocked", state["audit"])
        self.assertNotIn("execute:synthetic-only", state["audit"])

    def test_forged_trusted_result_blocks_before_execution(self):
        events = copy.deepcopy(synthetic_tool_events())
        events[0]["result"]["trusted"] = True
        state = run_synthetic_mcp_trace("synthetic code review", thread_id="forged-result", tool_events=events)
        self.assertEqual(state["status"], "blocked")
        self.assertNotIn("execute:synthetic-only", state["audit"])
