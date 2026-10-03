import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from neurolab.document_analysis_cache import AnalysisOutcomeUnknown, run_cached_step, step_key
from neurolab.document_cards import parse_window_note, plan_page_windows


PAYLOAD = {"summary": "Структурированная заметка описывает экспериментальный компонент системы.",
           "architecture_layers": ["component"], "implementation_signals": [],
           "evaluation_signals": [], "limitations": ["Независимая проверка результатов не выполнена."]}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.window = plan_page_windows(("RAW PDF SECRET",))[0]
        self.validate = lambda raw: parse_window_note(raw, window=self.window)
        self.key = step_key(document_sha256="a" * 64, model_label="GigaChat-2-Pro", prompt="RAW PROMPT SECRET")
        self.ask = Mock(return_value=json.dumps(PAYLOAD))

    def run_step(self, ask=None):
        meta = {"new_model_calls": 0}
        result = run_cached_step(self.path, self.key, meta, ask or self.ask, self.validate)
        return result, meta

    def test_completed_output_reused_without_model_and_no_raw_input_retained(self):
        first, meta = self.run_step()
        second, reused = self.run_step()
        self.assertEqual(first, second)
        self.ask.assert_called_once()
        self.assertEqual(reused["new_model_calls"], 0)
        content = (self.path / (self.key + ".json")).read_text()
        self.assertNotIn("RAW", content)
        self.assertEqual(meta["new_model_calls"], 1)

    def test_unknown_provider_outcome_is_never_automatically_repeated(self):
        with self.assertRaises(TimeoutError):
            self.run_step(Mock(side_effect=TimeoutError("RAW SECRET")))
        with self.assertRaises(AnalysisOutcomeUnknown):
            self.run_step()
        self.ask.assert_not_called()
        self.assertNotIn("RAW SECRET", (self.path / (self.key + ".json")).read_text())

    def test_definite_quota_refusal_allows_one_second_attempt_only(self):
        error = type("RateLimitError", (Exception,), {})("RAW QUOTA")
        refused = Mock(side_effect=error)
        for _ in range(2):
            with self.assertRaises(type(error)):
                self.run_step(refused)
        with self.assertRaises(AnalysisOutcomeUnknown):
            self.run_step()
        self.assertEqual(refused.call_count, 2)

    def test_quota_then_second_lane_success_reuses_completed_step(self):
        error = type("RateLimitError", (Exception,), {})()
        with self.assertRaises(type(error)):
            self.run_step(Mock(side_effect=error))
        self.run_step()
        self.run_step()
        self.ask.assert_called_once()

    def test_corrupt_cache_and_stale_parallel_lock_are_refused(self):
        self.run_step()
        path = self.path / (self.key + ".json")
        entry = json.loads(path.read_text())
        entry["validated_output"]["summary"] = "bad"
        path.write_text(json.dumps(entry))
        with self.assertRaises(ValueError):
            self.run_step()
        self.assertEqual(self.ask.call_count, 1)
        (self.path / (self.key + ".lock")).touch()
        with self.assertRaises(AnalysisOutcomeUnknown):
            self.run_step()

    def test_validation_failure_does_not_cache_raw_answer_or_enable_replay(self):
        with self.assertRaises(ValueError):
            self.run_step(Mock(return_value='{"raw":"SECRET"}'))
        content = (self.path / (self.key + ".json")).read_text()
        self.assertNotIn("SECRET", content)
        with self.assertRaises(AnalysisOutcomeUnknown):
            self.run_step()

    def test_key_changes_with_model_document_prompt(self):
        for kw in ({"model_label": "GigaChat-2-Max"}, {"document_sha256": "b" * 64}, {"prompt": "different"}):
            base = dict(document_sha256="a" * 64, model_label="GigaChat-2-Pro", prompt="RAW PROMPT SECRET")
            base.update(kw)
            self.assertNotEqual(self.key, step_key(**base))
