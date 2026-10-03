import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from neurolab.fulltext_verification import FullTextReceipt, FullTextVerificationError
from neurolab.license_verification import LicenseReceipt, LicenseVerificationError
from tests.test_fulltext_candidate_queue import assessment


class CorpusFulltextTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("fulltext_cycle", Path(__file__).resolve().parents[1] / "scripts/run_corpus_fulltext_preflight.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module.__file__ = str(Path(self.temp.name) / "scripts/run_corpus_fulltext_preflight.py")
        self.initial, self.reserve, self.finish = (MagicMock() for _ in range(3))
        self.initial.execute.side_effect = [[], [], []]
        self.reserve.execute.return_value.fetchone.return_value = ("reserved",)
        self.connections = []
        for conn in (self.initial, self.reserve, self.finish):
            cm = MagicMock()
            cm.__enter__.return_value = conn
            self.connections.append(cm)
        self.item = assessment(key="a" * 64)
        self.licence = LicenseReceipt(self.item.source_key, "arxiv", "https://arxiv.org/abs/2609.12345", "CC-BY-4.0", "b" * 64, "2026-10-03")
        self.document = FullTextReceipt(self.item.source_key, "arxiv", "https://export.arxiv.org/pdf/2609.12345",
                                       "CC-BY-4.0", "c" * 64, 123, 7, "d" * 64, 2000)

    def invoke(self, *, execute=True, license_error=None, pdf_error=None, corpus=None):
        output = io.StringIO()
        def licence_call(*args, **kwargs):
            self.assertTrue(self.connections[1].__exit__.called)
            if license_error:
                raise license_error
            return self.licence
        with patch.object(self.module.psycopg, "connect", side_effect=self.connections), \
             patch.object(self.module, "load_corpus_assessments", return_value=(self.item,) if corpus is None else corpus), \
             patch.object(self.module, "verify_arxiv_license", side_effect=licence_call) as license_api, \
             patch.object(self.module, "verify_open_access_pdf", return_value=self.document, side_effect=pdf_error) as pdf_api, \
             patch.object(self.module, "persist_license_receipt") as save_license, \
             patch.object(self.module, "persist_fulltext_receipt", return_value="document-uuid") as save_pdf, \
             patch.dict("os.environ", {"DATABASE_URL": "synthetic"}), \
             patch("sys.argv", ["preflight"] + (["--execute"] if execute else [])), \
             patch("sys.stdout", output):
            self.module.main()
        return json.loads(output.getvalue()), license_api, pdf_api, save_license, save_pdf

    def test_plan_calls_no_network(self):
        result, lic, pdf, sl, sp = self.invoke(execute=False)
        lic.assert_not_called()
        pdf.assert_not_called()
        self.reserve.execute.assert_not_called()
        self.assertEqual(result["status"], "planned")

    def test_license_refusal_never_downloads_or_persists_pdf(self):
        result, lic, pdf, sl, sp = self.invoke(license_error=LicenseVerificationError("RAW SECRET"))
        pdf.assert_not_called()
        sl.assert_not_called()
        sp.assert_not_called()
        self.assertEqual(result["status"], "license_unverified")
        self.assertNotIn("RAW SECRET", json.dumps(result))

    def test_success_calls_existing_legal_route_and_leaves_spec_blocked(self):
        result, lic, pdf, sl, sp = self.invoke()
        lic.assert_called_once()
        self.assertEqual(pdf.call_args.args[0].license_id, "CC-BY-4.0")
        sl.assert_called_once()
        sp.assert_called_once()
        self.assertEqual(result["pdf_sha256"], "c" * 64)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["new_model_calls"], 0)
        self.assertFalse(result["full_spec_allowed"])

    def test_pdf_failure_keeps_license_but_no_false_document(self):
        result, lic, pdf, sl, sp = self.invoke(pdf_error=FullTextVerificationError("RAW URL"))
        sl.assert_called_once()
        sp.assert_not_called()
        self.assertEqual(result["status"], "document_unverified")
        self.assertNotIn("RAW URL", json.dumps(result))

    def test_reserved_parallel_loser_does_no_network(self):
        self.reserve.execute.return_value.fetchone.return_value = None
        with self.assertRaisesRegex(RuntimeError, "reservation already taken"):
            self.invoke()
        self.finish.execute.assert_not_called()

    def test_unknown_failure_preserves_inflight(self):
        with self.assertRaises(RuntimeError):
            self.invoke(license_error=RuntimeError("unknown"))
        self.finish.execute.assert_not_called()

    def test_exhausted_queue_stops_without_manufactured_permission(self):
        result, lic, pdf, sl, sp = self.invoke(corpus=())
        lic.assert_not_called()
        self.reserve.execute.assert_not_called()
        self.assertEqual(result["status"], "queue_exhausted")
