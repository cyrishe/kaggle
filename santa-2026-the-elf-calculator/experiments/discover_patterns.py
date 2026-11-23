"""Find reusable arithmetic relations from puzzle inputs and targets."""

import argparse
import csv
import itertools
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SAMPLE_IDS = (
    "scored_0001", "scored_0112", "scored_0223", "scored_0390",
    "scored_0556", "scored_0596", "scored_0667", "scored_0810",
)
MAX_EXAMPLES = 8


def operations(a, b, limit):
    """Yield legal arithmetic using two available positive integers."""
    if a + b <= limit:
        yield "+", a, b, a + b
    if a * b <= limit:
        yield "*", a, b, a * b
    large, small = max(a, b), min(a, b)
    if large > small:
        yield "-", large, small, large - small
    if large % small == 0:
        yield "/", large, small, large // small


def short_recipes(starts, limit):
    """Enumerate every value reachable in at most two instructions."""
    recipes = {value: () for value in starts}
    for a, b in itertools.combinations_with_replacement(starts, 2):
        for step in operations(a, b, limit):
            recipes.setdefault(step[-1], (step,))
    first_steps = [(value, path) for value, path in recipes.items() if path]
    for value, path in first_steps:
        for other in (*starts, value):
            for step in operations(value, other, limit):
                recipes.setdefault(step[-1], path + (step,))
    return recipes


def target_links(targets, recipes, limit):
    """Find B = A*k + r with a short recipe for k and for the signed correction."""
    links = []
    for a, b in itertools.combinations(targets, 2):
        # Include pure differences and both rounded ratios. These are search
        # candidates. The resulting instructions still use exact arithmetic.
        quotient = b // a
        for k in sorted({1, quotient, quotient + 1}):
            if k not in recipes and k != 1:
                continue
            product = a * k
            residual = b - product

            candidates = []
            k_path = recipes[k] if k != 1 else ()
            if product <= limit and (residual == 0 or abs(residual) in recipes):
                correction = recipes[abs(residual)] if residual else ()
                steps = len(k_path) + len(correction)
                steps += int(k != 1) + int(residual != 0)
                candidates.append((steps, "after_multiply", k_path, correction))
            # B = (A + r/k)*k sometimes makes the correction much cheaper.
            if k > 1 and residual and residual % k == 0 and abs(residual // k) in recipes:
                correction = recipes[abs(residual // k)]
                candidates.append((len(k_path) + len(correction) + 2,
                                   "before_multiply", k_path, correction))
            if not candidates:
                continue
            steps, order, k_path, correction = min(candidates, key=lambda item: item[0])
            links.append({
                "from": a,
                "to": b,
                "multiplier": k,
                "residual": residual,
                "mode": order,
                "standalone_step_upper_bound": steps,
                "multiplier_recipe": k_path,
                "correction_recipe": correction,
            })
    return sorted(links, key=lambda item: (item["standalone_step_upper_bound"],
                                           abs(item["residual"]), item["from"], item["to"]))


def factor_groups(targets, recipes):
    """Find exact common factors and nearby targets with inexpensive residuals."""
    gcds = {math.gcd(a, b) for a, b in itertools.combinations(targets, 2)}
    divisors = [k for k in recipes if 2 <= k <= 16]
    candidates = gcds | {g // k for g in gcds for k in divisors if g % k == 0}
    groups = []
    for factor in sorted(candidates):
        if factor < 32:  # Ignore ubiquitous small divisors in this scan.
            continue
        exact = [
            {"target": t, "quotient": t // factor, "quotient_recipe": recipes.get(t // factor)}
            for t in targets if t % factor == 0
        ]
        if len(exact) < 2:
            continue
        groups.append({
            "factor": factor,
            "from_pair_gcd": factor in gcds,
            "factor_recipe": recipes.get(factor),
            "exact_targets": exact,
        })
    return sorted(groups, key=lambda group: (-len(group["exact_targets"]), -group["factor"]))


def anchor_groups(targets, groups, recipes, limit):
    """Find a common center with cheap corrections and retain its dependencies."""
    anchors = set(targets)
    for group in groups:
        factor = group["factor"]
        anchors.add(factor)
        for target in targets:
            quotient = target // factor
            for k in (quotient, quotient + 1):
                if 1 <= k <= 128:
                    anchors.add(k * factor)
    for target in targets:
        root = math.isqrt(target)
        anchors.update((root * root, (root + 1) ** 2))

    results = []
    for anchor in sorted(anchors):
        if not 1 <= anchor <= limit:
            continue
        nearby = [
            {"target": t, "residual": t - anchor, "correction_recipe": recipes[abs(t - anchor)]}
            for t in targets if t != anchor and abs(t - anchor) in recipes
        ]
        if len(nearby) < 2:
            continue
        sources = [
            [group["factor"], anchor // group["factor"]]
            for group in groups
            if anchor % group["factor"] == 0 and 2 <= anchor // group["factor"] <= 128
        ]
        exact_multiples = [t for t in targets if t != anchor and t % anchor == 0]
        results.append({
            "anchor": anchor,
            "is_target": anchor in targets,
            "initial_recipe": recipes.get(anchor),
            "is_square": math.isqrt(anchor) ** 2 == anchor,
            "factor_paths": sources,
            "exact_multiples": exact_multiples,
            "nearby_targets": nearby,
        })
    return sorted(results, key=lambda item: (
        -(len(item["nearby_targets"]) + len(item["exact_multiples"])),
        -len(item["exact_multiples"]),
        sum(len(hit["correction_recipe"]) for hit in item["nearby_targets"]),
        item["anchor"],
    ))


def analyze(row):
    starts = sorted(set(json.loads(row["starting_values"])))
    targets = sorted(set(json.loads(row["targets"])))
    limit = int(row["value_limit"])
    recipes = short_recipes(starts, limit)
    links = target_links(targets, recipes, limit)
    groups = factor_groups(targets, recipes)
    anchors = anchor_groups(targets, groups, recipes, limit)
    differences = [link for link in links if link["multiplier"] == 1]
    products = [link for link in links if link["multiplier"] > 1]
    return {
        "id": row["id"],
        "starts": starts,
        "value_limit": limit,
        "target_count": len(targets),
        "counts": {
            "short_difference_links": len(differences),
            "short_multiplicative_links": len(products),
            "shared_factors": len(groups),
            "shared_anchors": len(anchors),
        },
        "short_difference_examples": differences[:MAX_EXAMPLES],
        "short_multiplicative_examples": products[:MAX_EXAMPLES],
        "shared_factor_examples": groups[:MAX_EXAMPLES],
        "shared_anchor_examples": anchors[:MAX_EXAMPLES],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="Puzzle IDs to scan")
    parser.add_argument("--puzzles", type=Path, default=ROOT / "data" / "puzzles.csv")
    parser.add_argument("--output", type=Path, help="Write the discovery report as JSON")
    args = parser.parse_args()
    ids = args.ids or SAMPLE_IDS
    with args.puzzles.open(newline="") as stream:
        rows = {row["id"]: row for row in csv.DictReader(stream)}
    missing = set(ids) - rows.keys()
    if missing:
        parser.error(f"Unknown puzzle IDs: {', '.join(sorted(missing))}")
    report = [analyze(rows[ident]) for ident in ids]
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    for item in report:
        print(item["id"], item["target_count"], item["counts"])


if __name__ == "__main__":
    main()
