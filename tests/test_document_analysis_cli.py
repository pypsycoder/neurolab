import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import sys
from unittest.mock import Mock


class DocumentAskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("document_analysis_cli", Path(__file__).resolve().parents[1] / "scripts/run_gigachat_document_card.py")
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        cls.addClassCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(cls.module)

    def test_usage_captured_before_schema_failure_and_native_schema_used(self):
        client = Mock()
        client.chat.return_value = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=123, completion_tokens=5, total_tokens=128),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"invalid":"RAW SECRET"}'))])
        meta = {}
        with self.assertRaises(ValueError):
            self.module._ask(client, "synthetic", self.module._WindowResponse, metadata=meta)
        self.assertEqual(meta["provider_tokens"]["total_tokens"], 128)
        request = client.chat.call_args.args[0]
        self.assertEqual(request.max_tokens, 2048)
        self.assertIsNotNone(request.response_format)
        self.assertNotIn("RAW", str(meta))

    def test_non_stop_and_missing_usage_fail_closed_not_zero(self):
        for finish in ("length", "blacklist", None):
            client = Mock()
            client.chat.return_value = SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=finish)])
            meta = {}
            with self.assertRaises(ValueError):
                self.module._ask(client, "synthetic", self.module._WindowResponse, metadata=meta)
            self.assertIsNone(meta["provider_tokens"]["total_tokens"])
