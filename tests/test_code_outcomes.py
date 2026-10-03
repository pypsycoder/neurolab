import copy
import unittest
from neurolab.code_outcomes import CASES, project_code_outcome, outcome_hash


def receipt():
    cases=[{'case':name,'passed':True} for name in sorted(CASES)]
    return {'run_id':'00000000-0000-0000-0000-000000000001','spec_run_id':'00000000-0000-0000-0000-000000000002',
        'boundary':'public_synthetic_experimental_only','production_deployed':False,'code_executed':True,
        'agent':'GigaChat-SDK-structured-pure-function','status':'candidate_passed','decision':'harvest_parts',
        'baseline':{'evaluator_version':'provenance-frozen-v1','total':11,'passed':0,'cases':[dict(item,passed=False) for item in cases]},
        'evaluation':{'evaluator_version':'provenance-frozen-v1','total':11,'passed':11,'cases':cases},
        'independent_score':1.0,'self_score':.5,'spec_sha256':'a'*64,'code_sha256':'b'*64,
        'evaluator_sha256':'c'*64,'model_label':'GigaChat-2-Pro','provider_tokens':{'total_tokens':1223}}


class CodeOutcomeTests(unittest.TestCase):
    def test_openhands_requires_actual_change_and_successful_runtime(self):
        raw = receipt()
        raw.update(agent='OpenHands-CLI-1.16.0', agent_exit_code=0, code_changed=True)
        projected = project_code_outcome(raw)
        self.assertTrue(projected['runtime_gate_passed'])
        for exit_code, changed in ((-9, True), (124, True), (0, False)):
            with self.subTest(exit_code=exit_code, changed=changed):
                failed = copy.deepcopy(raw)
                failed.update(agent_exit_code=exit_code, code_changed=changed)
                with self.assertRaises(ValueError):
                    project_code_outcome(failed)
                failed.update(status='candidate_failed', decision='repair')
                self.assertFalse(project_code_outcome(failed)['runtime_gate_passed'])

    def test_openhands_malformed_runtime_gate_is_not_inferred(self):
        raw = receipt(); raw.update(agent='OpenHands-CLI-1.16.0', code_changed=True, agent_exit_code=True)
        with self.assertRaises(ValueError):
            project_code_outcome(raw)
        raw.pop('agent_exit_code')
        with self.assertRaises(ValueError):
            project_code_outcome(raw)

    def test_projection_excludes_raw_content_and_does_not_promote(self):
        raw=receipt(); raw['raw_prompt']='secret content'
        projected=project_code_outcome(raw)
        self.assertNotIn('raw_prompt',projected)
        self.assertEqual(projected['decision'],'harvest_parts')
        self.assertEqual(len(outcome_hash(projected)),64)

    def test_self_score_cannot_override_failed_independent_cases(self):
        raw=receipt(); raw['self_score']=1.0; raw['evaluation']['cases'][0]['passed']=False
        with self.assertRaises(ValueError):
            project_code_outcome(raw)

    def test_unknown_tests_prod_flags_or_boolean_metrics_rejected(self):
        for mutate in (lambda r:r.update(production_deployed=True),lambda r:r['evaluation']['cases'][0].update(case='untrusted test'),lambda r:r.update(self_score=True)):
            raw=receipt(); mutate(raw)
            with self.assertRaises(ValueError):
                project_code_outcome(raw)

    def test_static_error_prevents_acceptance_even_if_current_cases_pass(self):
        raw=receipt(); raw['static_diagnostics']=[{'code':'F821','line':6,'column':12}]
        with self.assertRaises(ValueError):
            project_code_outcome(raw)
        raw.update(status='candidate_failed',decision='repair')
        self.assertEqual(project_code_outcome(raw)['status'],'candidate_failed')
