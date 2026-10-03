"""Validate supplementary cycle metrics without replacing historical frozen results."""
VERSION = "provenance-cycles-v1"
CASES = {"cycle_length_3","cycle_length_4","cycle_length_5","cycle_length_8",
         "disconnected_cycle_length_3","disconnected_cycle_length_8","duplicate_cycle_edges",
         "acyclic_diamond_control","cyclic_holdout_24"}


def validate_cycle_result(value):
    if value.get("evaluator_version") != VERSION or type(value.get("total")) is not int or value["total"] != 9:
        raise ValueError("cycle gate identity mismatch")
    items = value.get("cases")
    if not isinstance(items,list) or len(items)!=9 or {item["case"] for item in items}!=CASES or any(type(item["passed"]) is not bool for item in items):
        raise ValueError("cycle gate case mismatch")
    passed = sum(item["passed"] for item in items)
    if type(value.get("passed")) is not int or value["passed"]!=passed:
        raise ValueError("cycle gate metrics mismatch")
    return passed, sorted(item["case"] for item in items if not item["passed"])
