"""Replay our archived joint-search programs using only the official puzzle definitions."""
import argparse
import csv
import json
from pathlib import Path

from first_solver import validate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Puzzle IDs, or omit to verify the entire archive.")
    args = parser.parse_args()
    saved = json.loads((ROOT / "reports/joint_bridge_verified_programs.json").read_text())
    with (ROOT / "data/puzzles.csv").open(newline="") as stream:
        puzzles = {row["id"]: row for row in csv.DictReader(stream)}
    ids = sorted(set(args.ids or saved))
    unknown = set(ids) - saved.keys()
    if unknown:
        parser.error("no archived program for " + ", ".join(sorted(unknown)))

    own_total = public_total = wins = ties = 0
    for puzzle_id in ids:
        row = saved[puzzle_id]
        steps, _, targets = validate(puzzles[puzzle_id], row["program"])
        if steps != row["steps"] or targets != row["targets"]:
            raise ValueError(f"{puzzle_id}: archived counts differ from replay")
        public = row["public"]
        own_total += steps
        public_total += public
        wins += steps < public
        ties += steps == public
        if args.ids:
            print(f"{puzzle_id}  targets={targets}  own={steps}  archived_public={public}")
    print(f"cases={len(ids)}  own={own_total}  archived_public={public_total}  wins={wins}  ties={ties}")


if __name__ == "__main__":
    main()
