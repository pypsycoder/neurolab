"""Regression tests for the always-on control-plane worker."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql://example.invalid/neuro_lab")


def load_worker():
    sys.modules.pop("control_plane_worker", None)
    spec = importlib.util.spec_from_file_location(
        "control_plane_worker", ROOT / "orchestrator" / "worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeQueue:
    def __init__(self):
        self.pushed = []

    def rpush(self, key, value):
        self.pushed.append((key, value))

    def eval(self, script, keys, *args):
        self.eval_call = (script, keys, args)
        return 1


class ControlPlaneWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = load_worker()

    def test_millisecond_expiry_is_normalized_and_refreshed_before_expiry(self):
        client = self.worker.GigaChatClient()
        client.credential_for = Mock(return_value="credential")
        client.request_json = Mock(
            side_effect=[
                {"access_token": "first", "expires_at": 1_700_001_800_000},
                {"access_token": "second", "expires_at": 1_700_003_600_000},
            ]
        )

        with patch.object(self.worker.time, "time", return_value=1_700_000_000):
            self.assertEqual(client.access_token("primary"), "first")
        self.assertEqual(client.tokens["primary"]["expires_at"], 1_700_001_800)

        with patch.object(self.worker.time, "time", return_value=1_700_001_770):
            self.assertEqual(client.access_token("primary"), "second")
        self.assertEqual(client.request_json.call_count, 2)

    def test_exp_seconds_is_accepted(self):
        client = self.worker.GigaChatClient()
        client.credential_for = Mock(return_value="credential")
        client.request_json = Mock(return_value={"access_token": "token", "exp": 1_700_003_600})
        with patch.object(self.worker.time, "time", return_value=1_700_000_000):
            self.assertEqual(client.access_token("primary"), "token")
        self.assertEqual(client.tokens["primary"]["expires_at"], 1_700_003_600)

    def test_401_refreshes_cached_token_once(self):
        client = self.worker.GigaChatClient()
        client.access_token = Mock(side_effect=["old", "new"])
        client.request_json = Mock(
            side_effect=[
                self.worker.ProviderError("completion failed: 401", status_code=401),
                {"ok": True},
            ]
        )
        captured = []

        result = client.authorized_request_json(
            "primary", lambda token: captured.append(token) or token, "completion", 1
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured, ["old", "new"])
        self.assertEqual(client.request_json.call_count, 2)

    def test_malformed_delivery_goes_to_dead_letter_without_db_access(self):
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue

        self.assertTrue(self.worker.handle_delivery("not json"))
        self.assertEqual(fake_queue.pushed, [(self.worker.DEAD_LETTER_QUEUE, "not json")])

    def test_unexpected_exception_is_not_exposed_as_a_database_error(self):
        self.worker.heartbeat = Mock()
        self.worker.claim_task = Mock(return_value="00000000-0000-0000-0000-000000000002")
        self.worker.gigachat.complete = Mock(side_effect=RuntimeError("postgresql://secret@host"))
        recorded = []
        self.worker.record_failed = Mock(side_effect=lambda task_id, execution_id, exc: recorded.append(exc))

        with self.assertLogs("neuro_lab.worker", level="ERROR") as captured:
            self.assertTrue(
                self.worker.handle_delivery('{"task_id":"00000000-0000-0000-0000-000000000001","provider":"gigachat"}')
            )
        self.assertEqual(self.worker.safe_error_message(recorded[0]), "internal error: RuntimeError")
        self.assertNotIn("secret@host", "\n".join(captured.output))

    def test_delivery_is_retained_when_failure_cannot_be_persisted(self):
        self.worker.heartbeat = Mock()
        self.worker.claim_task = Mock(side_effect=RuntimeError("database unavailable"))
        self.worker.record_failed = Mock(side_effect=RuntimeError("database unavailable"))

        self.assertFalse(
            self.worker.handle_delivery('{"task_id":"00000000-0000-0000-0000-000000000001","provider":"gigachat"}')
        )

    def test_duplicate_delivery_is_acknowledged_without_a_provider_call(self):
        self.worker.heartbeat = Mock()
        self.worker.claim_task = Mock(return_value=None)
        self.worker.gigachat.complete = Mock()

        self.assertTrue(
            self.worker.handle_delivery('{"task_id":"00000000-0000-0000-0000-000000000001","provider":"gigachat"}')
        )
        self.worker.gigachat.complete.assert_not_called()

    def test_recovery_moves_exact_processing_payload_atomically(self):
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue

        self.assertEqual(self.worker.requeue_stale_delivery('{"task_id":"id"}'), 1)
        self.assertEqual(fake_queue.eval_call[1], 2)
        self.assertEqual(
            fake_queue.eval_call[2],
            (self.worker.PROCESSING_QUEUE, self.worker.TASK_QUEUE, '{"task_id":"id"}'),
        )


if __name__ == "__main__":
    unittest.main()
