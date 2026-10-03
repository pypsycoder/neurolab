"""Persist only a bounded projection of independently measured synthetic outcomes."""
from hashlib import sha256
import json
import math
import re
from uuid import UUID
from neurolab.code_diagnostics import RULES
from neurolab.code_cycle_gate import validate_cycle_result

CASES = {'empty','chain','upstream_excluded','branch_isolation','diamond_duplicates','isolated','leaf','cycle','self_loop','disconnected_cycle','synthetic_dag_holdout_50'}


def _suite(value):
    items=value['cases']
    if value['evaluator_version']!='provenance-frozen-v1' or type(value['total']) is not int or value['total']!=11 or len(items)!=11:
        raise ValueError('frozen evaluation identity mismatch')
    if {item['case'] for item in items}!=CASES or any(type(item['passed']) is not bool for item in items):
        raise ValueError('frozen evaluation cases mismatch')
    passed=sum(item['passed'] for item in items)
    if type(value['passed']) is not int or value['passed']!=passed:
        raise ValueError('evaluation metrics mismatch')
    return passed,sorted(item['case'] for item in items if not item['passed'])


def project_code_outcome(receipt):
    if len(json.dumps(receipt).encode())>12000:
        raise ValueError('code outcome exceeds budget')
    if receipt['boundary']!='public_synthetic_experimental_only' or receipt['production_deployed'] is not False or receipt['code_executed'] is not True:
        raise ValueError('outcome boundary mismatch')
    if receipt['agent'] not in {'GigaChat-SDK-structured-pure-function','OpenHands-CLI-1.16.0'}:
        raise ValueError('unsupported code outcome agent')
    if _suite(receipt['baseline'])[0]!=0:
        raise ValueError('baseline did not fail')
    passed,failed=_suite(receipt['evaluation'])
    diagnostics=receipt.get('static_diagnostics',[])
    if not isinstance(diagnostics,list) or len(diagnostics)>60:
        raise ValueError('static diagnostics invalid')
    for item in diagnostics:
        if set(item)!={'code','line','column'} or item['code'] not in RULES or type(item['line']) is not int or type(item['column']) is not int or not 1<=item['line']<=500 or not 1<=item['column']<=16000:
            raise ValueError('static diagnostics invalid')
    runtime_gate = True
    if receipt['agent']=='OpenHands-CLI-1.16.0':
        if type(receipt.get('agent_exit_code')) is not int or not -255 <= receipt['agent_exit_code'] <= 255 or type(receipt.get('code_changed')) is not bool:
            raise ValueError('agent execution receipt malformed')
        runtime_gate = receipt['agent_exit_code'] == 0 and receipt['code_changed']
    cycles = receipt.get('cycles_evaluation')
    cycles_passed = validate_cycle_result(cycles)[0] if cycles is not None else None
    accepted=passed==11 and not diagnostics and runtime_gate and cycles_passed in {None,9}
    expected_status='candidate_passed' if accepted else 'candidate_failed'
    expected_decision='harvest_parts' if accepted else 'repair'
    if receipt['status']!=expected_status or receipt['decision']!=expected_decision or receipt['independent_score']!=passed/11:
        raise ValueError('independent outcome decision mismatch')
    result={'run_id':str(UUID(receipt['run_id'])),'spec_run_id':str(UUID(receipt['spec_run_id'])),
        'boundary':receipt['boundary'],'agent':receipt['agent'],'status':expected_status,'decision':expected_decision,
        'passed':passed,'total':11,'failed_cases':failed,'independent_score':passed/11,
        'production_deployed':False,'self_score':receipt['self_score'],'static_diagnostics':diagnostics}
    if receipt['agent']=='OpenHands-CLI-1.16.0':
        result.update(agent_exit_code=receipt['agent_exit_code'],code_changed=receipt['code_changed'],runtime_gate_passed=runtime_gate)
    if cycles is not None:
        result.update(cycles_evaluation=cycles)
        digest = receipt.get('cycles_evaluator_sha256')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('cycle evaluator digest invalid')
        result['cycles_evaluator_sha256'] = digest
    score=result['self_score']
    if score is not None and (type(score) not in {float,int} or not math.isfinite(score) or not 0<=score<=1):
        raise ValueError('self score invalid')
    for key in ('spec_sha256','code_sha256','evaluator_sha256'):
        value=receipt[key]
        if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
            raise ValueError('outcome digest invalid')
        result[key]=value
    model=receipt['model_label']
    if not isinstance(model,str) or not re.fullmatch('[A-Za-z0-9_.:-]{2,80}',model):
        raise ValueError('outcome model label invalid')
    result['model_label']=model
    result['provider_tokens']={}
    for key in ('prompt_tokens','completion_tokens','total_tokens'):
        value=receipt.get('provider_tokens',{}).get(key)
        if value is not None and (type(value) is not int or not 0<=value<=1_000_000):
            raise ValueError('provider usage invalid')
        result['provider_tokens'][key]=value
    result['repair_from']=str(UUID(receipt['repair_from'])) if receipt.get('repair_from') else None
    return result


def outcome_hash(outcome):
    return sha256(json.dumps(outcome,sort_keys=True,separators=(',',':')).encode()).hexdigest()
