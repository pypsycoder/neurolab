"""Regression tests for dashboard task submission boundaries."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql://example.invalid/neuro_lab")


def load_dashboard():
    sys.modules.pop("control_plane_dashboard", None)
    spec = importlib.util.spec_from_file_location(
        "control_plane_dashboard", ROOT / "dashboard" / "app.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    previous_directory = os.getcwd()
    try:
        os.chdir(ROOT / "dashboard")
        spec.loader.exec_module(module)
    finally:
        os.chdir(previous_directory)
    return module


class DashboardQueueTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = load_dashboard()
        self.dashboard.task_queue = Mock()
        self.dashboard.record_queued_task = Mock()
        self.dashboard.daily_lane_task_count = Mock(return_value=0)

    def test_submission_persists_a_durable_outbox_task(self):
        self.dashboard.task_queue.llen.return_value = 0
        request = self.dashboard.TaskRequest(
            prompt="synthetic check", model="GigaChat-2-Pro", credential_lane="primary", max_tokens=32
        )

        result = self.dashboard.create_task(request)

        self.assertEqual(result["status"], "queued")
        self.dashboard.record_queued_task.assert_called_once()
        self.dashboard.task_queue.rpush.assert_not_called()

    def test_submission_refuses_safe_queue_capacity(self):
        self.dashboard.task_queue.llen.return_value = self.dashboard.MAX_QUEUE_DEPTH
        request = self.dashboard.TaskRequest(
            prompt="synthetic check", model="GigaChat-2-Pro", credential_lane="primary", max_tokens=32
        )

        with self.assertRaises(HTTPException) as raised:
            self.dashboard.create_task(request)
        self.assertEqual(raised.exception.status_code, 429)
        self.dashboard.record_queued_task.assert_not_called()

    def test_submission_refuses_daily_credential_lane_budget(self):
        self.dashboard.task_queue.llen.return_value = 0
        self.dashboard.daily_lane_task_count.return_value = self.dashboard.MAX_TASKS_PER_LANE_PER_DAY
        request = self.dashboard.TaskRequest(
            prompt="synthetic check", model="GigaChat-2-Pro", credential_lane="freemium", max_tokens=32
        )

        with self.assertRaises(HTTPException) as raised:
            self.dashboard.create_task(request)
        self.assertEqual(raised.exception.status_code, 429)
        self.dashboard.task_queue.rpush.assert_not_called()

    def test_recent_task_serialization_uses_persisted_credential_lane(self):
        row = ("00000000-0000-0000-0000-000000000007", None, None, "queued", "gigachat", "GigaChat-2-Pro", "synthetic", None, "freemium", {})
        self.assertEqual(self.dashboard.serialize_row(row)["credential_lane"], "freemium")


if __name__ == "__main__":
    unittest.main()
