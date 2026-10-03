import unittest
from langgraph.checkpoint.memory import InMemorySaver
from neurolab.durable_reconciliation import build_reconciliation_graph, run_or_resume

WORKFLOW='00000000-0000-0000-0000-000000000001'
SPEC='00000000-0000-0000-0000-000000000002'
CODE='00000000-0000-0000-0000-000000000003'


class DurableGraphTests(unittest.TestCase):
    def loaders(self):
        counts={'spec':0,'outcome':0}
        def spec(run_id):
            counts['spec']+=1
            return {'spec_sha256':'a'*64}
        def outcome(run_id):
            counts['outcome']+=1
            return {'spec_run_id':SPEC,'spec_sha256':'a'*64,'outcome_sha256':'b'*64,
                'production_deployed':False,'passed':11,'total':11,'decision':'harvest_parts'}
        return counts,spec,outcome

    def test_resume_does_not_repeat_completed_node_or_call_model(self):
        saver=InMemorySaver(); counts,spec,outcome=self.loaders()
        graph=build_reconciliation_graph(saver,spec,outcome,stop_after_spec=True)
        result=run_or_resume(graph,WORKFLOW,SPEC,CODE)
        self.assertEqual(result['pending_nodes'],['outcome'])
        resumed=build_reconciliation_graph(saver,spec,outcome)
        self.assertEqual(run_or_resume(resumed,WORKFLOW,SPEC,CODE)['decision'],'harvest_parts')
        self.assertEqual(run_or_resume(resumed,WORKFLOW,SPEC,CODE)['new_model_calls'],0)
        self.assertEqual(counts,{'spec':1,'outcome':1})

    def test_cancel_stops_pending_outcome_and_identity_cannot_be_reused(self):
        saver=InMemorySaver(); counts,spec,outcome=self.loaders()
        graph=build_reconciliation_graph(saver,spec,outcome,stop_after_spec=True)
        run_or_resume(graph,WORKFLOW,SPEC,CODE)
        result=run_or_resume(graph,WORKFLOW,SPEC,CODE,cancel=True)
        self.assertEqual(result['phase'],'cancelled'); self.assertEqual(result['pending_nodes'],[])
        self.assertEqual(counts,{'spec':1,'outcome':0})
        with self.assertRaises(ValueError):
            run_or_resume(graph,WORKFLOW,CODE,SPEC)

    def test_failed_outcome_cannot_be_harvested(self):
        counts,spec,outcome=self.loaders()
        def bad(run_id):
            return dict(outcome(run_id),passed=4)
        graph=build_reconciliation_graph(InMemorySaver(),spec,bad)
        with self.assertRaises(ValueError):
            run_or_resume(graph,WORKFLOW,SPEC,CODE)
