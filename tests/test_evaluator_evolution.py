import unittest
from hashlib import sha256
from uuid import uuid4

from neurolab.evaluator_evolution import EvaluationMetrics, EvaluationRun, EvaluatorEvolutionError, EvaluatorVersion, decide_evaluator_transition
from neurolab.evaluator_storage import EvaluatorStorageError, persist_evaluation_run
from neurolab.solution_memory import SolutionAsset, SolutionOutcome, next_asset_state


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def evaluator(*, state="promoted", parent=None, active=("case_a", "case_b"), proposed_by="author_one"):
    return EvaluatorVersion(str(uuid4()), "article_scoring", "v_one", proposed_by, digest(str(uuid4())), ("case_a", "case_b"), active, state, parent)


def run(version, *, assessor="critic_one", role="independent_evaluator", primary=.8, safety=.9, calibration=.8, cases=24, cohort=None):
    return EvaluationRun(str(uuid4()), version.evaluator_id, cohort or digest("cohort"), assessor, role, EvaluationMetrics(primary, safety, calibration, .7, cases))


class EvaluatorEvolutionTests(unittest.TestCase):
    def test_storage_refuses_missing_database_url(self):
        with self.assertRaises(EvaluatorStorageError):
            persist_evaluation_run("", run(evaluator()))

    def test_frozen_cases_cannot_be_removed(self):
        with self.assertRaises(EvaluatorEvolutionError):
            evaluator(active=("case_a",))

    def test_independent_holdout_improvement_promotes_candidate(self):
        baseline = evaluator()
        candidate = evaluator(state="shadow", parent=baseline.evaluator_id, proposed_by="author_two")
        self.assertEqual(decide_evaluator_transition(baseline, candidate, run(baseline), run(candidate, primary=.84, safety=.9, calibration=.82)).decision, "promoted")

    def test_self_certification_stays_in_shadow(self):
        baseline = evaluator()
        candidate = evaluator(state="shadow", parent=baseline.evaluator_id, proposed_by="author_two")
        decision = decide_evaluator_transition(baseline, candidate, run(baseline), run(candidate, assessor="author_two"))
        self.assertEqual(decision.decision, "shadow")

    def test_safety_regression_reverts_candidate(self):
        baseline = evaluator()
        candidate = evaluator(state="shadow", parent=baseline.evaluator_id)
        self.assertEqual(decide_evaluator_transition(baseline, candidate, run(baseline), run(candidate, primary=.9, safety=.89, calibration=.9)).decision, "reverted")

    def test_solution_assets_promote_only_after_repeated_success(self):
        asset = SolutionAsset(str(uuid4()), "workflow_scheme", "repair workflow", digest("asset"))
        outcomes = tuple(SolutionOutcome(asset.asset_id, digest(str(index)), str(uuid4()), "success", .85, .95) for index in range(3))
        self.assertEqual(next_asset_state(asset, outcomes), "promoted")
