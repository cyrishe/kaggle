"""A puzzle-only routing screen, sampled before looking up programs or scores."""

import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor

from collective_factor_latent import ROOT, detect, extend_table, make_table


def screen(p):
    goals = json.loads(p["targets"])
    limit = int(p["value_limit"])
    roots, entries = detect(goals, limit)
    hits = []
    for n in (4, 6, 9, 14):
        for variant in range(4):
            if not roots:
                continue
            if variant < 2:
                proposal = make_table(goals, roots[:n], entries, variant)
            else:
                proposal = extend_table(goals, roots[:n], limit, variant)
            if proposal:
                hits.append(len(proposal[2]))
    return p["id"], dict(
        flag=bool(hits),
        targets=len(goals),
        max_start=max(json.loads(p["starting_values"])),
        max_represented=max(hits, default=0),
    )


if __name__ == "__main__":
    seed = 119042
    excluded = {2, 60, 78, 529, 74, 489, 6, 3, 7, 8, 11, 12, 16, 17, 18, 22, 25, 27, 28}
    with (ROOT / "data/puzzles.csv").open() as stream:
        rows = sorted(
            (r for r in csv.DictReader(stream) if int(r["id"][-4:]) not in excluded),
            key=lambda r: r["id"],
        )
    sample = random.Random(seed).sample(rows, 100)
    with ProcessPoolExecutor(2) as pool:
        cases = dict(pool.map(screen, sample))
    (ROOT / "reports/collective_structure_screen.json").write_text(
        json.dumps(
            dict(seed=seed, excluded=sorted(excluded), cases=cases),
            separators=(",", ":"),
        )
        + "\n"
    )
    print("triggered", sum(r["flag"] for r in cases.values()), "of", len(cases))
