import tempfile
import unittest
from pathlib import Path
from neurolab.experimental_code import BASELINE, validate_code_asset, build_code_task
from neurolab.experimental_spec import DraftSpec
from test_experimental_spec import raw_draft


class ExperimentalCodeTests(unittest.TestCase):
    def test_task_has_fixed_permissions_not_shell_from_spec(self):
        task = build_code_task(DraftSpec.model_validate(raw_draft()))
        self.assertIn('ONLY /workspace/experiment/provenance.py', task)
        self.assertIn('not mounted', task)

    def test_asset_has_single_regular_bounded_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); target = root / 'provenance.py'
            target.write_text(BASELINE)
            self.assertEqual(len(validate_code_asset(root)[1]), 64)
            (root / 'extra.py').write_text('pass')
            with self.assertRaises(ValueError):
                validate_code_asset(root)

    def test_import_and_introspection_rejected_before_evaluator(self):
        for prefix in ('import os\n', 'from pathlib import Path\n', 'x = open("x")\n', 'x = (1).__class__\n', 'x = globals()\n'):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); (root/'provenance.py').write_text(prefix + BASELINE)
                with self.assertRaises(ValueError):
                    validate_code_asset(root)

    def test_frozen_evaluator_rejects_baseline(self):
        import importlib.util
        path = Path(__file__).parent/'fixtures/provenance_evaluator.py'
        spec = importlib.util.spec_from_file_location('frozen',path)
        evaluator = importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluator)
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp)/'provenance.py'; candidate.write_text(BASELINE)
            result = evaluator.evaluate(candidate)
        self.assertEqual(result['total'], 11)
        self.assertEqual(result['passed'], 0)
