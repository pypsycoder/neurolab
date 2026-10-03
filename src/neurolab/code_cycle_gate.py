"""Validate supplementary cycle metrics without replacing historical frozen results."""
VERSION = "provenance-cycles-v1"
EVALUATOR_SHA256 = "28139dd8a14dff8b20270391aaea3a724d59c758e556b7514aed14e8cd4c2322"
CASES = {"cycle_length_3","cycle_length_4","cycle_length_5","cycle_length_8",
         "disconnected_cycle_length_3","disconnected_cycle_length_8","duplicate_cycle_edges",
         "acyclic_diamond_control","cyclic_holdout_24"}


def validate_cycle_result(value):
    if not isinstance(value,dict) or set(value)!={'evaluator_version','total','passed','cases'}:
        raise ValueError('cycle gate shape mismatch')
    if value.get("evaluator_version") != VERSION or type(value.get("total")) is not int or value["total"] != 9:
        raise ValueError("cycle gate identity mismatch")
    items = value.get("cases")
    if not isinstance(items,list) or len(items)!=9 or any(not isinstance(item,dict) or set(item)!={'case','passed'} for item in items) or {item["case"] for item in items}!=CASES or any(type(item["passed"]) is not bool for item in items):
        raise ValueError("cycle gate case mismatch")
    passed = sum(item["passed"] for item in items)
    if type(value.get("passed")) is not int or value["passed"]!=passed:
        raise ValueError("cycle gate metrics mismatch")
    return passed, sorted(item["case"] for item in items if not item["passed"])


def project_cycle_assessment(value):
    from uuid import UUID
    import re
    result={"run_id":str(UUID(value['run_id'])),"cycles_evaluation":value['cycles_evaluation'],
            "cycles_evaluator_sha256":value['cycles_evaluator_sha256'],"code_sha256":value['code_sha256']}
    passed,_=validate_cycle_result(result['cycles_evaluation'])
    if result['cycles_evaluator_sha256']!=EVALUATOR_SHA256 or not re.fullmatch('[0-9a-f]{64}',result['code_sha256']):
        raise ValueError('cycle assessment identity mismatch')
    expected='passed' if passed==9 else 'failed'
    if value['status']!=expected or value.get('new_model_calls')!=0 or type(value.get('new_model_calls')) is not int or value.get('production_deployed') is not False or value.get('historical_outcome_modified') is not False:
        raise ValueError('cycle assessment boundary mismatch')
    result.update(status=expected,new_model_calls=0,production_deployed=False,historical_outcome_modified=False)
    return result


def assessment_hash(value):
    from hashlib import sha256
    import json
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
