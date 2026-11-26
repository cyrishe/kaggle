"""Detect a sparse shifted multiplication table directly in a puzzle's target values."""

import argparse
import csv
import json
import math
import random
import subprocess
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from collective_factor_bench import DEFAULT, ROOT, run_job
from first_solver import validate
from hybrid_graph_search import compile_changes, program_rules, rooted_rules


def nearest(n, d):
    return (n + d // 2) // d


def detect(goals, limit):
    # Each table entry must be substantially closer than one unit in either factor.
    # This also suppresses frequent accidental fits for small targets.
    def match(t, k, a, b):
        r = abs(t - k * a * b)
        return (
            min(a, b) >= 100 and k * a * b <= limit and r <= 6000 and 30 * r < min(a, b)
        )

    scales = range(1, 41)
    seed = set()
    for t in goals:
        for k in scales:
            x = math.isqrt(t // k)
            for a in (x, x + 1):
                if match(t, k, a, a):
                    seed.add(a)
    if not seed:
        return [], {}
    # Bidirectional inference. A newly inferred cofactor needs support on
    # different targets before it can become a new source for further expansion.
    roots = set(seed)
    for _ in range(2):
        support = defaultdict(set)
        for a in roots:
            for t in goals:
                for k in scales:
                    b = nearest(t, k * a)
                    if match(t, k, a, b):
                        support[b].add(t)
        roots.update(b for b, members in support.items() if len(members) >= 2)
        if len(roots) > 350:
            roots = set(
                sorted(roots, key=lambda v: (v not in seed, -len(support[v]), v))[:350]
            )
    entries = defaultdict(list)
    uses = defaultdict(set)
    for a in sorted(roots):
        for t in goals:
            for k in scales:
                b = nearest(t, k * a)
                if b < a or b not in roots or not match(t, k, a, b):
                    continue
                r = t - k * a * b
                uses[a].add(t)
                uses[b].add(t)
                entries[t].append((a, b, k, r))
    rank = sorted(uses, key=lambda v: (-len(uses[v]), v not in seed, v))
    return rank, entries


def make_table(goals, centers, entries, seed):
    rng = random.Random(seed)
    allowed = set(centers)
    offers = {}
    for t in goals:
        choices = []
        for a, b, k, r in entries.get(t, []):
            if a not in allowed or b not in allowed:
                continue
            score = math.log2(1 + abs(r)) * 0.30 + 0.7 * (k != 1) + rng.uniform(0, 0.65)
            choices.append((score, a, b, k, r))
        if choices:
            offers[t] = min(choices)[1:]
    actual = {z for a, b, k, r in offers.values() for z in (a, b)}
    if len(offers) < max(4, len(actual)):
        return None
    proxy = set(goals) - offers.keys()
    proxy |= actual
    rules = {}
    for t, (a, b, k, r) in offers.items():
        h = a * b
        rules[h] = ("*", a, b, h)
        if k > 1:
            proxy.add(k)
            rules[k * h] = ("*", h, k, k * h)
        if r:
            proxy.add(abs(r))
            rules[t] = ("+" if r > 0 else "-", k * h, abs(r), t)
    return sorted(proxy), rules, offers


def extend_table(goals, centers, limit, seed):
    # Once centers are corroborated, lift the small coefficient bound.
    # Other requested values can also be exact, already-paid base products.
    rng = random.Random(seed)
    bases = {
        a * b: (a, b)
        for idx, a in enumerate(centers)
        for b in centers[idx:]
        if a * b <= limit
    }
    edges = {}
    offers = {}
    proxy = set()
    used = set()
    scale_use = set()
    residual_use = set()
    for t in goals:
        options = []
        for product, pair in bases.items():
            k = nearest(t, product)
            if (
                k < 1
                or k * product > limit
                or (k == 1 and product == t and pair is None)
            ):
                continue
            r = t - k * product
            if abs(r) > max(8192, min(3000000, product // 4000)):
                continue
            # Cheap coefficients compete with a known base target; a shared root
            # is priced provisionally, then the emitted graph pays its exact cost.
            cost = 0 if pair is None or product in used else 1
            cost += sum(0.65 for a in set(pair or ()) if a not in used)
            cost += (
                0 if k == 1 else 1.1 + (0 if k in scale_use else 0.34 * math.log2(k))
            )
            cost += (
                0
                if r == 0
                else 1.1
                + (0 if abs(r) in residual_use else 0.36 * math.log2(1 + abs(r)))
            )
            options.append((cost + rng.uniform(0, 0.66), product, k, r, pair))
        if options:
            _, prod, k, r, pair = min(options, key=lambda o: o[0])
            offers[t] = (prod, k, r, *(pair or ()))
            if pair:
                a, b = pair
                proxy.update(pair)
                used.update(pair)
                edges[prod] = ("*", a, b, prod)
            used.add(prod)
            if k > 1:
                proxy.add(k)
                scale_use.add(k)
                edges[prod * k] = ("*", prod, k, prod * k)
            if r:
                proxy.add(abs(r))
                residual_use.add(abs(r))
                edges[t] = ("+" if r > 0 else "-", prod * k, abs(r), t)
            # The exact pre-correction product can now be a common ancestor.
            bases.setdefault(prod * k, None)
        else:
            proxy.add(t)
        bases.setdefault(t, None)
    # Some initially priced leaves can themselves be constructed by selected edges.
    proxy -= edges.keys()
    if sum(len(description) > 3 for description in offers.values()) < 4:
        return None
    return sorted(proxy), edges, offers


def build_case(exe, p, starts, goals, base_tries, width):
    started = time.monotonic()
    roots, entries = detect(goals, int(p["value_limit"]))
    best = None
    meta = None
    attempts = []
    seen = set()
    for n_centers in (4, 6, 9, 14):
        for variant in range(4):
            if not roots:
                continue
            if variant < 2:
                data = make_table(goals, roots[:n_centers], entries, variant)
            else:
                data = extend_table(
                    goals, roots[:n_centers], int(p["value_limit"]), variant
                )
            if not data:
                continue
            proxy, rules, offers = data
            signature = tuple(sorted(rules.items()))
            if signature in seen:
                continue
            seen.add(signature)
            synthetic = dict(p, targets=json.dumps(proxy))
            _, _, trial = run_job(
                (exe, synthetic, 2, base_tries, width, 57431 + n_centers * 11 + variant)
            )
            out = None
            for candidate in [trial["program"], *trial["alternatives"]]:
                graph = {
                    v: rule
                    for rule in program_rules(synthetic, candidate)
                    for v in [rule[-1]]
                }
                # Prefer the known products and retain the proxy calculation derivations.
                graph.update({v: r for v, r in rules.items() if v not in proxy})
                for order in (
                    goals,
                    sorted(goals, key=lambda t: (t not in offers, offers.get(t, (t,)))),
                ):
                    try:
                        plan = rooted_rules(starts, order, graph)
                    except (KeyError, ValueError):
                        continue
                    out2 = compile_changes(p, plan, goals)
                    if out2 is not None and (out is None or len(out2) < len(out)):
                        out = out2
            attempts.append(
                dict(
                    centers=n_centers,
                    variant=variant,
                    matched=len(offers),
                    steps=len(out) if out is not None else None,
                )
            )
            if out is not None and (best is None or len(out) < len(best)):
                best = out
                meta = dict(centers=roots[:n_centers], offers=offers)
    if best is not None:
        validate(p, best)
    return dict(
        program=best,
        steps=len(best) if best is not None else None,
        winner=meta,
        roots=roots,
        attempts=attempts,
        seconds=round(time.monotonic() - started, 3),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", type=int, nargs="+", default=DEFAULT + [6])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--width", type=int, default=8)
    ap.add_argument("--out", default="reports/collective_factor_latent.json")
    args = ap.parse_args()
    with (ROOT / "data/puzzles.csv").open() as stream:
        puzzles = {row["id"]: row for row in csv.DictReader(stream)}
    output = {"cases": {}, "parameters": vars(args)}
    with tempfile.TemporaryDirectory() as folder:
        exe = str(Path(folder) / "solver")
        subprocess.run(
            [
                "c++",
                "-std=c++17",
                "-O3",
                str(Path(__file__).with_name("collective_factor_search.cpp")),
                "-o",
                exe,
            ],
            check=True,
        )
        for idx in args.ids:
            ident = f"scored_{idx:04}"
            p = puzzles[ident]
            result = build_case(
                exe,
                p,
                json.loads(p["starting_values"]),
                json.loads(p["targets"]),
                args.trials,
                args.width,
            )
            output["cases"][ident] = result
            (ROOT / args.out).write_text(
                json.dumps(output, separators=(",", ":")) + "\n"
            )
            print(ident, result["steps"], len(result["roots"]), flush=True)


if __name__ == "__main__":
    main()
