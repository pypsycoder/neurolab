import tempfile
from pathlib import Path
import unittest
from neurolab.code_diagnostics import static_diagnostics, project_diagnostics


class CodeDiagnosticTests(unittest.TestCase):
    def test_undefined_name_is_located_without_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'candidate.py'
            source.write_text('def affected_nodes(edges, failed):\n    return Edges\n')
            self.assertEqual(static_diagnostics(source), [{'code': 'F821', 'line': 2, 'column': 12}])

    def test_clean_source_and_raw_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'candidate.py'
            source.write_text('def affected_nodes(edges, failed):\n    return [failed]\n')
            self.assertEqual(static_diagnostics(source), [])
        result = project_diagnostics([{'code': 'F821', 'location': {'row': 6, 'column': 12}, 'message': 'raw name', 'filename': '/private/path'}])
        self.assertEqual(result, [{'code': 'F821', 'line': 6, 'column': 12}])

    def test_invalid_diagnostics_rejected(self):
        for items in ([{'code': 'E501', 'location': {'row': 2, 'column': 1}}], [{'code': 'F821', 'location': {'row': True, 'column': 1}}]):
            with self.assertRaises(ValueError):
                project_diagnostics(items)
