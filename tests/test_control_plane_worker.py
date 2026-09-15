"""Regression tests for the always-on control-plane worker."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


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

    def lrem(self, key, count, value):
        self.lrem_call = (key, count, value)
        return 1

    def lrange(self, key, start, end):
        return []


class FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.queries = []

    def execute(self, query, params):
        self.queries.append((query, params))

    def fetchone(self):
        return next(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True


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

    def test_semantically_invalid_lane_goes_to_dead_letter_without_db_access(self):
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue

        self.assertTrue(self.worker.handle_delivery('{"provider":"gigachat","credential_lane":"local"}'))
        self.assertEqual(fake_queue.pushed, [(self.worker.DEAD_LETTER_QUEUE, '{"provider":"gigachat","credential_lane":"local"}')])

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

    def test_provider_cost_is_recorded_even_when_completion_loses_lease(self):
        task_id = "00000000-0000-0000-0000-000000000001"
        execution_id = "00000000-0000-0000-0000-000000000002"
        self.worker.heartbeat = Mock()
        self.worker.claim_task = Mock(return_value=execution_id)
        self.worker.gigachat.complete = Mock(return_value={
            "model": "GigaChat-test",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            "credential_lane": "primary",
        })
        self.worker.record_cost = Mock()
        self.worker.record_succeeded = Mock(return_value=False)

        self.assertTrue(self.worker.handle_delivery(
            '{"task_id":"%s","provider":"gigachat"}' % task_id
        ))

        self.worker.record_cost.assert_called_once_with(
            task_id, execution_id, "gigachat", "GigaChat-test",
            {"prompt_tokens": 3, "completion_tokens": 2}, "primary",
        )
        self.worker.record_succeeded.assert_called_once()

    def test_delivery_task_ids_reads_both_durable_queues_and_ignores_bad_payloads(self):
        queued_id = "00000000-0000-0000-0000-000000000007"
        processing_id = "00000000-0000-0000-0000-000000000008"
        fake_queue = FakeQueue()
        fake_queue.lrange = Mock(side_effect=[
            ['{"task_id":"%s","provider":"local-smoke-test"}' % queued_id, "not json"],
            ['{"task_id":"%s","provider":"local-smoke-test"}' % processing_id],
        ])
        self.worker.queue = fake_queue

        self.assertEqual(self.worker.delivery_task_ids(), {queued_id, processing_id})

    def test_outbox_claim_is_published_then_acknowledged(self):
        task_id = "00000000-0000-0000-0000-000000000009"
        claim_id = "00000000-0000-0000-0000-000000000010"
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue
        self.worker.mark_outbox_delivered = Mock(return_value=True)

        self.assertTrue(self.worker.publish_outbox_claim(
            task_id,
            {"task_id": task_id, "provider": "local-smoke-test"},
            claim_id,
        ))

        self.assertEqual(fake_queue.pushed, [
            (self.worker.TASK_QUEUE, '{"task_id": "00000000-0000-0000-0000-000000000009", "provider": "local-smoke-test"}')
        ])
        self.worker.mark_outbox_delivered.assert_called_once_with(task_id, claim_id)

    def test_terminal_outbox_cleanup_uses_configured_retention(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.execute.return_value.rowcount = 2

        with patch.object(self.worker.psycopg, "connect", return_value=connection):
            self.assertEqual(self.worker.cleanup_terminal_outbox(), 2)

        query, params = connection.execute.call_args.args
        self.assertIn("DELETE FROM task_outbox", query)
        self.assertIn("tasks.status IN ('succeeded', 'failed')", query)
        self.assertEqual(params, (self.worker.OUTBOX_RETENTION_SECONDS,))
        connection.commit.assert_called_once()

    def test_recovery_moves_exact_processing_payload_atomically(self):
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue

        self.assertEqual(self.worker.requeue_stale_delivery('{"task_id":"id"}'), 1)
        self.assertEqual(fake_queue.eval_call[1], 2)
        self.assertEqual(
            fake_queue.eval_call[2],
            (self.worker.PROCESSING_QUEUE, self.worker.TASK_QUEUE, '{"task_id":"id"}'),
        )

    def test_recovery_dead_letters_malformed_processing_payload(self):
        fake_queue = FakeQueue()
        self.worker.queue = fake_queue

        self.assertEqual(self.worker.dead_letter_processing_delivery("not json"), 1)
        self.assertEqual(fake_queue.eval_call[1], 2)
        self.assertEqual(
            fake_queue.eval_call[2],
            (self.worker.PROCESSING_QUEUE, self.worker.DEAD_LETTER_QUEUE, "not json"),
        )

    def test_recovery_acknowledges_terminal_processing_delivery(self):
        raw_payload = '{"task_id":"00000000-0000-0000-0000-000000000004","provider":"local-smoke-test"}'
        fake_queue = FakeQueue()
        fake_queue.lrange = Mock(return_value=[raw_payload])
        self.worker.queue = fake_queue
        cursor = FakeCursor(rows=[None, None, ("succeeded",)])
        connection = FakeConnection(cursor)
        self.worker.acknowledge_processing_delivery = Mock(return_value=1)

        with patch.object(self.worker.psycopg, "connect", return_value=connection):
            self.worker.recover_stale_deliveries()

        self.worker.acknowledge_processing_delivery.assert_called_once_with(raw_payload)

    def test_recovery_continues_after_a_database_error(self):
        first = '{"task_id":"00000000-0000-0000-0000-000000000005","provider":"local-smoke-test"}'
        second = '{"task_id":"00000000-0000-0000-0000-000000000006","provider":"local-smoke-test"}'
        fake_queue = FakeQueue()
        fake_queue.lrange = Mock(return_value=[first, second])
        self.worker.queue = fake_queue
        connection = FakeConnection(FakeCursor(rows=[("00000000-0000-0000-0000-000000000006",)]))
        self.worker.requeue_stale_delivery = Mock(return_value=1)

        with patch.object(
            self.worker.psycopg,
            "connect",
            side_effect=[self.worker.psycopg.Error("temporary database failure"), connection],
        ):
            self.worker.recover_stale_deliveries()

        self.worker.requeue_stale_delivery.assert_called_once_with(second)

    def test_recovery_requeues_processing_delivery_without_a_database_claim(self):
        raw_payload = '{"task_id":"00000000-0000-0000-0000-000000000003","provider":"local-smoke-test"}'
        fake_queue = FakeQueue()
        fake_queue.lrange = Mock(return_value=[raw_payload])
        self.worker.queue = fake_queue
        cursor = FakeCursor(rows=[("00000000-0000-0000-0000-000000000003",)])
        connection = FakeConnection(cursor)
        self.worker.requeue_stale_delivery = Mock(return_value=1)

        with patch.object(self.worker.psycopg, "connect", return_value=connection):
            self.worker.recover_stale_deliveries()

        self.assertTrue(connection.committed)
        self.assertIn("INSERT INTO tasks", cursor.queries[0][0])
        self.worker.requeue_stale_delivery.assert_called_once_with(raw_payload)


if __name__ == "__main__":
    unittest.main()
