import unittest

from neurolab.workflow import build_smoke_graph, run_smoke_task


class WorkflowTests(unittest.TestCase):
    def test_research_without_evidence_trace_is_blocked(self):
        state = run_smoke_task("synthetic research", "research", thread_id="no-trace")
        self.assertEqual(state["status"], "blocked")
        self.assertIn("blocked:no-evidence-trace", state["audit"])

    def test_engineering_path_validates(self):
        state = run_smoke_task("synthetic code change", "engineering", thread_id="code")
        self.assertEqual(state["status"], "validated")
        self.assertEqual(state["audit"][:3], ["plan", "execute", "validate"])

    def test_cancel_stops_before_execution(self):
        state = run_smoke_task("cancel", "engineering", thread_id="cancel", cancelled=True)
        self.assertEqual(state["status"], "cancelled")
        self.assertNotIn("execute", state["audit"])

    def test_checkpoint_retains_final_state_for_thread(self):
        graph = build_smoke_graph()
        config = {"configurable": {"thread_id": "checkpoint"}}
        graph.invoke(
            {"task": "synthetic code change", "kind": "engineering", "max_steps": 3},
            config,
        )
        self.assertEqual(graph.get_state(config).values["status"], "validated")
