"""First durable LangGraph boundary: existing receipts only, no paid calls or execution."""
from typing import TypedDict
from uuid import UUID
import re
from langgraph.graph import StateGraph, START, END
from neurolab.code_cycle_gate import validate_cycle_result

BOUNDARY='public_synthetic_experimental_only'
GRAPH_VERSION='receipt-reconcile-v2'


class ReconciliationState(TypedDict, total=False):
    spec_run_id: str
    code_run_id: str
    boundary: str
    spec_sha256: str
    outcome_sha256: str
    phase: str
    decision: str
    independent_passed: int
    independent_total: int
    cycles_passed: int | None
    production_deployed: bool


def digest(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('receipt digest malformed')
    return value


def build_reconciliation_graph(checkpointer, load_spec, load_outcome, *, stop_after_spec=False):
    def spec_node(state):
        if state.get('boundary')!=BOUNDARY:
            raise ValueError('workflow boundary invalid')
        spec_id=str(UUID(state['spec_run_id']))
        row=load_spec(spec_id)
        return {'spec_sha256':digest(row['spec_sha256']),'phase':'spec_checked'}

    def outcome_node(state):
        row=load_outcome(str(UUID(state['code_run_id'])))
        if row['spec_run_id']!=state['spec_run_id'] or row['spec_sha256']!=state['spec_sha256'] or row['production_deployed'] is not False:
            raise ValueError('outcome linkage invalid')
        passed,total=row['passed'],row['total']
        if type(passed) is not int or type(total) is not int or total!=11 or not 0<=passed<=total:
            raise ValueError('outcome metrics invalid')
        if row['decision'] not in {'repair','harvest_parts'}:
            raise ValueError('outcome decision invalid')
        if row['decision']=='harvest_parts' and passed!=total:
            raise ValueError('failed candidate cannot be harvested')
        cycles = row.get('cycles_evaluation')
        cycles_passed = validate_cycle_result(cycles)[0] if cycles is not None else None
        decision = row['decision']
        if decision == 'harvest_parts':
            if cycles_passed is None:
                decision = 'continue'  # Legacy result needs the new independent gate, not code promotion.
            elif cycles_passed != 9:
                raise ValueError('failed cycle gate cannot be harvested')
        return {'outcome_sha256':digest(row['outcome_sha256']),'independent_passed':passed,
            'independent_total':total,'cycles_passed':cycles_passed,'decision':decision,'production_deployed':False,'phase':'outcome_checked'}

    def decision_node(state):
        if state['decision'] not in {'repair','harvest_parts','continue'}:
            raise ValueError('unsupported decision')
        return {'phase':'complete'}

    graph=StateGraph(ReconciliationState)
    graph.add_node('spec',spec_node); graph.add_node('outcome',outcome_node); graph.add_node('decision',decision_node)
    graph.add_edge(START,'spec'); graph.add_edge('spec','outcome'); graph.add_edge('outcome','decision'); graph.add_edge('decision',END)
    return graph.compile(checkpointer=checkpointer,interrupt_after=['spec'] if stop_after_spec else [])


def run_or_resume(graph, workflow_id, spec_id, code_id, *, cancel=False):
    workflow_id,spec_id,code_id=map(lambda item:str(UUID(item)),(workflow_id,spec_id,code_id))
    config={'configurable':{'thread_id':GRAPH_VERSION+':'+workflow_id},'recursion_limit':8}
    snapshot=graph.get_state(config)
    reused=bool(snapshot.values)
    if reused:
        if snapshot.values.get('spec_run_id')!=spec_id or snapshot.values.get('code_run_id')!=code_id or snapshot.values.get('boundary')!=BOUNDARY:
            raise ValueError('workflow identity reuse invalid')
        if cancel:
            if not snapshot.next:
                raise ValueError('terminal workflow cannot be cancelled')
            graph.update_state(config,{'phase':'cancelled','decision':'cancelled','production_deployed':False},as_node='decision')
        elif snapshot.next:
            graph.invoke(None,config)
    elif cancel:
        raise ValueError('missing workflow cannot be cancelled')
    else:
        graph.invoke({'spec_run_id':spec_id,'code_run_id':code_id,'boundary':BOUNDARY,'phase':'created'},config)
    final=graph.get_state(config)
    values=final.values
    return {'workflow_id':workflow_id,'graph_version':GRAPH_VERSION,'spec_run_id':spec_id,'code_run_id':code_id,
        'phase':values['phase'],'decision':values.get('decision'),'pending_nodes':list(final.next),
        'checkpoint_id':final.config['configurable']['checkpoint_id'],'reused_checkpoint':reused,
        'new_model_calls':0,'production_deployed':False,'independent_passed':values.get('independent_passed'),
        'independent_total':values.get('independent_total'),'cycles_passed':values.get('cycles_passed')}
