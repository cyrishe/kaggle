"""Rebuild the seven product-table hypotheses from official puzzles and a pinned detector."""

import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
IDS = [f"scored_{n:04d}" for n in (2, 60, 78, 529, 74, 489, 6)]
COMMIT = "3bfae157e32a3ea49d6333cf5b0619e9905d44e0"
FILE = "solvers/native/matrix_recover.cpp"
SOURCE = f"https://github.com/Hansen0223/Santa_2026/blob/{COMMIT}/{FILE}"
RAW = f"https://raw.githubusercontent.com/Hansen0223/Santa_2026/{COMMIT}/{FILE}"
SHA256 = "89f673ab1c9e78d97b4ce63a1bcd363235e6afcc76eecc773ec2e21b01dc7aa3"


def detect(executable, puzzle):
    goals = json.loads(puzzle["targets"])
    fields = [puzzle["id"], puzzle["value_limit"], len(goals), *goals]
    output = subprocess.check_output(
        [executable], input=" ".join(map(str, fields)) + "\n", text=True
    )
    header, *lines = output.splitlines()
    ident, hubs_count, matches, score = header.split()
    if ident != puzzle["id"]:
        raise ValueError(f"Unexpected detector output for {puzzle['id']}")
    hubs = list(map(int, lines.pop(0).split())) if int(hubs_count) else []
    if len(hubs) != int(hubs_count) or len(lines) != int(matches):
        raise ValueError(f"Incorrect detector output counts for {ident}")
    targets = []
    seen = set()
    for line in lines:
        t, a, b, k, r, d, e, weight = line.split()
        t, a, b, k, r, d, e = map(int, (t, a, b, k, r, d, e))
        if t not in goals or t in seen or a not in hubs or b not in hubs:
            raise ValueError(f"Unknown or duplicate target or factor for {ident}")
        if t != k * a * b + r or r != k * d + e:
            raise ValueError(f"Invalid integer identity for {ident} target {t}")
        seen.add(t)
        targets.append(dict(t=t, a=a, b=b, k=k, r=r, d=d, e=e, weight=float(weight)))
    return dict(hubs=hubs, targets=targets, total=len(goals), score=float(score))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzles", type=Path, default=ROOT / "data/puzzles.csv")
    parser.add_argument("--source", type=Path, help="Use a local copy of the pinned C++ source")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/collective_matrix_fits.json")
    args = parser.parse_args()
    with args.puzzles.open(newline="") as stream:
        puzzles = {row["id"]: row for row in csv.DictReader(stream) if row["id"] in IDS}
    if puzzles.keys() != set(IDS):
        raise ValueError(f"Missing puzzles: {sorted(set(IDS) - puzzles.keys())}")
    if args.source:
        source = args.source.read_bytes()
    else:
        with urlopen(RAW, timeout=30) as response:
            source = response.read()
    if hashlib.sha256(source).hexdigest() != SHA256:
        raise ValueError("Detector source differs from the pinned revision")
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "matrix_recover.cpp"
        executable = Path(work) / "matrix_recover"
        path.write_bytes(source)
        subprocess.run(["c++", "-O3", "-std=c++17", path, "-o", executable], check=True)
        cases = {key: detect(executable, puzzles[key]) for key in IDS}
    report = dict(source=SOURCE, source_sha256=SHA256, flags=[], cases=cases)
    args.output.write_text(json.dumps(report, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
