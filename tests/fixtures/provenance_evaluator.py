"""Immutable independent evaluator. Never mounted in the code agent's container."""
import importlib.util
import json
import random
import sys


def evaluate(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = module.affected_nodes
    cases = []
    fixtures = [
        ("empty", [], "failed", ["failed"]),
        ("chain", [("a", "b"), ("b", "c")], "a", ["a", "b", "c"]),
        ("upstream_excluded", [("a", "b"), ("b", "c")], "b", ["b", "c"]),
        ("branch_isolation", [("a", "b"), ("x", "y")], "a", ["a", "b"]),
        ("diamond_duplicates", [("a", "c"), ("a", "b"), ("c", "d"), ("b", "d"), ("a", "c")], "a", ["a", "b", "c", "d"]),
        ("isolated", [("a", "b")], "z", ["z"]),
        ("leaf", [("a", "b")], "b", ["b"]),
    ]
    for name, edges, failed, expected in fixtures:
        original = list(edges)
        try:
            passed = function(edges, failed) == expected and edges == original
        except Exception:
            passed = False
        cases.append({"case": name, "passed": passed})
    for name, edges in (("cycle", [("a", "b"), ("b", "a")]), ("self_loop", [("a", "a")]), ("disconnected_cycle", [("x", "y"), ("y", "x"), ("a", "b")])):
        try:
            function(edges, "a")
            passed = False
        except ValueError:
            passed = True
        except Exception:
            passed = False
        cases.append({"case": name, "passed": passed})
    # A separate oracle with fixed synthetic random graphs guards against fixture-only repair.
    rng = random.Random(20261002)
    passed = True
    for _ in range(50):
        nodes = [f"n{i:02}" for i in range(18)]
        edges = [(nodes[i], nodes[j]) for i in range(18) for j in range(i + 1, 18) if rng.random() < .13]
        failed = rng.choice(nodes)
        expected = {failed}
        for _ in range(18):
            expected |= {b for a, b in edges if a in expected}
        try:
            if function(edges, failed) != sorted(expected):
                passed = False
        except Exception:
            passed = False
    cases.append({"case": "synthetic_dag_holdout_50", "passed": passed})
    return {"evaluator_version": "provenance-frozen-v1", "cases": cases, "passed": sum(c["passed"] for c in cases), "total": len(cases)}


if __name__ == "__main__":
    result = evaluate(sys.argv[1])
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
