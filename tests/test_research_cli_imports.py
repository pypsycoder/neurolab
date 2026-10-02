"""Offline entrypoint imports must work before a paid live provider invocation."""
import importlib.util
from pathlib import Path
import unittest


class ResearchEntrypointImports(unittest.TestCase):
    def test_model_entrypoints_import_without_calling_provider(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("run_gigachat_document_card", "run_gigachat_diagram_cards", "run_experimental_spec"):
            with self.subTest(name=name):
                spec = importlib.util.spec_from_file_location(name, root / "scripts" / (name + ".py"))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertTrue(callable(module.main))
