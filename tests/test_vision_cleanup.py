"""Provider failure and upload cleanup must never become partial-batch success."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location("vision_cli", Path(__file__).resolve().parents[1] / "scripts/run_gigachat_diagram_cards.py")
vision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vision)


class Client:
    def __init__(self, *, chat_error=None, cleanup_error=None, finish_reason="stop", content="malformed"):
        self.chat_error = chat_error
        self.cleanup_error = cleanup_error
        self.deleted = []
        self.finish_reason = finish_reason
        self.content = content
        self.requests = []

    def upload_file(self, *args, **kwargs):
        return SimpleNamespace(id_="ephemeral-upload")

    def chat(self, *args, **kwargs):
        self.requests.append(args[0])
        if self.chat_error:
            raise self.chat_error
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=self.finish_reason, message=SimpleNamespace(content=self.content))])

    def delete_file(self, file_id):
        self.deleted.append(file_id)
        if self.cleanup_error:
            raise self.cleanup_error


class VisionCleanupTests(unittest.TestCase):
    def test_complete_json_with_non_stop_reason_is_never_accepted(self):
        raw = json.dumps(dict(diagram_kind="other", summary="Synthetic diagram", components=[], connections=[], feedback_or_control=[], limitations=[]))
        for reason in ("length", "blacklist", None):
            with self.subTest(reason=reason):
                client = Client(finish_reason=reason, content=raw)
                with self.assertRaises(vision.DiagramCardError):
                    vision._vision(client, "synthetic", b"image", 1)
                self.assertEqual(client.deleted, ["ephemeral-upload"])

    def test_native_attachment_and_output_limit_are_preserved(self):
        raw = json.dumps(dict(diagram_kind="other", summary="Synthetic diagram", components="Component", connections=[], feedback_or_control=[], limitations=[]))
        client = Client(content=raw)
        parsed = json.loads(vision._vision(client, "synthetic", b"image", 1))
        self.assertEqual(parsed["components"], ["Component"])
        self.assertEqual(client.requests[0].max_tokens, 2048)
        self.assertEqual(client.requests[0].messages[0].attachments, ["ephemeral-upload"])
        self.assertEqual(client.deleted, ["ephemeral-upload"])

    def test_oversized_response_is_rejected_and_upload_deleted(self):
        client = Client(content="x" * 24001)
        with self.assertRaises(vision.DiagramCardError):
            vision._vision(client, "synthetic", b"image", 1)
        self.assertEqual(client.deleted, ["ephemeral-upload"])

    def test_quota_propagates_after_cleanup(self):
        error = RuntimeError("provider-body")
        error.status_code = 429
        client = Client(chat_error=error)
        metadata = {}
        with self.assertRaises(RuntimeError) as failed:
            vision._vision(client, "synthetic", b"image", 1, metadata=metadata)
        self.assertIs(failed.exception, error)
        self.assertEqual(client.deleted, ["ephemeral-upload"])
        self.assertEqual(metadata, {"model_calls": 1, "temporary_upload_deleted": True})
        self.assertNotIn("provider-body", json.dumps(metadata))

    def test_bad_json_is_recoverable_but_cleanup_failure_is_not(self):
        client = Client()
        with self.assertRaises(vision.DiagramCardError):
            vision._vision(client, "synthetic", b"image", 1)
        self.assertEqual(client.deleted, ["ephemeral-upload"])
        client = Client(cleanup_error=ValueError("private-provider-body"))
        with self.assertRaises(vision.TemporaryUploadCleanupError) as failed:
            vision._vision(client, "synthetic", b"image", 1)
        self.assertNotIn("private-provider-body", str(failed.exception))
