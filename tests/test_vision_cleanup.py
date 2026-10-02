"""Provider failure and upload cleanup must never become partial-batch success."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location("vision_cli", Path(__file__).resolve().parents[1] / "scripts/run_gigachat_diagram_cards.py")
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)


class Client:
    def __init__(self, *, chat_error=None, cleanup_error=None):
        self.chat_error = chat_error
        self.cleanup_error = cleanup_error
        self.deleted = []

    def upload_file(self, *args, **kwargs):
        return SimpleNamespace(id_="ephemeral-upload")

    def chat(self, *args, **kwargs):
        if self.chat_error:
            raise self.chat_error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="malformed"))])

    def delete_file(self, file_id):
        self.deleted.append(file_id)
        if self.cleanup_error:
            raise self.cleanup_error


class VisionCleanupTests(unittest.TestCase):
    def test_quota_propagates_after_cleanup(self):
        error = RuntimeError("provider-body")
        error.status_code = 429
        client = Client(chat_error=error)
        with self.assertRaises(RuntimeError) as failed:
            vision._vision(client, "synthetic", b"image", 1)
        self.assertIs(failed.exception, error)
        self.assertEqual(client.deleted, ["ephemeral-upload"])

    def test_bad_json_is_recoverable_but_cleanup_failure_is_not(self):
        client = Client()
        with self.assertRaises(vision.DiagramCardError):
            vision._vision(client, "synthetic", b"image", 1)
        self.assertEqual(client.deleted, ["ephemeral-upload"])
        client = Client(cleanup_error=ValueError("private-provider-body"))
        with self.assertRaises(vision.TemporaryUploadCleanupError) as failed:
            vision._vision(client, "synthetic", b"image", 1)
        self.assertNotIn("private-provider-body", str(failed.exception))
