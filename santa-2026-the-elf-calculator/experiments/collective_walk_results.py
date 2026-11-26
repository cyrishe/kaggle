"""Independently verify each search policy and summarize nested restart budgets."""

import csv
import json
from pathlib import Path
from first_solver import validate

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "data/puzzles.csv").open() as src:
    puzzles = {row["id"]: row for row in csv.DictReader(src)}
cases = {}
for name in ("", "_modular", "_meet", "_ladder", "_prefix_race"):
    path = ROOT / ("reports/collective_walk" + name + ".json")
    if path.exists():
        for ident, row in json.loads(path.read_text())["cases"].items():
            for mode, results in row.items():
                assert validate(puzzles[ident], results["best_program"])[0] == min(results["lengths"])
                for trial, program in enumerate(results["programs"]):
                    assert validate(puzzles[ident], program)[0] == results["lengths"][trial]
                cases.setdefault(ident, {})[mode] = results

for mode in ("shallow", "combined", "modular", "meet", "ladder", "prefix_race"):
    runs = [cases[ident][mode] for ident in sorted(cases) if mode in cases[ident]]
    if not runs:
        continue
    checkpoints = [n for n in (1, 2, 4) if all(len(r["lengths"]) >= n for r in runs)]
    print(
        mode,
        len(runs),
        [
            (
                n,
                sum(min(r["lengths"][:n]) for r in runs),
                round(sum(sum(r["seconds"][:n]) for r in runs), 1),
            )
            for n in checkpoints
        ],
    )
print("paired runs matched to total wall time spent by shallow on 4 candidates:")
for ident, row in cases.items():
    cap = sum(row["shallow"]["seconds"])

    def budgeted(run):
        used = 0
        lengths = []
        for n, s in zip(run["lengths"], run["seconds"]):
            if used + s > cap + 1e-8:
                break
            used += s
            lengths.append(n)
        return (len(lengths), min(lengths)) if lengths else None

    print(ident, round(cap, 1), {k: budgeted(r) for k, r in row.items()})
