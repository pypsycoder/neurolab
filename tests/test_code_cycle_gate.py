import importlib.util
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from neurolab.code_cycle_gate import CASES, VERSION, EVALUATOR_SHA256, validate_cycle_result, project_cycle_assessment, assessment_hash
from neurolab.code_outcomes import project_code_outcome
from test_code_outcomes import receipt

spec=importlib.util.spec_from_file_location('cycles',Path(__file__).parent/'fixtures/provenance_cycle_evaluator.py')
cycles=importlib.util.module_from_spec(spec); spec.loader.exec_module(cycles)


class CodeCycleGateTests(unittest.TestCase):
    def test_supplementary_fixture_is_pinned(self):
        self.assertEqual(sha256((Path(__file__).parent/'fixtures/provenance_cycle_evaluator.py').read_bytes()).hexdigest(),EVALUATOR_SHA256)

    def test_reassessment_is_redacted_and_bound_to_the_frozen_gate(self):
        value={'run_id':'00000000-0000-0000-0000-000000000001','code_sha256':'a'*64,'cycles_evaluator_sha256':EVALUATOR_SHA256,
               'cycles_evaluation':{'evaluator_version':VERSION,'total':9,'passed':9,'cases':[{'case':name,'passed':True} for name in sorted(CASES)]},
               'status':'passed','new_model_calls':0,'production_deployed':False,'historical_outcome_modified':False,'raw_prompt':'private'}
        projected=project_cycle_assessment(value)
        self.assertNotIn('raw_prompt',projected)
        self.assertEqual(len(assessment_hash(projected)),64)
        value['cycles_evaluator_sha256']='b'*64
        with self.assertRaises(ValueError):
            project_cycle_assessment(value)

    def test_cycle_metrics_cannot_carry_raw_extra_fields(self):
        value={'evaluator_version':VERSION,'total':9,'passed':9,'cases':[{'case':name,'passed':True} for name in sorted(CASES)]}
        value['raw_output']='private'
        with self.assertRaises(ValueError):
            validate_cycle_result(value)
        value.pop('raw_output'); value['cases'][0]['raw_output']='private'
        with self.assertRaises(ValueError):
            validate_cycle_result(value)
    def test_old_frozen_suite_is_unchanged(self):
        path=Path(__file__).parent/'fixtures/provenance_evaluator.py'
        self.assertEqual(sha256(path.read_bytes()).hexdigest(),'f2c98b97dff5d4bd37dd826eb72d789b915f6497fa622b158b86a550b89d066a')

    def test_reject_everything_cannot_game_control(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reference.py'; path.write_text('def affected_nodes(edges, failed):\n    raise ValueError()\n')
            result=cycles.evaluate(path)
        self.assertEqual(validate_cycle_result(result)[0],8)
        self.assertEqual(validate_cycle_result(result)[1],['acyclic_diamond_control'])

    def test_stdlib_graphlib_reference_passes_supplement(self):
        # Independent test oracle only: never an agent candidate or production asset.
        reference='''from graphlib import TopologicalSorter
def affected_nodes(edges, failed):
    graph={}
    for a,b in edges:
        graph.setdefault(a,set()).add(b)
    list(TopologicalSorter(graph).static_order())
    reached={failed}
    for _ in range(len(graph)+1):
        reached |= {b for a,b in edges if a in reached}
    return sorted(reached)
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'reference.py'; path.write_text(reference)
            result=cycles.evaluate(path)
        self.assertEqual(validate_cycle_result(result),(9,[]))

    def test_new_gate_failure_cannot_be_promoted_by_old_eleven_pass(self):
        raw=receipt(); raw['cycles_evaluation']={'evaluator_version':VERSION,'total':9,'passed':0,'cases':[{'case':name,'passed':False} for name in sorted(CASES)]}
        raw['cycles_evaluator_sha256']='d'*64
        with self.assertRaises(ValueError):
            project_code_outcome(raw)
        raw.update(status='candidate_failed',decision='repair')
        self.assertEqual(project_code_outcome(raw)['cycles_evaluation']['passed'],0)
