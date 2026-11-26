"""Replay new own-only candidates, select per-puzzle minima and compare to the frozen archive."""

import csv
import json

from collective_factor_bench import DEFAULT, ROOT
from first_solver import validate

REPORTS = ROOT / "reports"
# Entries involving an external solver or external matrix hypotheses are controls only.
SOURCES = (
    "collective_factor_32",
    "collective_factor_latent",
    "collective_walk",
    "collective_walk_ladder",
    "collective_walk_meet",
    "collective_walk_modular",
    "collective_walk_0060_restarts",
    "collective_walk_prefix_race",
    "collective_fusion",
    "collective_fusion_extra",
    "collective_fusion_hard",
    "collective_factor_512_hard",
    "collective_factor_blind_control48",
    "collective_factor_latent_blind",
    "collective_blind_joint_repair",
    "collective_screen_control48",
    "collective_screen_latent",
)


def programs(record, label):
    if isinstance(record, dict):
        for key, value in record.items():
            tag = label + "/" + key
            if key in ("program", "best_program"):
                if value:
                    yield tag, value
            elif key in ("programs", "alternatives") and isinstance(value, list):
                for j, p in enumerate(value):
                    if isinstance(p, list) and p:
                        yield tag + "/" + str(j), p
            elif isinstance(value, dict):
                yield from programs(value, tag)


def main():
    with (ROOT / "data/puzzles.csv").open() as f:
        puzzles = {r["id"]: r for r in csv.DictReader(f)}
    prev = json.loads((REPORTS / "saved_own_portfolio_audit.json").read_text())
    best = {}
    checked = 0
    for source in SOURCES:
        cases = json.loads((REPORTS / (source + ".json")).read_text())["cases"]
        for i, case in cases.items():
            for tag, prog in programs(case, source):
                n = validate(puzzles[i], prog)[0]
                checked += 1
                if i not in best or n < best[i]["steps"]:
                    best[i] = dict(steps=n, program=prog, source=tag)
    public = json.loads((REPORTS / "public_v89_step_counts.json").read_text())["steps"]
    for i, data in best.items():
        data["old"] = prev["cases"][i]["steps"]
        data["saved"] = max(0, data["old"] - data["steps"])
        data["public_reference"] = public[i]
    groups = {
        "core": ["scored_%04d" % n for n in DEFAULT],
        "small_seed_12": list(
            json.loads((REPORTS / "collective_factor_latent_blind.json").read_text())[
                "cases"
            ]
        ),
        "screened_positives": list(
            json.loads((REPORTS / "collective_screen_latent.json").read_text())["cases"]
        ),
        "known_positive": ["scored_0006"],
    }
    for name, ids in groups.items():
        print(name, [(i, best[i]["old"], best[i]["steps"], public[i]) for i in ids])
        print(
            "total",
            sum(best[i]["old"] for i in ids),
            sum(min(best[i]["old"], best[i]["steps"]) for i in ids),
            sum(public[i] for i in ids),
        )
    savings = sum(data["saved"] for data in best.values())
    report = dict(
        verified_candidates_including_duplicates=checked,
        old_full=prev["verified_total"],
        savings=savings,
        updated_full=prev["verified_total"] - savings,
        groups=groups,
        cases=best,
    )
    (REPORTS / "collective_search_best.json").write_text(
        json.dumps(report, separators=(",", ":")) + "\n"
    )
    print(
        "archive",
        report["old_full"],
        report["updated_full"],
        "puzzles",
        len(best),
        "checked",
        checked,
    )


if __name__ == "__main__":
    main()
