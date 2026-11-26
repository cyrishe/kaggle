"""Measure a pinned public constructor using only the official puzzle definitions."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time
from urllib.request import urlopen

from first_solver import validate


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f392d2444f5d87146a4a856f6f00a6cdc9c89c62"
SOURCE = (
    "https://raw.githubusercontent.com/niclox44/ElfCalculator-Kaggle/"
    + COMMIT + "/third_party/santa_dictionary/beam_search.cpp"
)
SHA256 = "b0468e79adca7358d24b3ac44d5678536f29bf01774c5039d1119b0c01c415a4"
DEFAULT_IDS = [f"scored_{n:04d}" for n in (2, 60, 78, 529, 74, 489)]


def input_row(puzzle):
    initial = json.loads(puzzle["starting_values"])
    targets = json.loads(puzzle["targets"])
    return " ".join(map(str, [
        puzzle["id"], puzzle["value_limit"], len(initial), len(targets), *initial, *targets
    ]))


def child_cpu():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def measure(executable, puzzles, flags):
    data = "\n".join(map(input_row, puzzles.values())) + "\n"
    started, cpu = time.monotonic(), child_cpu()
    result = subprocess.run([executable, *flags], input=data, text=True,
                            capture_output=True, check=True, timeout=180)
    elapsed, cpu = time.monotonic() - started, child_cpu() - cpu
    programs = {}
    for line in result.stdout.splitlines():
        puzzle_id, encoded = line.split(" ", 1)
        ops = json.loads(encoded)
        steps, _, covered = validate(puzzles[puzzle_id], ops)
        if puzzle_id in programs:
            raise ValueError(f"duplicate program for {puzzle_id}")
        programs[puzzle_id] = {"steps": steps, "covered": covered, "program": ops}
    if programs.keys() != puzzles.keys():
        raise ValueError("incomplete puzzle set")
    return {"flags": flags, "cpu_seconds": round(cpu, 3), "wall_seconds": round(elapsed, 3),
            "sum_steps": sum(p["steps"] for p in programs.values()), "cases": programs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    parser.add_argument("--source", type=Path, help="Optional offline pinned C++ source")
    parser.add_argument("--compiler", default="c++")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "reports" / "collective_external_control.json")
    args = parser.parse_args()
    if args.source:
        source = args.source.read_bytes()
    else:
        with urlopen(SOURCE, timeout=30) as response:
            source = response.read()
    if hashlib.sha256(source).hexdigest() != SHA256:
        raise ValueError("public source differs from the pinned version")
    with (ROOT / "data" / "puzzles.csv").open() as stream:
        puzzle_rows = {p["id"]: p for p in csv.DictReader(stream)}
    puzzles = {key: puzzle_rows[key] for key in args.ids}
    flags = ["3", ".18", "52", "56", "19"]
    settings = {"fixed": ["0", "0"], "shuffle_17": ["2", "17"],
                "shuffle_29": ["2", "29"], "replan": ["1", "0"]}
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "dictionary.cpp"
        path.write_bytes(source)
        executable = Path(temp) / "dictionary"
        subprocess.run([args.compiler, "-std=c++17", "-O3", path, "-o", executable], check=True)
        runs = {name: measure(executable, puzzles, flags + extra) for name, extra in settings.items()}
    report = {"source": SOURCE, "commit": COMMIT, "sha256": SHA256,
              "provenance": "Public constructor by Tony Li, parameterized by konbu17 and extended by niclox44; no input programs or precomputed intermediates.",
              "ids": args.ids, "budget": "One full construction per arm and case; one CPU process. Runtime excludes compilation and independent replay.",
              "runs": runs}
    args.output.write_text(json.dumps(report, separators=(",", ":")) + "\n")
    for name, run in runs.items():
        print(name, run["sum_steps"], run["cpu_seconds"])


if __name__ == "__main__":
    main()
