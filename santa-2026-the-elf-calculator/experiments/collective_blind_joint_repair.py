"""Compare stochastic graph repair on ordinary and latent-factor programs."""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import time

from hybrid_graph_search import program_rules, rooted_rules
from isolated_catalog_search import extract
from first_solver import validate


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def rebuild(puzzle, parents, binary, trials):
    starts = json.loads(puzzle["starting_values"])
    goals = json.loads(puzzle["targets"])
    values = set(starts+goals)
    sources = []
    for program in parents:
        graph = {}
        for op in program_rules(puzzle,program):
            if op[-1] not in starts:
                graph.setdefault(op[-1],op)
        needed = {op[-1] for op in rooted_rules(starts,goals,graph)}
        # Preserve the parent's paid execution order as the fallback schedule.
        # DFS by ascending target can exceed 48 live values on an otherwise valid DAG.
        source = [op for v,op in graph.items() if v in needed]
        sources.append(source)
        values.update(op[-1] for op in source)
    candidate, stats = extract(puzzle,binary,trials,20261126,values,sources)
    shortest = min([candidate,*parents],key=len)
    validate(puzzle,shortest)
    return {"before":min(map(len,parents)), "steps":len(shortest), "program":shortest,
            "n_parents":len(parents),"proposals_per_arm":trials,"search":stats}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generic",type=Path,default=REPORTS / "collective_factor_blind_control48.json")
    parser.add_argument("--latent",type=Path,default=REPORTS / "collective_factor_latent_blind.json")
    parser.add_argument("--output",type=Path,default=REPORTS / "collective_blind_joint_repair.json")
    parser.add_argument("--trials",type=int,default=100)
    args = parser.parse_args()
    with (ROOT / "data" / "puzzles.csv").open() as stream:
        puzzles = {p["id"]:p for p in csv.DictReader(stream)}
    generic = json.loads(args.generic.read_text())["cases"]
    latent = json.loads(args.latent.read_text())["cases"]
    assert generic.keys() == latent.keys()
    cases = {}
    with tempfile.TemporaryDirectory() as temp:
        engine = Path(temp) / "joint"
        subprocess.run(["c++","-std=c++17","-O3",ROOT / "experiments" / "joint_bridge_search.cpp",
                        "-o",engine],check=True)
        for i, runs in generic.items():
            p = puzzles[i]
            ordinary = min((r["program"] for r in runs.values()),key=len)
            special = latent[i].get("program")
            validate(p,ordinary)
            arms = {"generic_only":[ordinary]}
            if special:
                validate(p,special)
                arms.update(latent_only=[special],joint=[ordinary,special])
            results = {}
            for name,parents in arms.items():
                tick = time.monotonic()
                result = rebuild(p,parents,engine,args.trials)
                result["elapsed_seconds"] = round(time.monotonic()-tick,3)
                results[name] = result
            winner = min(results,key=lambda arm:results[arm]["steps"])
            cases[i] = {"generic_before":len(ordinary),"latent_before":len(special) if special else None,
                        "before":min([len(ordinary)]+([len(special)] if special else [])),
                        "after":results[winner]["steps"],"winner":winner,"program":results[winner]["program"],
                        "arms":results}
            print(i,{name:result["steps"] for name,result in results.items()},flush=True)
    report = {"sources":[args.generic.name,args.latent.name],"trials_per_arm":args.trials,
              "seed":20261126,"cases":cases}
    args.output.write_text(json.dumps(report,separators=(",",":"))+"\n")


if __name__ == "__main__":
    main()
