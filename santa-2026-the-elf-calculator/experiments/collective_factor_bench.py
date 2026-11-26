"""Measure complete programs from the signed quotient search, without warm-starting."""

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import subprocess
import tempfile
import time

from first_solver import validate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = [2, 60, 78, 529, 74, 489]


def run_job(args):
    executable, puzzle, mode, tries, width, seed = args
    starts = json.loads(puzzle["starting_values"])
    goals = json.loads(puzzle["targets"])
    header = [
        int(puzzle["value_limit"]),
        int(puzzle["registers"]),
        len(starts),
        len(goals),
        mode,
        width,
        tries,
        seed,
    ]
    payload = "\n".join(" ".join(map(str, row)) for row in (header, starts, goals))
    tic = time.monotonic()
    process = subprocess.Popen(
        [executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    process.stdin.write(payload + "\n")
    process.stdin.close()
    best, trajectory, elites = None, [], []
    for line in process.stdout:
        index, length = map(int, line.split())
        ops = []
        for _ in range(length):
            op, *registers = next(process.stdout).split()
            ops.append([op, *map(int, registers)])
        validate(puzzle, ops)
        if best is None or length < len(best):
            best = ops
        if ops not in elites:
            elites.append(ops)
            elites.sort(key=len)
            del elites[3:]
        trajectory.append(
            dict(
                trial=index + 1,
                steps=length,
                best=len(best),
                seconds=round(time.monotonic() - tic, 3),
            )
        )
    if process.wait() or len(trajectory) != tries:
        raise RuntimeError(f'Incomplete search for {puzzle["id"]}')
    print(
        puzzle["id"],
        mode,
        [r["steps"] for r in trajectory],
        round(time.monotonic() - tic, 2),
        flush=True,
    )
    return (
        puzzle["id"],
        str(mode),
        dict(
            program=best,
            alternatives=elites[1:],
            steps=len(best),
            trajectory=trajectory,
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=int, nargs="+", default=DEFAULT)
    ap.add_argument("--modes", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--trials", type=int, default=8)
    ap.add_argument("--width", type=int, default=10)
    ap.add_argument("--seed", type=int, default=173712)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out", default="reports/collective_factor_bench.json")
    args = ap.parse_args()
    with (ROOT / "data/puzzles.csv").open() as stream:
        puzzles = {row["id"]: row for row in csv.DictReader(stream)}
    output = {"parameters": vars(args), "cases": {}}
    with tempfile.TemporaryDirectory() as tmp:
        exe = str(Path(tmp) / "solver")
        subprocess.run(
            [
                "c++",
                "-O3",
                "-std=c++17",
                str(Path(__file__).with_name("collective_factor_search.cpp")),
                "-o",
                exe,
            ],
            check=True,
        )
        jobs = [
            (
                exe,
                puzzles[f"scored_{i:04}"],
                mode,
                args.trials,
                args.width,
                args.seed + i,
            )
            for i in args.ids
            for mode in args.modes
        ]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for ident, mode, data in pool.map(run_job, jobs):
                output["cases"].setdefault(ident, {})[mode] = data
                (ROOT / args.out).write_text(
                    json.dumps(output, separators=(",", ":")) + "\n"
                )


if __name__ == "__main__":
    main()
