"""Replay a matched sequence of independent whole-puzzle walks under multiple proposal policies."""

import argparse
import csv
import json
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from first_solver import validate
from prune_program import prune

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = "0002 0060 0078 0529 0074 0489".split()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", nargs="+", default=DEFAULT)
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--modes", nargs="+", type=int, default=[0, 1], choices=[0, 1, 2, 3, 4, 5])
    ap.add_argument("--output", type=Path, default=ROOT / "reports/collective_walk.json")
    ap.add_argument("--resume", type=Path, help="Reuse the nested trial prefix from this result file")
    args = ap.parse_args()
    ids = [s if s.startswith("scored_") else "scored_" + s for s in args.ids]
    with (ROOT / "data/puzzles.csv").open() as f:
        puzzles = {p["id"]: p for p in csv.DictReader(f) if p["id"] in ids}
    old_rows = json.loads(args.resume.read_text())["cases"] if args.resume else {}
    rows = {ident: old_rows[ident] for ident in ids if ident in old_rows}
    with TemporaryDirectory() as work:
        exe = Path(work) / "walk"
        subprocess.run(
            ["c++", "-O3", "-std=c++20", ROOT / "experiments/collective_walk.cpp", "-o", exe],
            check=True,
        )
        for trial in range(args.trials):
            for ident in ids:
                row = rows.setdefault(ident, {})
                p = puzzles[ident]
                starts, targets = map(json.loads, (p["starting_values"], p["targets"]))
                for mode in args.modes:
                    label = ["shallow", "combined", "modular", "meet", "ladder", "prefix_race"][mode]
                    result = row.setdefault(
                        label, {"lengths": [], "seconds": [], "best_program": [], "programs": []}
                    )
                    if len(result["lengths"]) > trial:
                        continue
                    seed = 11270000 + int(ident[-4:]) * 31 + trial
                    values = [
                        p["value_limit"],
                        p["registers"],
                        len(starts),
                        len(targets),
                        mode,
                        seed,
                        *starts,
                        *targets,
                    ]
                    before = time.perf_counter()
                    lines = subprocess.check_output(
                        [exe], input=" ".join(map(str, values)), text=True
                    ).splitlines()
                    elapsed = time.perf_counter() - before
                    ops = [[w[0], *map(int, w[1:])] for w in (line.split() for line in lines[1:])]
                    assert int(lines[0]) == len(ops)
                    validate(p, ops)
                    ops = prune(p, ops)
                    if trial < 3:
                        result["programs"].append(ops)
                    result["seconds"].append(round(elapsed, 3))
                    result["lengths"].append(len(ops))
                    if not result["best_program"] or len(ops) < len(result["best_program"]):
                        result["best_program"] = ops
                    tmp = args.output.with_suffix(".tmp")
                    tmp.write_text(
                        json.dumps(
                            {"seed": "11270000 + numeric ID * 31 + zero-based trial", "cases": rows},
                            separators=(",", ":"),
                        )
                    )
                    tmp.replace(args.output)
                    print(trial + 1, ident, label, len(ops), round(elapsed, 2), flush=True)


if __name__ == "__main__":
    main()
