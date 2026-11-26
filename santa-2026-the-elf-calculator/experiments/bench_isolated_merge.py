"""First solve each target from the starts, then merge and rewrite its internal expressions."""
import argparse
import csv
import json
import random
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from choose_target_paths import choose
from converge_target_paths import improve
from first_solver import validate
from hybrid_graph_search import compile_changes
from isolated_target_paths import IsolatedSolver
from probe_baseline_pair import compile_values

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/isolated_merge.json'
DIAGNOSTICS = ('scored_0289', 'scored_0810', 'scored_0253', 'scored_0035', 'scored_0667')


def exact_short_paths(binary, starts, goals, limit):
    wire = f'{limit} {len(starts)} {len(goals)}\n' + ' '.join(map(str, starts)) + '\n' + ' '.join(map(str, goals)) + '\n'
    lines = iter(subprocess.check_output([binary], input=wire, text=True).splitlines())
    hits = {}
    for target in goals:
        goal, count = map(int, next(lines).split())
        assert target == goal
        paths = []
        for _ in range(count):
            path = []
            for _ in range(int(next(lines))):
                op, a, b, value = next(lines).split()
                path.append((op, int(a), int(b), int(value)))
            paths.append(path)
        hits[goal] = paths
    return hits


def diversity(candidates, keep=6):
    """Start with the shortest path and retain alternatives with different intermediate values."""
    remaining = sorted(set(tuple(map(tuple, path)) for path in candidates), key=lambda p:(len(p), p))
    best = remaining.pop(0)
    selected = [best]
    visited = {r[-1] for r in best}
    remaining = [p for p in remaining if len(p) <= len(best) + 3]
    while remaining and len(selected) < keep:
        def rank(path):
            distinct = sum(r[-1] not in visited for r in path)
            return (len(path) - min(4, distinct) * 0.3, -distinct, path)
        choice = min(remaining, key=rank)
        selected.append(choice)
        visited.update(r[-1] for r in choice)
        remaining.remove(choice)
    return [list(p) for p in selected]


def isolated_concatenation(puzzle, catalog):
    # Preserve the original input registers across segments. Each target starts
    # from an empty set of temporaries, even if the preceding target made a useful value.
    starts = json.loads(puzzle['starting_values'])
    init = {v:i for i,v in enumerate(starts)}
    ops = []
    for target, paths in catalog.items():
        program = paths[0]
        if not program:
            assert target in init
            continue
        last = {v:i for i,r in enumerate(program) for v in r[1:3]}
        where = dict(init)
        free = set(range(len(starts), int(puzzle['registers'])))
        for i,(op,a,b,value) in enumerate(program):
            left, right = where[a], where[b]
            for v in {a,b}:
                if last[v] == i and v not in init:
                    free.add(where.pop(v))
            if not free:
                raise ValueError('no scratch register in isolated concatenation')
            dest = min(free)
            ops.append([op,left,right,dest])
            if value in last:
                where[value] = dest
                free.remove(dest)
    validate(puzzle,ops)
    return ops


def exact_merge(puzzle, catalog, raw, seed):
    goals = list(catalog)
    rng = random.Random(seed)
    orders = [goals, goals[::-1], sorted(goals, key=lambda t:len(catalog[t][0]))]
    for _ in range(12):
        order = list(goals)
        rng.shuffle(order)
        orders.append(order)
    best = raw
    for order in orders:
        flat = [row for t in order for row in catalog[t][0]]
        candidate = compile_changes(puzzle, flat, goals)
        if candidate is not None and len(candidate) < len(best):
            best = candidate
    return best


def save(path, value):
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(value, separators=(',',':'))+'\n')
    tmp.replace(path)


def run(job):
    p, binary, seed, work = job
    ident = p['id']
    case_seed = seed + int(ident.split('_')[-1])
    starts = json.loads(p['starting_values'])
    goals = json.loads(p['targets'])
    tick = time.monotonic()
    exact = exact_short_paths(binary,starts,goals,int(p['value_limit']))
    solver = IsolatedSolver(starts,int(p['value_limit']),int(p['registers']))
    catalog = {}
    solo = {}
    for t in goals:
        heur = solver.paths(t)
        paths = diversity(list(heur) + exact[t])
        proxy = dict(p,targets=json.dumps([t]))
        for path in paths:
            prog = compile_values(proxy,path,[t])
            if validate(proxy,prog)[0] != len(path):
                raise ValueError(f'nonminimal dependency slice in {ident} / {t}')
        lengths = [len(s) for s in paths]
        if exact[t] and len(exact[t][0]) != min(lengths):
            raise ValueError('exact and heuristic disagree')
        if not exact[t] and min(lengths) <= 4:
            raise ValueError('missing certified path')
        lower = len(exact[t][0]) if exact[t] else 5
        solo[t] = dict(steps=lengths[0],lower_bound=lower,known_optimal=(lower==lengths[0]),
                       alternatives=lengths,best_heuristic=min(map(len,heur)),shortest_path=paths[0])
        catalog[t] = paths
    if work:
        save(work/'catalog'/f'{ident}.json',catalog)
    t_solo = time.monotonic()
    raw = isolated_concatenation(p,catalog)
    same = exact_merge(p,catalog,raw,case_seed)
    t_same = time.monotonic()
    joint,choice_stats = choose(p,catalog,same,seed=case_seed)
    t_choice = time.monotonic()
    fused,rewrite_stats = improve(p,joint,seed=case_seed,rounds=8)
    # Isolate the effect of internal rewiring even when alternative paths plateau.
    straight,straight_stats = improve(p,same,seed=case_seed,rounds=8) if joint!=same else (fused,rewrite_stats)
    winner = min([fused,straight],key=len)
    programs = dict(raw=raw,equal=same,choices=joint,rewire_from_equal=straight,rewire_from_choices=fused,best=winner)
    lengths = {label:validate(p,prog)[0] for label,prog in programs.items()}
    assert lengths['raw'] == sum(x['steps'] for x in solo.values())
    row = dict(targets=solo, steps=lengths,programs=programs,choice=choice_stats,
               rewrite=rewrite_stats, rewrite_from_equal=straight_stats,
               seconds=dict(solo=round(t_solo-tick,3),equal=round(t_same-t_solo,3),
                            choices=round(t_choice-t_same,3),rewrites=round(time.monotonic()-t_choice,3)))
    if work:
        save(work/'cases'/f'{ident}.json',row)
    return ident,row


def compare(rows):
    old = json.loads((ROOT/'reports/paired_tail_repair.json').read_text())['cases']
    for key,row in rows.items():
        if key in old:
            parent = old[key]
            row['previous'] = min(v['steps'] for v in parent['methods'].values())
            row['public'] = parent['public_archived_steps']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids',nargs='+',default=DIAGNOSTICS)
    parser.add_argument('--all-archive',action='store_true')
    parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--seed',type=int,default=20261126)
    parser.add_argument('--work-dir',type=Path,help='Keep separate catalogs and per-case checkpoints')
    parser.add_argument('--output',type=Path,default=REPORT)
    args=parser.parse_args()
    with (ROOT/'data/puzzles.csv').open() as stream:
        puzzles={r['id']:r for r in csv.DictReader(stream)}
    ids=list(dict.fromkeys([v if v.startswith('scored_') else 'scored_'+v for v in args.ids]))
    if args.all_archive:
        ids += sorted(set(json.loads((ROOT/'reports/joint_bridge_verified_programs.json').read_text()))-set(ids))
    if args.work_dir:
        for folder in ('catalog','cases'):
            (args.work_dir/folder).mkdir(parents=True,exist_ok=True)
    cases={}
    with tempfile.TemporaryDirectory() as tmp:
        binary=Path(tmp)/'exact-four'
        subprocess.run(['c++','-std=c++17','-O3',str(Path(__file__).with_name('isolated_exact_four.cpp')),'-o',binary],check=True)
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs=[pool.submit(run,(puzzles[i],binary,args.seed,args.work_dir)) for i in ids]
            for done in as_completed(jobs):
                ident,row=done.result()
                print(ident,row['steps'],row['seconds'],flush=True)
                cases[ident]=row
    compare(cases)
    save(args.output,dict(seed=args.seed,puzzle_ids=ids,cases={i:cases[i] for i in ids}))


if __name__ == '__main__':
    main()
