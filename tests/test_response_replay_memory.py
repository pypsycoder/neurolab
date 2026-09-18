import unittest
from hashlib import sha256
from uuid import uuid4

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun
from neurolab.response_replay_memory import response_replay_outcome, response_replay_prompt_asset


def run(*, primary=.9, safety=.9, calibration=.9):
    return EvaluationRun(
        str(uuid4()), str(uuid4()), sha256(b"cohort").hexdigest(), "contract_evaluator", "independent_evaluator",
        EvaluationMetrics(primary, safety, calibration, 1.0, 4),
    )


class ResponseReplayMemoryTests(unittest.TestCase):
    def test_safety_failure_becomes_regression(self):
        outcome = response_replay_outcome(run(primary=.99, safety=.89, calibration=.99))
        self.assertEqual(outcome.outcome, "regression")
        self.assertEqual(outcome.asset_id, response_replay_prompt_asset().asset_id)

    def test_quality_failure_becomes_failure_and_good_run_is_success(self):
        self.assertEqual(response_replay_outcome(run(primary=.79, safety=.95, calibration=.95)).outcome, "failure")
        self.assertEqual(response_replay_outcome(run(primary=.85, safety=.95, calibration=.85)).outcome, "success")
