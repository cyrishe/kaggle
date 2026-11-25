"""Run matched construction and repair on fixed random and diagnostic scored cases."""
import argparse
import csv
import json
import random
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections import Counter

from baseline_lineage import DB, DEFAULT_PUZZLES, ROOT
from first_solver import validate
from hybrid_graph_search import Construction, graph_search, live_rollout, local_repair

SAMPLE_SEED = 20261125
SEARCH_SEEDS = (11, 29, 47)
DIAGNOSTICS = ('scored_0001', 'scored_0253', 'scored_0667', 'scored_0810')


def load_reference(ident):
    with sqlite3.connect(DB.resolve().as_uri()+'?mode=ro', uri=True) as db:
        rows = db.execute('''SELECT n.op,l.dest,r.dest,n.dest FROM nodes n
            JOIN nodes l ON l.puzzle=n.puzzle AND l.step=n.left_step
            JOIN nodes r ON r.puzzle=n.puzzle AND r.step=n.right_step
            WHERE n.puzzle=? ORDER BY n.step''', (ident,))
        return [list(row) for row in rows]


def run(puzzle):
    ident = puzzle['id']
    result = dict(id=ident, steps={}, seconds={}, programs={}, details={})
    def record(name, start, program):
        steps, _, _ = validate(puzzle, program)
        result['steps'][name] = steps
        result['seconds'][name] = round(time.monotonic()-start, 3)
        result['programs'][name] = program
    start = time.monotonic()
    public = load_reference(ident)
    record('public', start, public)
    start = time.monotonic()
    model = Construction(puzzle)
    control = model.construct()
    record('signed_radix', start, control)
    result.update(layers=model.layer_counts, shared_factor_groups=len(model.groups))
    start = time.monotonic()
    deterministic, stats = graph_search(model, control)
    record('factor_graph', start, deterministic)
    result['details']['factor_graph'] = stats
    start = time.monotonic()
    best = deterministic
    repeats = []
    for seed in SEARCH_SEEDS:
        program, info = graph_search(model, deterministic, seed)
        repeats.append(dict(seed=seed, steps=len(program), **info))
        if len(program)<len(best):
            best = program
    record('stochastic_graph', start, best)
    result['details']['stochastic_graph'] = repeats
    start = time.monotonic()
    rollout, stats = live_rollout(model)
    record('live_fixed', start, rollout if rollout is not None else best)
    result['details']['live_fixed'] = dict(finished=rollout is not None, **stats)
    start = time.monotonic()
    live_best = rollout
    repeats = []
    for seed in SEARCH_SEEDS:
        trial, stats = live_rollout(model, seed)
        repeats.append(dict(seed=seed, steps=len(trial) if trial is not None else None, **stats))
        if trial is not None and (live_best is None or len(trial)<len(live_best)):
            live_best = trial
    if live_best is not None and len(live_best)<len(best):
        best = live_best
    record('live_portfolio', start, best)
    result['details']['live_portfolio'] = repeats
    start = time.monotonic()
    common = model.common
    model.common = Counter()
    no_gcd, info = live_rollout(model, virtual=True)
    model.common = common
    record('virtual_no_gcd', start, no_gcd if no_gcd is not None else control)
    result['details']['virtual_no_gcd'] = dict(finished=no_gcd is not None, **info)
    start = time.monotonic()
    fixed, info = live_rollout(model, virtual=True)
    record('virtual_fixed', start, fixed if fixed is not None else control)
    result['details']['virtual_fixed'] = dict(finished=fixed is not None, **info)
    start = time.monotonic()
    variants = [p for p in [fixed] if p is not None]
    repeats = []
    for seed in SEARCH_SEEDS:
        trial, info = live_rollout(model, seed, virtual=True)
        repeats.append(dict(seed=seed, steps=len(trial) if trial is not None else None, **info))
        if trial is not None:
            variants.append(trial)
    if variants:
        vbest = min(variants,key=len)
        if len(vbest)<len(best):
            best = vbest
    record('virtual_portfolio', start, best)
    result['details']['virtual_portfolio'] = repeats
    for name, initial in [('repair_own', best), ('repair_public', public)]:
        start = time.monotonic()
        best_program = initial
        repeats = []
        for seed in SEARCH_SEEDS:
            program, wins = local_repair(puzzle, initial, seed, budget=32, reschedule=True)
            repeats.append(dict(seed=seed, steps=len(program), wins=wins))
            if len(program)<len(best_program):
                best_program = program
        record(name, start, best_program)
        result['details'][name] = repeats
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=12)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--holdout', action='store_true', help='Sample from outside the initial 12 cases and four diagnostics.')
    parser.add_argument('--ids', nargs='+', help='Benchmark only the named scored puzzles.')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles = {p['id']: p for p in csv.DictReader(f)}
    seed = SAMPLE_SEED
    population = sorted(puzzles)
    diagnostics = list(DIAGNOSTICS)
    if args.holdout:
        excluded = set(random.Random(seed).sample(population, 12)) | set(diagnostics)
        population = [ident for ident in population if ident not in excluded]
        seed += 1
        diagnostics = []
    sample = random.Random(seed).sample(population, args.count)
    ids = list(dict.fromkeys(sample + diagnostics))
    if args.ids:
        sample, diagnostics = [], list(dict.fromkeys(args.ids))
        ids = diagnostics
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        cases = []
        for item in pool.map(run, [puzzles[i] for i in ids]):
            cases.append(item)
            print(item['id'], item['steps'], flush=True)
    report = dict(sample_seed=seed, sample=sample, diagnostics=diagnostics,
                  search_seeds=SEARCH_SEEDS, cases=cases)
    filename = 'hybrid_graph_holdout.json' if args.holdout else 'hybrid_graph_benchmark.json'
    if args.ids:
        filename = 'hybrid_graph_selected.json'
    destination = args.output or ROOT/'reports'/filename
    destination.write_text(json.dumps(report, separators=(',', ':'))+'\n')
