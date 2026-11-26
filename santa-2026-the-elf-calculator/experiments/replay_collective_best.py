"""Replay the saved collective-search winners and reconcile the 1,000-puzzle ledger."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from first_solver import validate

ROOT = Path(__file__).resolve().parents[1]


def check(label, actual, expected):
    if actual != expected:
        raise ValueError(f"{label}: expected {expected}, got {actual}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puzzles", type=Path, default=ROOT / "data/puzzles.csv")
    args = parser.parse_args()
    with args.puzzles.open(newline="", encoding="utf-8") as stream:
        puzzles = {row["id"]: row for row in csv.DictReader(stream)}
    reports = ROOT / "reports"
    archive = json.loads((reports / "saved_own_portfolio_audit.json").read_text())
    results = json.loads((reports / "collective_search_best.json").read_text())
    cases = results["cases"]
    old_steps = {key: row["steps"] for key, row in archive["cases"].items()}
    check("archive size", len(old_steps), archive["puzzles"])
    if old_steps.keys() != puzzles.keys():
        raise ValueError("The archive and the input puzzles have different IDs")
    groups = results["groups"]
    members = Counter(key for ids in groups.values() for key in ids)
    check("group membership", members, Counter(cases.keys()))
    old_total = sum(old_steps.values())
    check("prior archive sum", old_total, archive["verified_total"])
    check("prior total in the winner report", old_total, results["old_full"])

    updated = old_steps.copy()
    for key, row in cases.items():
        try:
            steps, _, _ = validate(puzzles[key], row["program"])
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc
        check(f"{key} replay", steps, row["steps"])
        check(f"{key} prior steps", old_steps[key], row["old"])
        updated[key] = min(old_steps[key], steps)
        check(f"{key} saved steps", old_steps[key] - updated[key], row["saved"])

    saved = 0
    for name, ids in groups.items():
        prior = sum(old_steps[key] for key in ids)
        best = sum(updated[key] for key in ids)
        public = sum(cases[key]["public_reference"] for key in ids)
        print(f"{name}: cases={len(ids)} old={prior} best={best} archived_public={public}")
        saved += prior - best
    total = sum(updated.values())
    check("group savings", saved, results["savings"])
    check("archive savings", old_total - total, saved)
    check("updated archive", total, results["updated_full"])
    print(f"replayed={len(cases)} archive_cases={len(updated)} old={old_total} "
          f"saved={saved} updated={total}")


if __name__ == "__main__":
    main()
