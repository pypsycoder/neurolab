"""Search reservations must precede network; failure must not become success."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from neurolab.corpus_gap_plan import SEARCH_TEMPLATES
from neurolab.it_research import ItResearchError, ItResearchQuery, ItResearchRun
from tests.test_fulltext_candidate_queue import assessment


class CorpusGapCycleTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("gap_cycle", Path(__file__).resolve().parents[1] / "scripts/run_corpus_gap_cycle.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module.__file__ = str(Path(self.temp.name) / "scripts/run_corpus_gap_cycle.py")
        self.initial, self.reserve, self.finish = (MagicMock() for _ in range(3))
        self.initial.execute.side_effect = [[], []]
        self.reserve.execute.return_value.fetchone.return_value = ("reserved",)
        self.connections = []
        for conn in (self.initial, self.reserve, self.finish):
            cm = MagicMock()
            cm.__enter__.return_value = conn
            self.connections.append(cm)

    def invoke(self, *, execute=True, corpus=(), error=None):
        run = ItResearchRun(ItResearchQuery("agent architecture", 2), "2026-10-03",
                            tuple(a.item for a in corpus), (), "review_required", ())
        output = io.StringIO()
        with patch.object(self.module.psycopg, "connect", side_effect=self.connections), \
             patch.object(self.module, "load_corpus_assessments", return_value=corpus), \
             patch.object(self.module, "run_it_research", return_value=run, side_effect=error) as search, \
             patch.object(self.module, "persist_run") as persist, \
             patch.object(self.module, "record_synthesis_status"), \
             patch.dict("os.environ", {"DATABASE_URL": "synthetic"}), \
             patch("sys.argv", ["gap_cycle"] + (["--execute"] if execute else [])), \
             patch("sys.stdout", output):
            self.module.main()
        return json.loads(output.getvalue()), search, persist

    def test_plan_does_not_reserve_or_search(self):
        output, search, persist = self.invoke(execute=False)
        search.assert_not_called()
        persist.assert_not_called()
        self.reserve.execute.assert_not_called()
        self.assertEqual(output["status"], "planned")

    def test_execution_commits_reservation_and_finishes_redacted_receipt(self):
        def network(*args, **kwargs):
            self.assertTrue(self.connections[1].__exit__.called)
            self.assertEqual(args[0].arxiv_topic_terms, ("agent", "architecture", "orchestration"))
            return ItResearchRun(args[0], "2026-10-03", (), (), "review_required", ())
        output, search, persist = self.invoke(error=network)
        self.assertEqual(search.call_count, 1)
        persist.assert_called_once()
        self.assertEqual(output["status"], "completed")
        self.assertEqual(output["new_model_calls"], 0)
        self.assertFalse(output["full_spec_allowed"])
        receipt = json.loads(self.finish.execute.call_args.args[1][1])
        self.assertNotIn("synthetic", receipt.values())
        self.assertIn("after", receipt)

    def test_parallel_reservation_loser_never_calls_network(self):
        self.reserve.execute.return_value.fetchone.return_value = None
        with self.assertRaisesRegex(RuntimeError, "reservation already taken"):
            self.invoke()
        self.finish.execute.assert_not_called()

    def test_provider_refusal_is_unavailable_not_completed(self):
        output, search, persist = self.invoke(error=ItResearchError("RAW SECRET URL"))
        self.assertEqual(output["status"], "unavailable")
        persist.assert_not_called()
        receipt = json.loads(self.finish.execute.call_args.args[1][1])
        self.assertEqual(receipt["failure_code"], "insufficient_public_provider_evidence")
        self.assertNotIn("RAW SECRET", json.dumps(receipt))

    def test_unknown_failure_remains_reserved_no_false_final_status(self):
        with self.assertRaises(RuntimeError):
            self.invoke(error=RuntimeError("synthetic failure"))
        self.finish.execute.assert_not_called()

    def test_exhausted_catalog_calls_no_provider(self):
        self.initial.execute.side_effect = [[(t.template_id,) for t in SEARCH_TEMPLATES], []]
        output, search, persist = self.invoke()
        search.assert_not_called()
        self.reserve.execute.assert_not_called()
        self.assertIsNone(output["next_search"])
