"""Matched-budget UCB and round-robin allocation of complete stochastic rollouts."""
import argparse
import csv
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from baseline_lineage import DEFAULT_PUZZLES, ROOT
from first_solver import validate
from hybrid_graph_search import Construction, live_rollout

ARMS = ('order', 'shared', 'residual')
SEED = 20261125


def compare(item):
    puzzle, reference = item
    model = Construction(puzzle)
    cache = {}

    def trial(arm, repetition):
        key = arm, repetition
        if key not in cache:
            start = time.monotonic()
            p, _ = live_rollout(model, seed=SEED+repetition, virtual=True, policy=arm)
            if p is not None:
                validate(puzzle,p)
            cache[key] = p, time.monotonic()-start
        return cache[key]

    result = dict(id=puzzle['id'], fixed=len(reference))
    for policy in ('round_robin','ucb'):
        visits = [0]*len(ARMS)
        rewards = [0.0]*len(ARMS)
        best = reference
        log = []
        for i in range(9):
            if i<len(ARMS) or policy=='round_robin':
                idx = i%len(ARMS)
            else:
                idx = max(range(len(ARMS)), key=lambda k:rewards[k]/visits[k] +
                          0.35*math.sqrt(2*math.log(i)/visits[k]))
            arm = ARMS[idx]
            p,elapsed = trial(arm,visits[idx])
            visits[idx] += 1
            steps = len(p) if p is not None else None
            reward = (0.5+(len(reference)-steps)/max(12,0.24*len(reference))) if p is not None else 0.0
            rewards[idx] += min(1.0,max(0.0,reward))
            if p is not None and steps<len(best):
                best = p
            log.append(dict(arm=arm,repeat=visits[idx],steps=steps,seconds=round(elapsed,4)))
        result[policy] = dict(steps=len(best),program=best,trials=log,visits=visits)
    print(puzzle['id'],result['fixed'],result['round_robin']['steps'],result['ucb']['steps'],flush=True)
    return result


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',nargs='+',type=Path)
    args = parser.parse_args()
    with DEFAULT_PUZZLES.open() as f:
        puzzles = {p['id']:p for p in csv.DictReader(f)}
    items = [(puzzles[c['id']],c['programs']['virtual_fixed'])
             for path in args.reports for c in json.loads(path.read_text())['cases']]
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(compare,items))
    (ROOT/'reports/hybrid_rollout_bandit.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
