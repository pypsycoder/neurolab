"""Supplementary frozen cycle gate; original provenance-frozen-v1 is unchanged."""
import importlib.util
import json
import random
import sys

VERSION = "provenance-cycles-v1"


def evaluate(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    function = module.affected_nodes
    cases = []
    def reject(name, edges, failed):
        original = list(edges)
        try:
            function(edges, failed); passed = False
        except ValueError:
            passed = edges == original
        except Exception:
            passed = False
        cases.append({"case": name, "passed": passed})
    for size in (3, 4, 5, 8):
        edges = [(f"c{i}", f"c{(i+1)%size}") for i in range(size)]
        reject(f"cycle_length_{size}", edges, "c0")
    for size in (3, 8):
        edges = [(f"z{i}", f"z{(i+1)%size}") for i in range(size)] + [("a", "b")]
        reject(f"disconnected_cycle_length_{size}", edges, "a")
    reject("duplicate_cycle_edges", [("a","b"),("b","c"),("c","a"),("a","b")], "a")
    edges = [("a","b"),("a","c"),("b","d"),("c","d")]
    original = list(edges)
    try:
        passed = function(edges, "a") == ["a","b","c","d"] and edges == original
    except Exception:
        passed = False
    cases.append({"case": "acyclic_diamond_control", "passed": passed})
    rng = random.Random(20261003)
    passed = True
    for index in range(24):
        size = rng.randrange(3, 19)
        nodes = [f"h{index}_{i}" for i in range(size)]
        rng.shuffle(nodes)
        edges = [(nodes[i],nodes[(i+1)%size]) for i in range(size)]
        rng.shuffle(edges)
        original = list(edges)
        try:
            function(edges, "isolated"); passed = False
        except ValueError:
            passed = passed and edges == original
        except Exception:
            passed = False
    cases.append({"case":"cyclic_holdout_24","passed":passed})
    return {"evaluator_version":VERSION,"cases":cases,"passed":sum(c["passed"] for c in cases),"total":len(cases)}


if __name__ == "__main__":
    result = evaluate(sys.argv[1]); print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result["passed"] == result["total"] else 1)
