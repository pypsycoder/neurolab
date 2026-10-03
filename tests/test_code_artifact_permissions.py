import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("code_runner", Path(__file__).resolve().parents[1] / "scripts/run_experimental_code.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CodeArtifactPermissionsTests(unittest.TestCase):
    def test_redacted_artifact_has_explicit_non_root_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            with patch.object(runner.os, "chown", create=True) as chown:
                runner.publish_artifact(path, b'{"status":"synthetic"}\n')
            chown.assert_called_once_with(path, 1000, 1000)
            self.assertEqual(path.read_bytes(), b'{"status":"synthetic"}\n')
