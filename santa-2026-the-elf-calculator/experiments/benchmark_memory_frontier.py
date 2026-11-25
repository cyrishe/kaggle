"""Compare additional third-depth recipe capacity at fixed live-search settings."""
import argparse
import csv
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

from depth_graph_study import ROOT, DEFAULT_PUZZLES, rules
from first_solver import validate
from hybrid_graph_search import Construction, live_rollout


def partial_layer(model, cap):
    support = {}
    for v, rule in model.shallow.items():
        support[v] = set() if rule is None else support[rule[1]] | support[rule[2]] | {v}
    keys = sorted(support, key=lambda v:(len(support[v]), v))
    recipes, costs = {}, {}
    pairs = 0
    for j,b in enumerate(keys):
        for i in range(j+1):
            a = keys[i]
            pairs += 1
            for rule in rules(min(a,b),max(a,b),model.limit):
                v = rule[3]
                if 0<v<=model.limit and v not in support and v not in recipes:
                    recipes[v] = rule
                    costs[v] = 1+len(support[a] | support[b])
                    if len(recipes)==cap:
                        return (recipes,costs),pairs,False
    return (recipes,costs),pairs,True


def measure(ident, cap):
    start = time.perf_counter()
    with DEFAULT_PUZZLES.open() as f:
        puzzle = next(p for p in csv.DictReader(f) if p['id']==ident)
    model = Construction(puzzle)
    extra, pairs, complete = partial_layer(model,cap) if cap else (None,0,False)
    built = time.perf_counter()
    program, _ = live_rollout(model, virtual=True, extra_layer=extra)
    validate(puzzle,program)
    end = time.perf_counter()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return dict(id=ident,cap=cap,extra_nodes=len(extra[0]) if extra else 0,
                complete=complete,pairs=pairs,steps=len(program),program=program,
                build_seconds=round(built-start,3),total_seconds=round(end-start,3),
                peak_MiB=round(rss/(2**20 if sys.platform=='darwin' else 1024),1))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',nargs=2)
    args = parser.parse_args()
    if args.worker:
        ident, cap = args.worker
        print(json.dumps(measure(ident,int(cap))))
    else:
        historical = json.loads((ROOT/'reports/hybrid_graph_results.json').read_text())
        selected = [r for r in historical['cases'] if r['group']=='diagnostic']
        selected += [r for r in historical['cases'] if r['group']=='holdout_random'][:2]
        rows = []
        for case in selected:
            for cap in (0,50000,500000):
                output = subprocess.check_output([sys.executable,__file__,'--worker',case['id'],str(cap)],text=True)
                row = json.loads(output)
                if not cap:
                    assert row['steps'] == case['steps']['virtual_fixed']
                row['prior_best'] = case['steps']['own_final']
                rows.append(row)
                print(row['id'],cap,row['extra_nodes'],row['steps'],row['peak_MiB'],row['total_seconds'],flush=True)
        (ROOT/'reports/memory_frontier_benchmark.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
