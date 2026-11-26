"""Build multiplication-table solutions with the public signed-remainder constructor."""

import argparse
import csv
import json
import random
import subprocess
import tempfile
from pathlib import Path

from collective_external_control import ROOT, input_row
from first_solver import validate
from hybrid_graph_search import compile_changes, program_rules, rooted_rules
from collective_blind_joint_repair import rebuild


def plans(item, family, limit):
    t, a, b, k = (item[key] for key in ("t", "a", "b", "k"))
    center = a*b
    origins = [(1, center)] + [
        (x["k"], x["t"]) for x in family if x["a"] * x["b"] == center
        and x["t"] < t and k % x["k"] == 0
    ]
    alternatives = []
    for ratio, origin in origins:
        m = k//ratio
        gap = t - m*origin
        for inner in {0, gap//m, (gap+m//2)//m}:
            corrected = origin + inner
            value = m*corrected
            if not (0 < value <= limit and 0 < corrected <= limit):
                continue
            ops = []
            if origin == center:
                ops.append(("*", a, b, center))
            if inner:
                ops.append(("+" if inner > 0 else "-", origin, abs(inner), corrected))
            if m != 1:
                ops.append(("*", corrected, m, value))
            if value != t:
                ops.append(("+" if t > value else "-", value, abs(t-value), t))
            if ops and all(v not in (x,y) for _,x,y,v in ops):
                alternatives.append(ops)
    return alternatives


def select(puzzle, fits, order_seed):
    starts = set(json.loads(puzzle["starting_values"]))
    targets = set(json.loads(puzzle["targets"]))
    retained = starts | targets
    recipes = {}
    required = set()
    rng = random.Random(order_seed)
    ordered = sorted(fits["targets"], key=lambda v:v["t"])
    if order_seed:
        rng.shuffle(ordered)
    for item in ordered:
        best = None
        for path in plans(item, fits["targets"], int(puzzle["value_limit"])):
            interior = {v for _,_,_,v in path}
            leaves = {x for _,a,b,_ in path for x in (a,b)} - interior
            n_new = len(interior - recipes.keys())
            score = n_new + sum(1 + .29*x.bit_length() for x in leaves - retained - required)
            if best is None or score < best[0]:
                best = score, path, leaves
        if best:
            _, path, leaves = best
            required.update(leaves)
            for op in path:
                recipes.setdefault(op[3],op)
    required.update(targets)
    required.difference_update(recipes)
    required.difference_update(starts)
    return recipes, required


def dictionary_program(puzzle, executable, seed):
    flags = ["3", ".18", "52", "56", "19", "1", str(seed)]
    raw = subprocess.check_output([executable,*flags],input=input_row(puzzle)+"\n",text=True)
    subid, text = raw.split(" ",1)
    assert subid == puzzle["id"]
    partial = json.loads(text)
    validate(puzzle,partial)
    return partial


def solve(puzzle, fits, executable, seed):
    recipes, required = select(puzzle, fits, seed)
    subproblem = {**puzzle, "targets":json.dumps(sorted(required))}
    partial = dictionary_program(subproblem,executable,seed)
    graph = {}
    for op in program_rules(subproblem,partial):
        graph.setdefault(op[-1],op)
    graph.update(recipes)
    starts = json.loads(puzzle["starting_values"])
    targets = json.loads(puzzle["targets"])
    for order in [targets,list(reversed(targets))]:
        seq = rooted_rules(starts,order,graph)
        ops = compile_changes(puzzle,seq,targets)
        if ops is not None:
            validate(puzzle, ops)
            return {"steps":len(ops),"program":ops,"subtargets":sorted(required),
                    "subtarget_steps":len(partial),"selected_recipes":list(recipes.values())}
    raise ValueError("register allocation failed")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dictionary",type=Path,help="Pinned public C++ constructor compiled as in collective_external_control.py")
    parser.add_argument("--seeds",type=int,nargs="+",default=[0,17,29])
    parser.add_argument("--trials",type=int,default=100)
    parser.add_argument("--output",type=Path,default=ROOT/"reports"/"collective_matrix_external.json")
    args=parser.parse_args()
    with (ROOT/"data"/"puzzles.csv").open() as f:
        puzzles={x["id"]:x for x in csv.DictReader(f)}
    fits=json.loads((ROOT/"reports"/"collective_matrix_fits.json").read_text())
    cases={}
    searches = {}
    with tempfile.TemporaryDirectory() as temp:
        binary = Path(temp)/"joint"
        subprocess.run(["c++","-std=c++17","-O3",ROOT/"experiments"/"joint_bridge_search.cpp",
                        "-o",binary],check=True)
        for key, case in fits["cases"].items():
            if not case["targets"]:
                continue
            puzzle = puzzles[key]
            results={}
            for seed in args.seeds:
                try:
                    results[seed]=solve(puzzle,case,args.dictionary,seed)
                except ValueError as err:
                    results[seed]={"error":str(err)}
                print(key,seed,results[seed].get("steps"),flush=True)
            cases[key]=results
            control = dictionary_program(puzzle,args.dictionary,0)
            candidates = [r["program"] for r in results.values() if "program" in r]
            arms = {"plain_single":[control], "combined_parents":[control,*candidates]}
            if "program" in results.get(0,{}):
                arms["table_single"] = [results[0]["program"]]
            searches[key] = {arm:rebuild(puzzle,parents,binary,args.trials) for arm,parents in arms.items()}
            for name, result in searches[key].items():
                print(key, name, result["before"], result["steps"],flush=True)
        args.output.write_text(json.dumps({"cases":cases,"seeds":args.seeds,"fits":"collective_matrix_fits.json",
            "joint_search":searches,
            "constructor":"collective_external_control.py, replan flags, combined with newly selected multiplication-table recipes"},separators=(",",":"))+"\n")


if __name__ == "__main__":
    main()
